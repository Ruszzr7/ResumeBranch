"""Canonical contracts for structured resume content.

This module is deliberately renderer-agnostic.  Import, editing, agent
validation, and export code all use the same small vocabulary for experience
content blocks, so a value received from an older parser cannot silently turn
into a different visual structure in another layer.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, Field


CONTENT_BLOCK_TYPES = ("paragraph", "numbered_list", "bullet_list")
CONTENT_BLOCK_SEMANTIC_ROLES = ("tech_stack", "introduction", "responsibilities", "generic")
CONTENT_BLOCK_TYPE_LABELS = {
    "paragraph": "段落",
    "bullet_list": "分点",
    "numbered_list": "编号",
}
CONTENT_BLOCK_ROLE_LABELS = {
    "tech_stack": "技术栈",
    "introduction": "项目简介",
    "responsibilities": "项目职责",
    "generic": "普通内容",
}
DEFAULT_CONTENT_BLOCK_TYPES = {
    "tech_stack": "paragraph",
    "introduction": "paragraph",
    "responsibilities": "numbered_list",
    "generic": "bullet_list",
}
class ProjectContentBlock(BaseModel):
    """A semantic block used by work and project experiences."""

    type: Literal["paragraph", "numbered_list", "bullet_list"] = Field(
        default="paragraph", description="段落、编号列表或普通分点列表"
    )
    semantic_role: Literal["tech_stack", "introduction", "responsibilities", "generic"] | None = Field(
        default=None, description="稳定语义角色；旧数据缺省时由类型和标签兼容推断"
    )
    label: str = Field(default="", description="例如技术栈、项目简介、项目职责")
    label_bold: bool = Field(default=True, description="语义标签是否加粗")
    text: str = Field(default="", description="paragraph 类型的正文")
    items: list[str] = Field(default_factory=list, description="列表类型的逐条内容，不包含序号")
    # These fields are parser-only evidence.  normalize_content_block consumes
    # them and never persists or renders them, but the extraction model needs a
    # way to describe where the source document's visual group changes.
    source_layout_group: str = Field(
        default="",
        description="仅供解析阶段使用的连续视觉组标识；不要写入最终简历数据",
    )
    source_indent_level: int | None = Field(
        default=None,
        description="仅供解析阶段使用的相对缩进层级；无法确认时留空",
    )
    source_marker_type: Literal["paragraph", "bullet", "numbered", ""] = Field(
        default="",
        description="仅供解析阶段使用的原始段落/分点/编号形式；不要写入最终简历数据",
    )


_TYPE_ALIASES = {
    "paragraph": "paragraph",
    "paragraphs": "paragraph",
    "text": "paragraph",
    "段落": "paragraph",
    "分段": "paragraph",
    "bullet": "bullet_list",
    "bullets": "bullet_list",
    "bullet_list": "bullet_list",
    "unordered_list": "bullet_list",
    "list": "bullet_list",
    "分点": "bullet_list",
    "编号": "numbered_list",
    "numbered": "numbered_list",
    "numbered_list": "numbered_list",
    "ordered_list": "numbered_list",
    "numbers": "numbered_list",
}
_ROLE_ALIASES = {
    "tech_stack": "tech_stack",
    "technology_stack": "tech_stack",
    "technology": "tech_stack",
    "技术栈": "tech_stack",
    "技术选型": "tech_stack",
    "使用技术": "tech_stack",
    "技术工具": "tech_stack",
    "introduction": "introduction",
    "intro": "introduction",
    "项目简介": "introduction",
    "项目背景": "introduction",
    "项目概述": "introduction",
    "responsibilities": "responsibilities",
    "responsibility": "responsibilities",
    "duty": "responsibilities",
    "duties": "responsibilities",
    "主要职责": "responsibilities",
    "项目职责": "responsibilities",
    "generic": "generic",
    "other": "generic",
    "普通内容": "generic",
    "普通工作内容": "generic",
    "其他项目内容": "generic",
    "其他工作内容": "generic",
    "普通项目内容": "generic",
}
_LEADING_NUMBER_RE = re.compile(r"^\s*[（(]?\s*\d{1,2}\s*[）).、．]\s*")
_LEADING_BULLET_RE = re.compile(r"^\s*(?:[•·▪‣●○◦]\s*|-\s+)")
_INTRO_RE = re.compile(r"^(项目简介|项目背景|项目概述|项目说明)\s*[：:]\s*(.*)$")
_DUTY_RE = re.compile(r"^(项目职责|主要职责|个人职责|负责内容)\s*[：:]?\s*(.*)$")
_TECH_STACK_RE = re.compile(r"^(技术栈|技术选型|使用技术|技术工具)\s*[：:]?\s*(.*)$")
_BOLD_HEADING_RE = re.compile(r"^\*\*(技术栈|技术选型|使用技术|技术工具|项目简介|项目背景|项目概述|项目说明|项目职责|主要职责|个人职责|负责内容)\*\*\s*[：:]?\s*(.*)$")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalize_heading_surface(value: Any) -> tuple[str, bool]:
    """Remove only heading-level bold wrappers before semantic matching."""
    text = _text(value)
    if not text:
        return "", False
    whole_bold = (
        text.startswith("**") and text.endswith("**") and len(text) >= 4
        and text.count("**") == 2
    )
    if whole_bold:
        text = text[2:-2].strip()
    text = re.sub(
        r"^\*\*(技术栈|技术选型|使用技术|技术工具|项目简介|项目背景|项目概述|项目说明|项目职责|主要职责|个人职责|负责内容)\*\*",
        r"\1",
        text,
    )
    return text, whole_bold


def _semantic_heading_match(value: Any) -> tuple[str, str, str, bool] | None:
    """Return role, label, body and whether the whole source line was bold."""
    normalized, whole_bold = _normalize_heading_surface(value)
    intro_match = _INTRO_RE.match(normalized)
    if intro_match:
        return "introduction", intro_match.group(1), intro_match.group(2).strip(), whole_bold
    duty_match = _DUTY_RE.match(normalized)
    if duty_match:
        return "responsibilities", duty_match.group(1), duty_match.group(2).strip(), whole_bold
    tech_stack_match = _TECH_STACK_RE.match(normalized)
    if tech_stack_match:
        return "tech_stack", tech_stack_match.group(1), tech_stack_match.group(2).strip(), whole_bold
    bold_match = _BOLD_HEADING_RE.match(_text(value))
    if bold_match:
        label = bold_match.group(1)
        if label in {"技术栈", "技术选型", "使用技术", "技术工具"}:
            role = "tech_stack"
        else:
            role = "introduction" if label in {"项目简介", "项目背景", "项目概述", "项目说明"} else "responsibilities"
        return role, label, bold_match.group(2).strip(), True
    return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            text = _text(item.get("text") or item.get("content") or item.get("value"))
        else:
            text = _text(item)
        if text and text not in result:
            result.append(text)
    return result


def _bool_value(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "0", "no", "off", "否", "不"}:
            return False
        if normalized in {"true", "1", "yes", "on", "是", "加粗"}:
            return True
    return bool(value)


def _source_visual_signature(raw: Any) -> tuple[str, int | None, str]:
    """Read parser-only visual evidence without exposing it to renderers.

    The parser may use either the canonical ``source_*`` names or the shorter
    aliases while producing JSON.  The normalized persisted block deliberately
    omits all of these fields; they are only used to decide whether a block is
    a continuation of the responsibility group after an introduction.
    """
    if not isinstance(raw, Mapping):
        return "", None, ""
    group = _text(
        raw.get("source_layout_group")
        or raw.get("source_visual_group")
        or raw.get("visual_group")
    )
    indent_value = raw.get("source_indent_level")
    if indent_value is None:
        indent_value = raw.get("visual_indent_level")
    try:
        indent = int(indent_value) if indent_value is not None and str(indent_value).strip() else None
    except (TypeError, ValueError):
        indent = None
    marker = _text(raw.get("source_marker_type") or raw.get("visual_marker_type")).lower()
    marker = {
        "paragraph": "paragraph",
        "段落": "paragraph",
        "text": "paragraph",
        "bullet": "bullet",
        "bullet_list": "bullet",
        "分点": "bullet",
        "numbered": "numbered",
        "numbered_list": "numbered",
        "编号": "numbered",
    }.get(marker, "")
    return group, indent, marker


def _visual_group_key(signature: tuple[str, int | None, str]) -> tuple[Any, ...] | None:
    """Return a comparable visual-group key, or ``None`` when unavailable."""
    group, indent, marker = signature
    if group:
        return ("group", group)
    if indent is not None or marker:
        return ("shape", indent, marker)
    return None


def canonical_content_block_type(value: Any) -> str:
    return _TYPE_ALIASES.get(_text(value).lower(), "")


def canonical_content_block_role(value: Any) -> str:
    return _ROLE_ALIASES.get(_text(value).lower(), "")


def default_content_block_type(semantic_role: str) -> str:
    return DEFAULT_CONTENT_BLOCK_TYPES.get(semantic_role, "bullet_list")


def strip_content_marker(value: Any) -> str:
    """Remove a stored list marker while preserving the actual wording."""
    text = _text(value)
    text = _LEADING_NUMBER_RE.sub("", text)
    return _LEADING_BULLET_RE.sub("", text).strip()


def _generic_label_prefix(label: str, label_bold: bool) -> str:
    rendered = label.strip()
    if not rendered:
        return ""
    if label_bold and not (rendered.startswith("**") and rendered.endswith("**")):
        rendered = f"**{rendered}**"
    separator = "" if rendered.endswith((":", "：")) else "："
    return f"{rendered}{separator}"


def _flatten_generic_label(
    label: str,
    label_bold: bool,
    text: str,
    items: list[str],
) -> tuple[str, list[str]]:
    """Keep an unexpected generic label as an inline prefix, never a block title."""
    prefix = _generic_label_prefix(label, label_bold)
    if not prefix:
        return text, items
    if items:
        return text, [f"{prefix}{items[0]}", *items[1:]]
    if text:
        return f"{prefix}{text}", items
    return "", [prefix.rstrip(":：")]


def normalize_content_block(raw: Any, *, keep_empty: bool = False) -> dict[str, Any] | None:
    """Normalize one explicit block to the canonical six-field shape.

    ``keep_empty`` is used by layout-flow helpers, which still need to decide
    whether an empty semantic label should be hidden.  Persistence and import
    use the default and discard completely empty blocks.
    """
    if not isinstance(raw, Mapping):
        return None

    block_type = canonical_content_block_type(raw.get("type"))

    label = _text(raw.get("label"))
    label_wrapped_bold = label.startswith("**") and label.endswith("**") and len(label) >= 4
    if label_wrapped_bold:
        label = label[2:-2].strip()
    semantic_role = canonical_content_block_role(raw.get("semantic_role"))
    label_role = canonical_content_block_role(label)
    if semantic_role == "generic" and label_role in {"introduction", "responsibilities"}:
        semantic_role = label_role
    if not semantic_role:
        # Unknown labels are not semantic evidence.  They are usually bold
        # prefixes inside a list item, so keep the block generic and flatten
        # the label into the first content value below.
        semantic_role = label_role or "generic"
    if not block_type:
        block_type = default_content_block_type(semantic_role)
    text = _text(raw.get("text"))
    items = [strip_content_marker(item) for item in _string_list(raw.get("items"))]
    items = [item for item in items if item]
    label_bold = _bool_value(raw.get("label_bold"), True) or label_wrapped_bold
    if semantic_role == "generic":
        if label_role == "generic":
            label = ""
        elif label:
            text, items = _flatten_generic_label(label, label_bold, text, items)
            label = ""
    result = {
        "type": block_type,
        "semantic_role": semantic_role,
        "label": label,
        "label_bold": label_bold,
        "text": text,
        "items": items,
    }
    if not keep_empty and not text and not items:
        return None
    return result


def _is_heading(text: str) -> bool:
    return _semantic_heading_match(text) is not None


def _clean_legacy_items(values: list[str]) -> list[str]:
    return [clean for clean in (strip_content_marker(value) for value in values) if clean]


def _legacy_list_type(values: list[str]) -> str:
    markers = [_LEADING_NUMBER_RE.match(_text(value)) for value in values if _text(value)]
    if markers and len(markers) == len([value for value in values if _text(value)]):
        return "numbered_list"
    bullets = [_LEADING_BULLET_RE.match(_text(value)) for value in values if _text(value)]
    if bullets and len(bullets) == len([value for value in values if _text(value)]):
        return "bullet_list"
    # A semantic responsibility block without visible markers uses the
    # product's existing default, numbered responsibilities.
    return "numbered_list"


def _legacy_semantic_blocks(details: list[str]) -> list[dict[str, Any]]:
    """Migrate legacy details while keeping explicit section boundaries.

    This path only serves pre-content-block data.  New imports are expected to
    provide explicit semantic blocks after the model has performed visual
    grouping and semantic classification; already structured generic blocks
    are never reclassified here.
    """
    blocks: list[dict[str, Any]] = []
    unmatched: list[str] = []

    def flush_unmatched() -> None:
        if unmatched:
            blocks.append({
                "type": "bullet_list", "semantic_role": "generic", "label": "", "label_bold": True,
                "text": "", "items": _clean_legacy_items(unmatched),
            })
            unmatched.clear()

    index = 0
    while index < len(details):
        value = _text(details[index])
        heading = _semantic_heading_match(value)
        if heading and heading[0] == "tech_stack":
            flush_unmatched()
            _, label, body, whole_bold = heading
            index += 1
            following = [f"**{body}**" if whole_bold and body else body] if body else []
            while index < len(details) and not _is_heading(_text(details[index])):
                following.append(details[index])
                index += 1
            values = [value for value in following if _text(value)]
            if values:
                blocks.append({
                    "type": "paragraph", "semantic_role": "tech_stack", "label": label,
                    "label_bold": True, "text": "\n".join(values), "items": [],
                })
            continue
        if heading and heading[0] == "introduction":
            flush_unmatched()
            _, label, body, whole_bold = heading
            if whole_bold and body:
                body = f"**{body}**"
            if body:
                blocks.append({
                    "type": "paragraph", "semantic_role": "introduction", "label": label,
                    "label_bold": True, "text": body, "items": [],
                })
            index += 1
            following: list[str] = []
            while index < len(details) and not _is_heading(_text(details[index])):
                following.append(details[index])
                index += 1
            items = _clean_legacy_items(following)
            if items:
                blocks.append({
                    "type": _legacy_list_type(following), "semantic_role": "responsibilities",
                    "label": "项目职责", "label_bold": True, "text": "", "items": items,
                })
            continue

        if heading and heading[0] == "responsibilities":
            flush_unmatched()
            _, label, body, whole_bold = heading
            index += 1
            following = [f"**{body}**" if whole_bold and body else body] if body else []
            while index < len(details) and not _is_heading(_text(details[index])):
                following.append(details[index])
                index += 1
            items = _clean_legacy_items(following)
            if items:
                blocks.append({
                    "type": _legacy_list_type(following), "semantic_role": "responsibilities",
                    "label": label, "label_bold": True, "text": "", "items": items,
                })
            continue

        unmatched.append(value)
        index += 1

    flush_unmatched()
    return [block for block in blocks if block.get("text") or block.get("items")]


def _order_project_content_blocks(
    blocks: list[dict[str, Any]],
    *,
    experience_kind: str,
) -> list[dict[str, Any]]:
    """Apply the fixed semantic order when a project has technical-stack content.

    The editor exposes a fixed project order rather than a generic drag-and-
    drop operation.  Projects without the new role are returned untouched so
    existing resume ordering remains backward-compatible.  Once a project
    explicitly contains technical-stack content, all four semantic roles use
    the canonical order.
    """
    if experience_kind != "project":
        return blocks
    if not any(block.get("semantic_role") == "tech_stack" for block in blocks):
        return blocks
    role_order = {"tech_stack": 0, "introduction": 1, "responsibilities": 2, "generic": 3}
    return [
        block for _, block in sorted(
            enumerate(blocks),
            key=lambda pair: (role_order.get(pair[1].get("semantic_role"), 3), pair[0]),
        )
    ]


def normalize_content_blocks(
    value: Any,
    legacy_details: Any = None,
    *,
    experience_kind: str = "project",
) -> list[dict[str, Any]]:
    """Normalize explicit blocks and migrate the supported legacy shape."""
    entries: list[tuple[Any, dict[str, Any], tuple[str, int | None, str]]] = []
    if isinstance(value, list):
        for raw in value:
            block = normalize_content_block(raw)
            if block is not None:
                entries.append((raw, block, _source_visual_signature(raw)))

    # A parser may omit semantic_role for content that visually continues an
    # explicit introduction.  The introduction's own body remains an
    # introduction; only blocks after that body enter the responsibility
    # candidate window.  The first visual group in that window is the default
    # responsibility group.  A later, clearly different visual group becomes
    # generic.  With no visual evidence we stay conservative and keep the
    # continuation in responsibilities instead of risking data loss.
    result: list[dict[str, Any]] = []
    active_semantic_group: str | None = None
    responsibility_visual_key: tuple[Any, ...] | None = None

    def as_responsibilities(
        block: dict[str, Any],
    ) -> dict[str, Any]:
        items = list(block["items"])
        if not items and block["text"]:
            items = [block["text"]]
        return {
            **block,
            "type": "numbered_list",
            "semantic_role": "responsibilities",
            "label": "项目职责",
            "label_bold": True,
            "text": "",
            "items": items,
        }

    def append_responsibilities(block: dict[str, Any]) -> None:
        if (
            result
            and result[-1]["semantic_role"] == "responsibilities"
            and result[-1]["label"] == "项目职责"
            and result[-1]["type"] == block["type"]
        ):
            items = list(block["items"])
            if not items and block["text"]:
                items = [block["text"]]
            if result[-1]["type"] == "paragraph":
                result[-1]["text"] = "\n".join(
                    value for value in [result[-1]["text"], *items] if value
                )
            else:
                result[-1]["items"].extend(items)
        else:
            result.append(block)

    for raw, block, visual_signature in entries:
        has_explicit_semantic_role = (
            isinstance(raw, Mapping) and bool(_text(raw.get("semantic_role")))
        )
        if block["semantic_role"] == "tech_stack":
            # Project technical stack is a fixed semantic block. It is kept
            # outside the responsibility continuation window and moved ahead
            # of the introduction by the final project ordering step.
            result.append(block)
            active_semantic_group = None
            responsibility_visual_key = None
            continue
        if block["semantic_role"] == "introduction":
            result.append(block)
            active_semantic_group = "introduction" if block["label"] else None
            responsibility_visual_key = None
            continue
        elif block["semantic_role"] == "responsibilities":
            # An explicit block comes from the editor/parser contract. Its
            # selected paragraph, bullet, or numbered form is authoritative.
            append_responsibilities(block)
            active_semantic_group = "responsibilities" if block["label"] else None
            responsibility_visual_key = _visual_group_key(visual_signature)
            continue
        elif has_explicit_semantic_role:
            # Explicit generic content marks a real boundary. Do not fold it
            # into the preceding responsibility group when visual evidence is
            # unavailable (which is normal for editor-authored data).
            result.append(block)
            active_semantic_group = None
            responsibility_visual_key = None
            continue

        if active_semantic_group in {"introduction", "responsibilities"}:
            visual_key = _visual_group_key(visual_signature)
            if responsibility_visual_key is None and visual_key is not None:
                responsibility_visual_key = visual_key

            # A block is generic after an introduction/responsibility only
            # when the parser supplied clear visual evidence that it belongs
            # to a different group.  Missing evidence, unlabeled blocks, and
            # conflicting semantic guesses all default to responsibilities.
            is_distinct_visual_group = (
                responsibility_visual_key is not None
                and visual_key is not None
                and visual_key != responsibility_visual_key
            )
            if not is_distinct_visual_group:
                append_responsibilities(as_responsibilities(block))
                continue

            result.append({
                **block,
                "type": "bullet_list" if block["type"] == "numbered_list" else block["type"],
                "semantic_role": "generic",
                "label": "",
            })
            continue

        # Without an explicit semantic heading there is no basis for inventing
        # a project-introduction or responsibility label.  The block remains
        # generic and retains its source form where one was explicitly given.
        result.append(block)
    legacy = _string_list(legacy_details)
    if result or not legacy:
        return _order_project_content_blocks(result, experience_kind=experience_kind)

    # Work descriptions historically had no semantic labels. Preserve that
    # legacy generic shape only when no explicit semantic heading exists;
    # an explicit project-introduction or responsibility heading always wins.
    if experience_kind == "work" and not any(_semantic_heading_match(item) for item in legacy):
        return _order_project_content_blocks([{
            "type": "bullet_list", "semantic_role": "generic", "label": "", "label_bold": True,
            "text": "", "items": legacy,
        }], experience_kind=experience_kind)
    return _order_project_content_blocks(_legacy_semantic_blocks(legacy), experience_kind=experience_kind)
