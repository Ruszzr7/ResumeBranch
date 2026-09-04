"""Preview-first, deterministic resume edit capability.

The conversation model is responsible for understanding the user's request and
emitting structured operations.  This module deliberately does not call an
LLM: it validates and applies those operations to copies of the canonical
resume/layout data, then returns a candidate for the existing confirmation
flow.  Persistence remains exclusively behind confirmation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.layout_config import normalize_layout_config
from backend.layout_capabilities import (
    EDITABLE_GLOBAL_FIELDS,
    EDITABLE_MODULE_FIELDS,
    validate_layout_operations,
)
from backend.resume_contract import (
    CONTENT_BLOCK_SEMANTIC_ROLES,
    RESUME_EDIT_ROOTS,
    validate_resume_operation_path,
    validate_resume_operation_item,
    validate_resume_operation_value,
)
from backend.resume_changes import (
    build_resume_state_version,
    resume_state_version_matches,
)
from backend.resume_schema import validate_resume_data


MAX_OPERATIONS = 100
MAX_OPERATION_VALUE_BYTES = 256 * 1024
MAX_PATH_DEPTH = 32


class ResumeEditToolInput(BaseModel):
    """Arguments the model is allowed to supply to the Skill."""

    model_config = ConfigDict(extra="forbid")

    answer_text: str = Field(
        default="",
        description="修改预览前需要展示的独立回答或澄清；纯修改请求留空。",
    )
    resume_operations: list[dict] = Field(
        default_factory=list,
        description="本次明确授权的简历内容结构化操作。",
    )
    layout_operations: list[dict] = Field(
        default_factory=list,
        description="本次明确授权且属于对话可编辑范围的排版结构化操作。",
    )


class ResumeEditRuntimeContext(BaseModel):
    """Trusted graph-owned context that the model cannot provide."""

    model_config = ConfigDict(extra="forbid")

    resume_data: dict = Field(default_factory=dict)
    layout_config: dict = Field(default_factory=dict)
    jd_data: dict = Field(default_factory=dict)
    context_type: str = "main"
    base_version: dict[str, str] = Field(default_factory=dict)
    conversation_context: str = ""


class ResumeEditOutput(BaseModel):
    """Validated candidate returned to the existing confirmation flow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resume_data: dict
    layout_config: dict
    base_version: dict[str, str]
    resume_operations: tuple[dict, ...] = ()
    layout_operations: tuple[dict, ...] = ()
    already_satisfied: bool = False

_PATH_SEGMENT_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<indexes>(?:\[\d+\])*)$")
_INDEX_RE = re.compile(r"\[(\d+)\]")

_RESUME_ROOTS = set(RESUME_EDIT_ROOTS)
_LAYOUT_ROOTS = {"global", *EDITABLE_MODULE_FIELDS}
_FORBIDDEN_LAYOUT_PARTS = {
    "fontsize",
    "fontsizes",
    "latinfont",
    "eastasiafont",
    "fallbackfonts",
}


class ResumeEditOperationError(ValueError):
    """Raised when a structured operation cannot be safely applied."""


@dataclass(frozen=True)
class ResumeEditRequest:
    """Canonical data plus operations resolved by the conversation model."""

    resume_data: dict = field(default_factory=dict)
    layout_config: dict = field(default_factory=dict)
    resume_operations: tuple[dict, ...] = ()
    layout_operations: tuple[dict, ...] = ()
    jd_data: dict = field(default_factory=dict)
    context_type: str = "main"
    base_version: dict[str, str] = field(default_factory=dict)
    conversation_context: str = ""


@dataclass(frozen=True)
class ResumeEditResult:
    resume_data: dict
    layout_config: dict
    base_version: dict[str, str]
    resume_operations: tuple[dict, ...] = ()
    layout_operations: tuple[dict, ...] = ()
    already_satisfied: bool = False


def _coerce_operations(value: Any, *, field_name: str) -> tuple[dict, ...]:
    """Normalize tool arguments without interpreting natural language."""
    if value in (None, "", []):
        return ()
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ResumeEditOperationError(f"{field_name} 必须是结构化操作列表")
    if len(value) > MAX_OPERATIONS:
        raise ResumeEditOperationError("单次修改操作过多，无法安全生成预览")
    operations: list[dict] = []
    for operation in value:
        if not isinstance(operation, dict):
            raise ResumeEditOperationError(f"{field_name} 中存在无效操作")
        operations.append(deepcopy(operation))
    return tuple(operations)


def _parse_path(path: Any, *, roots: set[str], field_name: str) -> tuple[str | int, ...]:
    value = str(path or "").strip()
    if not value or value.startswith("/") or ".." in value or "__" in value:
        raise ResumeEditOperationError(f"{field_name} 路径无效")
    tokens: list[str | int] = []
    for segment in value.split("."):
        match = _PATH_SEGMENT_RE.fullmatch(segment)
        if not match:
            raise ResumeEditOperationError(f"{field_name} 路径无效")
        key = match.group("key")
        if not tokens and key not in roots:
            raise ResumeEditOperationError(f"{field_name} 路径不在允许的简历范围内")
        tokens.append(key)
        for raw_index in _INDEX_RE.findall(match.group("indexes")):
            tokens.append(int(raw_index))
    if len(tokens) > MAX_PATH_DEPTH:
        raise ResumeEditOperationError(f"{field_name} 路径层级过深")
    return tuple(tokens)


def _resolve(root: Any, tokens: tuple[str | int, ...], *, path: str) -> Any:
    current = root
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, list) or token < 0 or token >= len(current):
                raise ResumeEditOperationError(f"目标路径不存在：{path}")
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                raise ResumeEditOperationError(f"目标路径不存在：{path}")
            current = current[token]
    return current


def _resolve_parent(root: Any, tokens: tuple[str | int, ...], *, path: str) -> tuple[Any, str | int]:
    if not tokens:
        raise ResumeEditOperationError(f"目标路径为空：{path}")
    return _resolve(root, tokens[:-1], path=path), tokens[-1]


def _check_expected(current: Any, operation: dict, *, path: str) -> None:
    if "expected" in operation and current != operation["expected"]:
        raise ResumeEditOperationError(f"目标内容已变化，无法安全修改：{path}")


def _validate_semantic_target(
    root: Any,
    tokens: tuple[str | int, ...],
    operation: dict,
    *,
    path: str,
) -> None:
    """Validate an optional semantic assertion for indexed content blocks.

    Array positions identify a storage location, not a meaning.  When the
    model supplies ``target_semantic_role`` the assertion is checked against
    the normalized block before applying the operation, so an index chosen for
    one role cannot silently mutate another.  The field remains optional for
    non-indexed/list-level operations and older callers.
    """
    if "target_semantic_role" not in operation:
        return
    requested = operation.get("target_semantic_role")
    if not isinstance(requested, str) or requested not in CONTENT_BLOCK_SEMANTIC_ROLES:
        raise ResumeEditOperationError(f"内容块目标语义角色无效：{path}")

    content_blocks_index: int | None = None
    for index, token in enumerate(tokens[:-1]):
        if token == "content_blocks" and isinstance(tokens[index + 1], int):
            content_blocks_index = index + 1
            break

    if content_blocks_index is None:
        # For append/insert, the assertion describes the new block itself;
        # other paths must not carry a semantic assertion unrelated to a block.
        if (
            tokens and tokens[-1] == "content_blocks"
            and str(operation.get("op", operation.get("type", ""))).lower() in {"append", "insert"}
        ):
            value = operation.get("value")
            actual = value.get("semantic_role") if isinstance(value, dict) else None
            if actual != requested:
                raise ResumeEditOperationError(f"新增内容块语义角色与声明不一致：{path}")
            return
        raise ResumeEditOperationError(f"内容块目标语义角色只能用于 content_blocks：{path}")

    block = _resolve(root, tokens[:content_blocks_index + 1], path=path)
    actual = block.get("semantic_role") if isinstance(block, dict) else None
    if actual not in CONTENT_BLOCK_SEMANTIC_ROLES:
        actual = "generic"
    if actual != requested:
        raise ResumeEditOperationError(
            f"内容块语义目标不匹配：{path}（当前为 {actual}，声明为 {requested}）"
        )


def _validate_operation_value(operation: dict) -> None:
    try:
        import json

        size = len(json.dumps(operation.get("value"), ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ResumeEditOperationError("修改值不是可保存的数据") from exc
    if size > MAX_OPERATION_VALUE_BYTES:
        raise ResumeEditOperationError("单项修改内容过大，无法安全生成预览")


def _apply_one(root: Any, operation: dict, *, roots: set[str], field_name: str, layout: bool) -> None:
    op = str(operation.get("op", operation.get("type", "")) or "").strip().lower()
    if op not in {"set", "replace", "append", "insert", "remove", "move"}:
        raise ResumeEditOperationError(f"{field_name} 操作类型无效")
    path_value = operation.get("path")
    tokens = _parse_path(path_value, roots=roots, field_name=field_name)
    path = str(path_value)
    if layout and any(
        isinstance(token, str) and token.lower() in _FORBIDDEN_LAYOUT_PARTS
        for token in tokens
    ):
        raise ResumeEditOperationError("字号和字体由专用排版设置管理，不能通过对话修改")
    if not layout:
        _validate_semantic_target(root, tokens, operation, path=path)
        try:
            validate_resume_operation_path(tokens, operation=op, path=path)
        except ValueError as exc:
            raise ResumeEditOperationError(str(exc)) from exc

    if op in {"set", "replace"}:
        if "value" not in operation:
            raise ResumeEditOperationError(f"{field_name} 缺少修改值")
        if not layout:
            try:
                current = _resolve(root, tokens, path=path)
                validate_resume_operation_value(
                    current, operation.get("value"), tokens, path=path,
                )
            except (ResumeEditOperationError, ValueError) as exc:
                raise ResumeEditOperationError(str(exc)) from exc
        if len(tokens) == 1 and layout:
            raise ResumeEditOperationError(f"不能整体覆盖排版根配置：{path}")
        parent, final = _resolve_parent(root, tokens, path=path)
        if isinstance(final, int):
            if not isinstance(parent, list) or final >= len(parent):
                raise ResumeEditOperationError(f"目标路径不存在：{path}")
            current = parent[final]
            _check_expected(current, operation, path=path)
            _validate_operation_value(operation)
            parent[final] = deepcopy(operation["value"])
        else:
            if not isinstance(parent, dict) or final not in parent:
                raise ResumeEditOperationError(f"目标路径不存在：{path}")
            current = parent[final]
            _check_expected(current, operation, path=path)
            _validate_operation_value(operation)
            parent[final] = deepcopy(operation["value"])
        return

    if op in {"append", "insert"}:
        if "value" not in operation:
            raise ResumeEditOperationError(f"{field_name} 缺少新增值")
        if not layout:
            try:
                validate_resume_operation_item(
                    operation.get("value"), tokens, path=f"{path}[]",
                )
            except ValueError as exc:
                raise ResumeEditOperationError(str(exc)) from exc
        target = _resolve(root, tokens, path=path)
        if not isinstance(target, list):
            raise ResumeEditOperationError(f"目标不是列表：{path}")
        _validate_operation_value(operation)
        if op == "append":
            target.append(deepcopy(operation["value"]))
        else:
            index = operation.get("index")
            if not isinstance(index, int) or index < 0 or index > len(target):
                raise ResumeEditOperationError(f"插入位置无效：{path}")
            target.insert(index, deepcopy(operation["value"]))
        return

    if op == "remove":
        if "index" in operation:
            target = _resolve(root, tokens, path=path)
            if not isinstance(target, list):
                raise ResumeEditOperationError(f"目标不是列表：{path}")
            index = operation["index"]
            if not isinstance(index, int) or index < 0 or index >= len(target):
                raise ResumeEditOperationError(f"删除位置无效：{path}")
            _check_expected(target[index], operation, path=f"{path}[{index}]")
            target.pop(index)
        else:
            parent, final = _resolve_parent(root, tokens, path=path)
            if isinstance(final, int):
                if not isinstance(parent, list) or final < 0 or final >= len(parent):
                    raise ResumeEditOperationError(f"目标路径不存在：{path}")
                _check_expected(parent[final], operation, path=path)
                parent.pop(final)
            else:
                if not isinstance(parent, dict) or final not in parent:
                    raise ResumeEditOperationError(f"目标路径不存在：{path}")
                _check_expected(parent[final], operation, path=path)
                del parent[final]
        return

    target = _resolve(root, tokens, path=path)
    if not isinstance(target, list):
        raise ResumeEditOperationError(f"目标不是列表：{path}")
    from_index = operation.get("from_index")
    to_index = operation.get("to_index")
    if (
        not isinstance(from_index, int)
        or not isinstance(to_index, int)
        or from_index < 0
        or from_index >= len(target)
        or to_index < 0
        or to_index >= len(target)
    ):
        raise ResumeEditOperationError(f"移动位置无效：{path}")
    _check_expected(target[from_index], operation, path=f"{path}[{from_index}]")
    item = target.pop(from_index)
    target.insert(to_index, item)


def _apply_operations(
    root: dict,
    operations: tuple[dict, ...],
    *,
    roots: set[str],
    field_name: str,
    layout: bool = False,
) -> dict:
    result = deepcopy(root)
    for operation in operations:
        _apply_one(result, operation, roots=roots, field_name=field_name, layout=layout)
    return result


async def run_resume_edit(
    request: ResumeEditRequest,
) -> ResumeEditResult:
    """Apply resolved operations and return a normalized candidate.

    This function never performs a model call or interprets natural-language
    instructions; callers must provide structured operation lists.
    """
    resume_operations = _coerce_operations(request.resume_operations, field_name="resume_operations")
    layout_operations = _coerce_operations(request.layout_operations, field_name="layout_operations")
    if not resume_operations and not layout_operations:
        raise ResumeEditOperationError("未收到可执行的结构化修改操作")

    current_resume = validate_resume_data(request.resume_data or {})
    current_layout = normalize_layout_config(request.layout_config or {})
    if request.base_version and not resume_state_version_matches(
        request.base_version,
        current_resume,
        current_layout,
        check_content=bool(resume_operations),
        check_layout=bool(layout_operations),
    ):
        raise ResumeEditOperationError("简历在生成预览前已发生变化，请重新生成修改建议")

    # The generic path applicator only knows whether a key exists.  Validate
    # the semantic layout capability separately so a model cannot request a
    # normalized-but-uneditable field (for example component coordinates,
    # per-module line heights, or arbitrary typography values).
    try:
        validate_layout_operations(layout_operations, current_layout)
    except ValueError as exc:
        raise ResumeEditOperationError(str(exc)) from exc

    candidate_resume = _apply_operations(
        current_resume,
        resume_operations,
        roots=_RESUME_ROOTS,
        field_name="resume_operations",
    )
    candidate_layout = _apply_operations(
        current_layout,
        layout_operations,
        roots=_LAYOUT_ROOTS,
        field_name="layout_operations",
        layout=True,
    )

    normalized_candidate_resume = validate_resume_data(candidate_resume)
    normalized_candidate_layout = normalize_layout_config(candidate_layout)
    return ResumeEditResult(
        resume_data=normalized_candidate_resume,
        layout_config=normalized_candidate_layout,
        base_version=request.base_version or build_resume_state_version(current_resume, current_layout),
        resume_operations=resume_operations,
        layout_operations=layout_operations,
        already_satisfied=(
            normalized_candidate_resume == current_resume
            and normalized_candidate_layout == current_layout
        ),
    )


async def run(
    arguments: ResumeEditToolInput,
    context: ResumeEditRuntimeContext,
) -> ResumeEditOutput:
    """Agent Skill entrypoint using model arguments plus trusted runtime context."""
    result = await run_resume_edit(
        ResumeEditRequest(
            resume_data=context.resume_data,
            layout_config=context.layout_config,
            resume_operations=tuple(arguments.resume_operations),
            layout_operations=tuple(arguments.layout_operations),
            jd_data=context.jd_data,
            context_type=context.context_type,
            base_version=context.base_version,
            conversation_context=context.conversation_context,
        )
    )
    return ResumeEditOutput(
        resume_data=result.resume_data,
        layout_config=result.layout_config,
        base_version=result.base_version,
        resume_operations=result.resume_operations,
        layout_operations=result.layout_operations,
        already_satisfied=result.already_satisfied,
    )


TOOL_INPUT_MODEL = ResumeEditToolInput
RUNTIME_CONTEXT_MODEL = ResumeEditRuntimeContext
OUTPUT_MODEL = ResumeEditOutput


def export_schemas() -> dict[str, dict]:
    return {
        "tool-input.schema.json": TOOL_INPUT_MODEL.model_json_schema(),
        "runtime-context.schema.json": RUNTIME_CONTEXT_MODEL.model_json_schema(),
        "output.schema.json": OUTPUT_MODEL.model_json_schema(),
    }


__all__ = [
    "ResumeEditOperationError",
    "ResumeEditRequest",
    "ResumeEditResult",
    "run_resume_edit",
]
