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

from ..layout_config import normalize_layout_config
from ..resume_changes import resume_digest
from ..resume_data import normalize_resume_data


MAX_OPERATIONS = 100
MAX_OPERATION_VALUE_BYTES = 256 * 1024
MAX_PATH_DEPTH = 32

_PATH_SEGMENT_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<indexes>(?:\[\d+\])*)$")
_INDEX_RE = re.compile(r"\[(\d+)\]")

_RESUME_ROOTS = {
    "basics",
    "education",
    "education_supplement",
    "research_interests",
    "honors",
    "publications",
    "work_experience",
    "internship_experience",
    "project_experience",
    "custom_sections",
    "others",
    "self_evaluation",
}
_LAYOUT_ROOTS = {
    "global",
    "basics",
    "education",
    "skills",
    "research_interests",
    "honors",
    "publications",
    "work_experience",
    "internship_experience",
    "project_experience",
    "custom_sections",
    "others",
    "self_evaluation",
}
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
    """Canonical data plus operations resolved by the conversation model.

    ``request_text`` and ``target_paths`` remain optional compatibility fields
    for older callers, but raw natural-language requests are intentionally not
    executable.  A caller must provide at least one operation list.
    """

    request_text: str = ""
    resume_data: dict = field(default_factory=dict)
    layout_config: dict = field(default_factory=dict)
    resume_operations: tuple[dict, ...] = ()
    layout_operations: tuple[dict, ...] = ()
    jd_data: dict = field(default_factory=dict)
    context_type: str = "main"
    target_paths: tuple[str, ...] = ()
    base_revision: str = ""
    conversation_context: str = ""


@dataclass(frozen=True)
class ResumeEditResult:
    resume_data: dict
    layout_config: dict
    target_paths: tuple[str, ...]
    base_revision: str
    resume_operations: tuple[dict, ...] = ()
    layout_operations: tuple[dict, ...] = ()


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

    if op in {"set", "replace"}:
        if "value" not in operation:
            raise ResumeEditOperationError(f"{field_name} 缺少修改值")
        if len(tokens) == 1:
            raise ResumeEditOperationError(f"不能整体覆盖简历根栏目：{path}")
        parent, final = _resolve_parent(root, tokens, path=path)
        if isinstance(final, int):
            if not isinstance(parent, list) or final >= len(parent):
                raise ResumeEditOperationError(f"目标路径不存在：{path}")
            current = parent[final]
            _check_expected(current, operation, path=path)
            parent[final] = deepcopy(operation["value"])
        else:
            if not isinstance(parent, dict) or final not in parent:
                raise ResumeEditOperationError(f"目标路径不存在：{path}")
            current = parent[final]
            _check_expected(current, operation, path=path)
            parent[final] = deepcopy(operation["value"])
        _validate_operation_value(operation)
        return

    if op in {"append", "insert"}:
        if "value" not in operation:
            raise ResumeEditOperationError(f"{field_name} 缺少新增值")
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
    llm: Any | None = None,
    **_legacy_kwargs: Any,
) -> ResumeEditResult:
    """Apply resolved operations and return a normalized candidate.

    ``llm`` and legacy keyword arguments are accepted only so older callers do
    not fail at import time; they are deliberately ignored.  This function
    never performs a model call or interprets natural-language instructions.
    """
    resume_operations = _coerce_operations(request.resume_operations, field_name="resume_operations")
    layout_operations = _coerce_operations(request.layout_operations, field_name="layout_operations")
    if not resume_operations and not layout_operations:
        if str(request.request_text or "").strip():
            raise ResumeEditOperationError("未收到结构化修改操作，不能把自然语言直接交给修改技能")
        raise ResumeEditOperationError("未收到可执行的结构化修改操作")

    current_resume = normalize_resume_data(request.resume_data or {})
    current_layout = normalize_layout_config(request.layout_config or {})
    if request.base_revision and request.base_revision != resume_digest(current_resume):
        raise ResumeEditOperationError("简历在生成预览前已发生变化，请重新生成修改建议")

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

    return ResumeEditResult(
        resume_data=normalize_resume_data(candidate_resume),
        layout_config=normalize_layout_config(candidate_layout),
        target_paths=tuple(request.target_paths or ()),
        base_revision=request.base_revision,
        resume_operations=resume_operations,
        layout_operations=layout_operations,
    )


__all__ = [
    "ResumeEditOperationError",
    "ResumeEditRequest",
    "ResumeEditResult",
    "run_resume_edit",
]
