"""Safe, deterministic inline-bold helpers for resume text.

Resume content remains plain JSON strings. Only paired ``**text**`` markers
carry inline formatting; arbitrary HTML and other Markdown are never emitted.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from html import escape
import re
from typing import Any, Iterator


_BOLD_PAIR_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_QUOTED_TEXT_RE = re.compile(r"[“\"‘'](.+?)[”\"’']")


@dataclass(frozen=True)
class InlineSegment:
    text: str
    bold: bool = False


@dataclass(frozen=True)
class ResumeTextReference:
    path: tuple[str | int, ...]
    section: str
    context: str
    value: str
    base_bold: bool = False


class InlineFormatError(ValueError):
    """A user-facing error that must fail closed without an LLM fallback."""


def parse_inline_bold(value: object) -> list[InlineSegment]:
    """Parse paired strong markers while treating unmatched markers literally."""
    text = str(value or "")
    segments: list[InlineSegment] = []
    cursor = 0
    for match in _BOLD_PAIR_RE.finditer(text):
        if match.start() > cursor:
            segments.append(InlineSegment(text[cursor:match.start()], False))
        segments.append(InlineSegment(match.group(1), True))
        cursor = match.end()
    if cursor < len(text):
        segments.append(InlineSegment(text[cursor:], False))
    return _merge_segments(segments)


def plain_inline_text(value: object) -> str:
    return "".join(segment.text for segment in parse_inline_bold(value))


def is_fully_bold_inline(value: object) -> bool:
    """Return whether all visible text in a value is explicitly bold."""
    segments = [segment for segment in parse_inline_bold(str(value or "").strip()) if segment.text.strip()]
    return bool(segments) and all(segment.bold for segment in segments)


def join_inline_with_inherited_separator(values: list[object], separator: str) -> str:
    """Join fields; a connector is bold only when both adjacent fields are bold."""
    normalized = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not normalized:
        return ""
    segments: list[InlineSegment] = []
    for index, value in enumerate(normalized):
        if index:
            segments.append(
                InlineSegment(
                    separator,
                    bold=(
                        is_fully_bold_inline(normalized[index - 1])
                        and is_fully_bold_inline(value)
                    ),
                )
            )
        segments.extend(parse_inline_bold(value))
    # Do not concatenate adjacent ``**...**`` fragments.  That form is
    # ambiguous to the inline parser; serializing the combined segments keeps
    # the connector in the same bold run as its preceding field.
    return serialize_inline_bold(segments)


def join_inline_label_value(label: object, value: object, separator: str) -> str:
    """Join a label and value; the label separator follows the label only."""
    label_text = str(label or "").strip()
    value_text = str(value or "").strip()
    if not label_text:
        return value_text
    segments = parse_inline_bold(label_text)
    segments.append(InlineSegment(separator, bold=is_fully_bold_inline(label_text)))
    segments.extend(parse_inline_bold(value_text))
    return serialize_inline_bold(segments)


def format_inline_html(value: object) -> str:
    """Render the allowlisted bold protocol as escaped HTML."""
    rendered = []
    for segment in parse_inline_bold(value):
        content = escape(segment.text, quote=True)
        rendered.append(f"<strong>{content}</strong>" if segment.bold else content)
    return "".join(rendered)


def set_inline_bold(value: object, quote: str, *, bold: bool) -> str:
    """Set one uniquely matched plain-text range to bold or normal."""
    segments = parse_inline_bold(value)
    plain = "".join(segment.text for segment in segments)
    target = plain_inline_text(quote)
    if not target:
        raise InlineFormatError("请用引号标出需要加粗或取消加粗的文字。")
    starts = _match_starts(plain, target)
    if not starts:
        raise InlineFormatError(f"当前简历中没有找到“{target}”。")
    if len(starts) > 1:
        raise InlineFormatError(f"同一段文字中找到 {len(starts)} 处“{target}”，请进一步说明具体位置。")
    start = starts[0]
    updated = _apply_bold_range(segments, start, start + len(target), bold)
    return serialize_inline_bold(updated)


def serialize_inline_bold(segments: list[InlineSegment]) -> str:
    rendered: list[str] = []
    for segment in _merge_segments(segments):
        if not segment.bold:
            rendered.append(segment.text)
            continue
        # 多行编辑字段最终会逐行保存；每行各自闭合，避免拆分后留下单侧标记。
        rendered.append("\n".join(f"**{line}**" if line else "" for line in segment.text.split("\n")))
    return "".join(rendered)


def format_resume_text(
    resume_data: dict,
    quote: str,
    *,
    bold: bool,
    request_text: str = "",
) -> tuple[dict, ResumeTextReference]:
    """Return a candidate with exactly one visible text occurrence formatted."""
    candidate = deepcopy(resume_data or {})
    target = plain_inline_text(quote).strip()
    if not target:
        raise InlineFormatError("请用引号标出需要加粗或取消加粗的文字。")
    references = [
        reference for reference in iter_resume_text_references(candidate, request_text)
        if target in plain_inline_text(reference.value)
    ]
    total_occurrences = sum(len(_match_starts(plain_inline_text(ref.value), target)) for ref in references)
    if total_occurrences == 0:
        raise InlineFormatError(f"当前指定范围内没有找到“{target}”，未生成任何修改。")
    if total_occurrences > 1:
        contexts = "、".join(dict.fromkeys(ref.context for ref in references))
        detail = f"，分别位于：{contexts}" if contexts else ""
        raise InlineFormatError(f"当前指定范围内找到 {total_occurrences} 处“{target}”{detail}。请补充公司、项目或条目位置。")
    reference = references[0]
    if reference.base_bold:
        if bold:
            raise InlineFormatError(f"“{target}”所在的标题或标签已由当前版式整体加粗，无需重复修改。")
        raise InlineFormatError(
            f"“{target}”所在的标题或标签由版式统一控制字重，不能只取消其中一部分的加粗；"
            "正文和元信息仍可逐字加粗或取消加粗。"
        )
    before = _get_path(candidate, reference.path)
    after = set_inline_bold(before, target, bold=bold)
    if after == before:
        state = "粗体" if bold else "普通字重"
        raise InlineFormatError(f"“{target}”已经是{state}，无需重复修改。")
    if plain_inline_text(before) != plain_inline_text(after):
        raise InlineFormatError("格式化校验失败：操作会改变原文字，系统已停止修改。")
    _set_path(candidate, reference.path, after)
    return candidate, reference


def iter_resume_text_references(data: dict, request_text: str = "") -> Iterator[ResumeTextReference]:
    """Yield allowlisted, user-visible free-text leaves, optionally scoped."""
    requested_sections = _requested_sections(request_text)
    legacy_default_bold = int(data.get("formatting_version") or 0) < 1

    def allowed(section: str) -> bool:
        return not requested_sections or section in requested_sections

    basics = data.get("basics") or {}
    if allowed("basics"):
        for key in ("name", "phone", "email", "target_position"):
            if basics.get(key):
                yield ResumeTextReference(
                    ("basics", key), "basics", f"基本信息·{key}", str(basics[key]),
                    base_bold=legacy_default_bold and key in {"name", "target_position"},
                )
        for index, field in enumerate(basics.get("additional_fields") or []):
            for key in ("label", "value"):
                if isinstance(field, dict) and field.get(key):
                    yield ResumeTextReference(("basics", "additional_fields", index, key), "basics", f"基本信息·补充信息{index + 1}", str(field[key]))

    if allowed("education"):
        for index, item in enumerate(data.get("education") or []):
            if not isinstance(item, dict):
                continue
            context = f"教育经历{index + 1}·{item.get('school_name') or '未命名学校'}"
            for key in ("school_name", "degree", "major", "gpa", "gpa_scale", "ranking"):
                if item.get(key):
                    yield ResumeTextReference(
                        ("education", index, key), "education", context, str(item[key]),
                        base_bold=legacy_default_bold and key == "school_name",
                    )
            for date_index, date_value in enumerate(item.get("date_range") or []):
                if date_value:
                    yield ResumeTextReference(
                        ("education", index, "date_range", date_index), "education", context, str(date_value)
                    )
            for tag_index, tag in enumerate(item.get("school_tags") or []):
                if tag:
                    yield ResumeTextReference(("education", index, "school_tags", tag_index), "education", context, str(tag))
            for thesis_index, thesis in enumerate(item.get("theses") or []):
                if not isinstance(thesis, dict):
                    continue
                if thesis.get("title"):
                    yield ResumeTextReference(
                        ("education", index, "theses", thesis_index, "title"),
                        "education", context, str(thesis["title"]), base_bold=legacy_default_bold,
                    )
                for detail_index, detail in enumerate(thesis.get("details") or []):
                    if detail:
                        yield ResumeTextReference(("education", index, "theses", thesis_index, "details", detail_index), "education", context, str(detail))

    for index, item in enumerate(data.get("work_experience") or []):
        if not isinstance(item, dict):
            continue
        is_internship = bool(re.search(r"实习|intern", f"{item.get('job_type', '')} {item.get('job_title', '')}", re.I))
        section = "internship_experience" if is_internship else "work_experience"
        if not allowed(section):
            continue
        context = f"{'实习' if is_internship else '工作'}经历{index + 1}·{item.get('company_name') or '未命名公司'}"
        for key in ("company_name", "job_title", "job_type"):
            if item.get(key):
                yield ResumeTextReference(
                    ("work_experience", index, key), section, context, str(item[key]),
                    base_bold=legacy_default_bold and key == "company_name",
                )
        for date_index, date_value in enumerate(item.get("date_range") or []):
            if date_value:
                yield ResumeTextReference(
                    ("work_experience", index, "date_range", date_index), section, context, str(date_value)
                )
        yield from _content_block_references(item, ("work_experience", index), section, context)

    if allowed("project_experience"):
        for index, item in enumerate(data.get("project_experience") or []):
            if not isinstance(item, dict):
                continue
            context = f"项目经历{index + 1}·{item.get('project_name') or '未命名项目'}"
            for key in ("project_name", "role"):
                if item.get(key):
                    yield ResumeTextReference(
                        ("project_experience", index, key), "project_experience", context, str(item[key]),
                        base_bold=legacy_default_bold and key == "project_name",
                    )
            for date_index, date_value in enumerate(item.get("date_range") or []):
                if date_value:
                    yield ResumeTextReference(
                        ("project_experience", index, "date_range", date_index), "project_experience", context, str(date_value)
                    )
            yield from _content_block_references(item, ("project_experience", index), "project_experience", context)

    list_sections = (
        ("research_interests", "research_interests", "研究方向"),
        ("honors", "honors", "主要荣誉"),
        ("self_evaluation", "self_evaluation", "自我评价"),
        ("education_supplement", "education", "教育经历补充"),
    )
    for key, section, label in list_sections:
        if not allowed(section):
            continue
        for index, value in enumerate(data.get(key) or []):
            if value:
                yield ResumeTextReference((key, index), section, f"{label}{index + 1}", str(value))

    others = data.get("others") or {}
    for key, section, label in (
        ("skills", "skills", "专业技能"),
        ("certificates", "others", "证书"),
        ("languages", "others", "语言"),
    ):
        if not allowed(section):
            continue
        for index, value in enumerate(others.get(key) or []):
            if value:
                yield ResumeTextReference(("others", key, index), section, f"{label}{index + 1}", str(value))

    if allowed("custom_sections"):
        for section_index, section in enumerate(data.get("custom_sections") or []):
            if not isinstance(section, dict):
                continue
            context = f"自定义栏目·{section.get('title') or section_index + 1}"
            if section.get("title"):
                yield ResumeTextReference(
                    ("custom_sections", section_index, "title"),
                    "custom_sections", context, str(section["title"]), base_bold=legacy_default_bold,
                )
            for item_index, value in enumerate(section.get("items") or []):
                if value:
                    yield ResumeTextReference(("custom_sections", section_index, "items", item_index), "custom_sections", context, str(value))


def _content_block_references(item: dict, prefix: tuple, section: str, context: str) -> Iterator[ResumeTextReference]:
    for block_index, block in enumerate(item.get("content_blocks") or []):
        if not isinstance(block, dict):
            continue
        if block.get("label"):
            yield ResumeTextReference(
                prefix + ("content_blocks", block_index, "label"),
                section,
                context,
                str(block["label"]),
                base_bold=bool(block.get("label_bold", True)),
            )
        if block.get("text"):
            yield ResumeTextReference(prefix + ("content_blocks", block_index, "text"), section, context, str(block["text"]))
        for item_index, value in enumerate(block.get("items") or []):
            if value:
                yield ResumeTextReference(prefix + ("content_blocks", block_index, "items", item_index), section, context, str(value))


def _requested_sections(text: str) -> set[str]:
    # Section words inside the quoted target are content, not scope. For
    # example, “项目性能提升” in an internship bullet must not also select the
    # project section.
    value = _QUOTED_TEXT_RE.sub("", str(text or ""))
    matches: set[str] = set()
    mapping = (
        (r"基本信息|姓名|联系方式|目标岗位", "basics"),
        (r"教育经历|教育背景|学校|学历", "education"),
        (r"实习经历", "internship_experience"),
        (r"工作经历", "work_experience"),
        (r"项目经历|项目", "project_experience"),
        (r"专业技能|技能", "skills"),
        (r"研究方向|研究兴趣", "research_interests"),
        (r"荣誉|奖项", "honors"),
        (r"证书|语言", "others"),
        (r"自定义栏目", "custom_sections"),
        (r"自我评价|个人总结", "self_evaluation"),
    )
    for pattern, section in mapping:
        if re.search(pattern, value, re.I):
            matches.add(section)
    return matches


def _apply_bold_range(segments: list[InlineSegment], start: int, end: int, bold: bool) -> list[InlineSegment]:
    result: list[InlineSegment] = []
    cursor = 0
    for segment in segments:
        segment_start = cursor
        segment_end = cursor + len(segment.text)
        cursor = segment_end
        overlap_start = max(start, segment_start)
        overlap_end = min(end, segment_end)
        if overlap_start >= overlap_end:
            result.append(segment)
            continue
        local_start = overlap_start - segment_start
        local_end = overlap_end - segment_start
        if local_start:
            result.append(InlineSegment(segment.text[:local_start], segment.bold))
        result.append(InlineSegment(segment.text[local_start:local_end], bold))
        if local_end < len(segment.text):
            result.append(InlineSegment(segment.text[local_end:], segment.bold))
    return _merge_segments(result)


def _merge_segments(segments: list[InlineSegment]) -> list[InlineSegment]:
    merged: list[InlineSegment] = []
    for segment in segments:
        if not segment.text:
            continue
        if merged and merged[-1].bold == segment.bold:
            merged[-1] = InlineSegment(merged[-1].text + segment.text, segment.bold)
        else:
            merged.append(segment)
    return merged


def _match_starts(text: str, target: str) -> list[int]:
    starts: list[int] = []
    cursor = 0
    while target and (position := text.find(target, cursor)) >= 0:
        starts.append(position)
        cursor = position + 1
    return starts


def _get_path(data: Any, path: tuple[str | int, ...]) -> Any:
    value = data
    for part in path:
        value = value[part]
    return value


def _set_path(data: Any, path: tuple[str | int, ...], value: Any) -> None:
    parent = data
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = value
