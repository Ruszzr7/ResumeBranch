"""Pure helpers for normalizing structured resume data."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


ACADEMIC_FIELD_ALIASES = {
    "gpa": ("GPA", "绩点", "平均绩点", "grade_point_average"),
    "gpa_scale": ("gpaScale", "gpa_max", "绩点满分", "满绩"),
    "ranking": ("rank", "class_rank", "专业排名", "排名"),
}

_RETIRED_ACADEMIC_ALIASES = (
    "average_score", "average", "averageScore", "weighted_average", "平均分", "加权平均分",
)

_GPA_LABEL = r"(?:GPA|平均绩点|绩点)"
_GPA_VALUE_RE = re.compile(
    rf"{_GPA_LABEL}\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)(?:\s*/\s*([0-9]+(?:\.[0-9]+)?))?",
    re.IGNORECASE,
)
_GPA_SCALE_RE = re.compile(
    r"(?:/\s*|满分\s*)([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_GPA_ONLY_TITLE_RE = re.compile(
    rf"^\s*{_GPA_LABEL}(?:\s*[:：]?\s*[0-9]+(?:\.[0-9]+)?(?:\s*/\s*[0-9]+(?:\.[0-9]+)?)?)?\s*$",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _take_alias(item: dict, canonical: str) -> str:
    current = _text(item.get(canonical))
    for alias in ACADEMIC_FIELD_ALIASES[canonical]:
        if not current and alias in item:
            current = _text(item.get(alias))
        item.pop(alias, None)
    return current


def _extract_gpa(text: str) -> tuple[str, str]:
    match = _GPA_VALUE_RE.search(text)
    if match:
        scale_match = _GPA_SCALE_RE.search(text[match.start():])
        return match.group(1), match.group(2) or (scale_match.group(1) if scale_match else "")
    return "", ""


def _migrate_gpa_thesis(education: dict) -> None:
    """Move legacy GPA-only thesis entries into explicit academic fields."""
    theses = education.get("theses")
    if not isinstance(theses, list):
        education["theses"] = []
        return

    retained = []
    for thesis in theses:
        if not isinstance(thesis, dict):
            retained.append(thesis)
            continue

        title = _text(thesis.get("title"))
        details = thesis.get("details")
        detail_text = " ".join(_text(value) for value in details) if isinstance(details, list) else _text(details)

        # Only migrate entries whose complete title is a GPA label/value. A real
        # thesis title that merely mentions GPA must remain a thesis.
        if not _GPA_ONLY_TITLE_RE.fullmatch(title):
            retained.append(thesis)
            continue

        value, scale = _extract_gpa(f"{title} {detail_text}")
        if not value:
            retained.append(thesis)
            continue

        if not education.get("gpa"):
            education["gpa"] = value
        if scale and not education.get("gpa_scale"):
            education["gpa_scale"] = scale

    education["theses"] = retained


_KNOWN_TOP_LEVEL = {
    "formatting_version",
    "basics",
    "education",
    "research_interests",
    "honors",
    "publications",
    "work_experience",
    "project_experience",
    "custom_sections",
    "others",
    "self_evaluation",
}

_TOP_LEVEL_ALIASES = {
    "research_direction": "research_interests",
    "research_directions": "research_interests",
    "research_areas": "research_interests",
    "research": "research_interests",
    "awards": "honors",
    "awards_and_honors": "honors",
    "achievements": "honors",
    "projects": "project_experience",
}

_NUMBERED_MARKER_RE = re.compile(r"(?<![A-Za-z0-9])[（(]\s*\d{1,2}\s*[）)]")
_LEADING_NUMBER_RE = re.compile(r"^\s*[（(]?\s*\d{1,2}\s*[）).、]\s*")
_PROJECT_INTRO_RE = re.compile(r"^(项目简介|项目背景|项目概述|项目说明)\s*[：:]\s*(.*)$")
_PROJECT_DUTY_RE = re.compile(r"^(项目职责|主要职责|个人职责|负责内容)\s*[：:]?\s*(.*)$")
_SKILL_SECTION_RE = re.compile(r"^(?:专业技能|技能特长|技术栈|核心技能|技能)$", re.IGNORECASE)
_LANGUAGE_SKILL_HINT_RE = re.compile(r"(?:英语|英文|语言能力|外语|CET[- ]?[四六46]|IELTS|TOEFL|雅思|托福)", re.IGNORECASE)
_CERTIFICATE_SKILL_HINT_RE = re.compile(r"(?:证书|认证|资格)", re.IGNORECASE)
_SYSTEM_METADATA_KEYS = {
    "parsing_status", "source_page_count", "source_fingerprint", "parser_adapter",
    "parser_transport", "layout_config", "workflow_state", "task_id", "project_id",
}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, dict):
            text = _text(item.get("text") or item.get("content") or item.get("value"))
        else:
            text = _text(item)
        if text and text not in result:
            result.append(text)
    return result


def _split_numbered_text(text: str) -> list[str]:
    """Split visibly numbered clauses without rewriting their wording."""
    value = _text(text)
    markers = list(_NUMBERED_MARKER_RE.finditer(value))
    if not markers:
        return [value] if value else []
    # A lone parenthesized number inside ordinary prose is not a safe split.
    prefix = value[: markers[0].start()].strip()
    if len(markers) == 1 and not re.search(r"(?:职责|内容|成果|工作|任务)\s*[：:]?\s*$", prefix):
        return [value]
    parts: list[str] = []
    if prefix:
        parts.append(prefix.rstrip("；;，,"))
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(value)
        part = value[marker.start():end].strip().rstrip("；;")
        if part:
            parts.append(part)
    return parts


def _normalize_details(value: Any) -> list[str]:
    result: list[str] = []
    for item in _string_list(value):
        for part in _split_numbered_text(item):
            if part and part not in result:
                result.append(part)
    return result


def _normalize_project_blocks(value: Any, legacy_details: list[str], *, experience_kind: str = "project") -> list[dict]:
    """Normalize semantic blocks and migrate the common legacy details shape."""
    result: list[dict] = []
    if isinstance(value, list):
        for raw in value:
            if not isinstance(raw, dict):
                continue
            block_type = _text(raw.get("type"))
            if block_type not in {"paragraph", "numbered_list", "bullet_list"}:
                block_type = "paragraph" if _text(raw.get("text")) else "bullet_list"
            label = _text(raw.get("label"))
            semantic_role = _text(raw.get("semantic_role"))
            if semantic_role not in {"introduction", "responsibilities", "generic"}:
                semantic_role = (
                    "introduction" if label and block_type == "paragraph"
                    else "responsibilities" if label
                    else "generic"
                )
            text = _text(raw.get("text"))
            items = [_LEADING_NUMBER_RE.sub("", item).strip() for item in _string_list(raw.get("items"))]
            items = [item for item in items if item]
            if text or items:
                result.append({
                    "type": block_type,
                    "semantic_role": semantic_role,
                    "label": label,
                    "label_bold": bool(raw.get("label_bold", True)),
                    "text": text,
                    "items": items,
                })
    if result or not legacy_details:
        return result

    # Work details are user-authored body text. Never infer semantic labels
    # from their wording; only explicit structured blocks may act as labels.
    if experience_kind == "work":
        return [{
            "type": "bullet_list", "semantic_role": "generic", "label": "", "label_bold": True,
            "text": "", "items": legacy_details,
        }]

    active_duties: dict | None = None
    unmatched: list[str] = []
    for detail in legacy_details:
        text = _text(detail)
        intro_match = _PROJECT_INTRO_RE.match(text)
        if intro_match:
            active_duties = None
            if intro_match.group(2).strip():
                result.append({
                    "type": "paragraph", "semantic_role": "introduction", "label": intro_match.group(1),
                    "label_bold": True, "text": intro_match.group(2).strip(), "items": [],
                })
            continue
        duty_match = _PROJECT_DUTY_RE.match(text)
        if duty_match:
            active_duties = {
                "type": "numbered_list", "semantic_role": "responsibilities", "label": duty_match.group(1),
                "label_bold": True, "text": "", "items": [],
            }
            remainder = _LEADING_NUMBER_RE.sub("", duty_match.group(2)).strip()
            if remainder:
                active_duties["items"].append(remainder)
            result.append(active_duties)
            continue
        if active_duties is not None:
            clean = _LEADING_NUMBER_RE.sub("", text).strip()
            if clean:
                active_duties["items"].append(clean)
            continue
        unmatched.append(text)
    if unmatched:
        result.append({
            "type": "bullet_list", "semantic_role": "generic", "label": "", "label_bold": True,
            "text": "", "items": unmatched,
        })
    return [block for block in result if block.get("text") or block.get("items")]


def _date_range(item: dict) -> list[str]:
    value = item.get("date_range", item.get("time", []))
    if isinstance(value, str):
        parts = re.split(r"\s*(?:-|—|–|~|至)\s*", value, maxsplit=1)
        values = [_text(part) for part in parts if _text(part)]
    elif isinstance(value, list):
        values = [_text(part) for part in value[:2] if _text(part)]
    else:
        values = []
    if not values:
        values = [_text(item.get("start_date")), _text(item.get("end_date"))]
        values = [part for part in values if part]
    return values


def _normalize_custom_sections(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    result: list[dict] = []
    for section in value:
        if not isinstance(section, dict):
            continue
        title = _text(section.get("title") or section.get("name") or section.get("section"))
        items = _string_list(section.get("items", section.get("lines", section.get("content"))))
        if title and items:
            result.append({"title": title, "items": items})
    return result


def _append_custom_section(sections: list[dict], title: str, value: Any) -> None:
    items = _string_list(value)
    if not title or not items:
        return
    existing = next((section for section in sections if section["title"] == title), None)
    if existing is None:
        sections.append({"title": title, "items": items})
        return
    for item in items:
        if item not in existing["items"]:
            existing["items"].append(item)


def normalize_resume_data(data: dict) -> dict:
    """Return a canonical, loss-preserving resume structure.

    Known legacy aliases are migrated. Unknown top-level textual sections are
    retained as custom sections instead of being silently discarded by schema
    validation.
    """
    if not isinstance(data, dict):
        raise TypeError("resume data must be a JSON object")

    normalized = deepcopy(data)
    for alias, canonical in _TOP_LEVEL_ALIASES.items():
        if alias in normalized and not normalized.get(canonical):
            normalized[canonical] = normalized[alias]
        normalized.pop(alias, None)

    basics = normalized.get("basics")
    if not isinstance(basics, dict):
        basics = {}
    if normalized.get("photo") and not basics.get("photo"):
        basics["photo"] = normalized.get("photo")
    normalized.pop("photo", None)
    if "date_of_birth" in basics and not basics.get("birth_date"):
        basics["birth_date"] = _text(basics.pop("date_of_birth"))
    else:
        basics.pop("date_of_birth", None)
    try:
        photo_ratio = float(basics.get("photo_aspect_ratio"))
    except (TypeError, ValueError):
        photo_ratio = None
    if photo_ratio is None:
        basics.pop("photo_aspect_ratio", None)
    else:
        basics["photo_aspect_ratio"] = min(3.0, max(0.2, photo_ratio))
    if "additional_fields" in basics:
        additional_fields = basics.get("additional_fields")
        if not isinstance(additional_fields, list):
            additional_fields = []
        basics["additional_fields"] = [
            {"label": _text(item.get("label")), "value": _text(item.get("value"))}
            for item in additional_fields
            if isinstance(item, dict) and (_text(item.get("label")) or _text(item.get("value")))
        ]
    normalized["basics"] = basics


    education_items = normalized.get("education") or []
    if not isinstance(education_items, list):
        raise TypeError("education must be a list")

    for education in education_items:
        if not isinstance(education, dict):
            raise TypeError("each education item must be a JSON object")

        for field in ACADEMIC_FIELD_ALIASES:
            education[field] = _take_alias(education, field)
        # Average score was removed from the product model. Drop both its
        # canonical key and historical aliases instead of persisting a dead
        # field that cannot be edited or rendered anymore.
        for retired in _RETIRED_ACADEMIC_ALIASES:
            education.pop(retired, None)

        # Accept a combined value such as "3.72/4.0" in the canonical gpa field.
        combined_value, combined_scale = _extract_gpa(f"GPA {education['gpa']}")
        if combined_value:
            education["gpa"] = combined_value
            if combined_scale and not education["gpa_scale"]:
                education["gpa_scale"] = combined_scale

        _migrate_gpa_thesis(education)

        education["date_range"] = _date_range(education)
        raw_school_tags = education.get("school_tags", [])
        if isinstance(raw_school_tags, str):
            raw_school_tags = re.split(r"[/·]", raw_school_tags)
        education["school_tags"] = _string_list(raw_school_tags)
        education.setdefault("theses", [])

    for key in ("research_interests", "honors", "publications", "self_evaluation"):
        if key in normalized:
            normalized[key] = _string_list(normalized.get(key))

    work_items = normalized.get("work_experience") or []
    if not isinstance(work_items, list):
        raise TypeError("work_experience must be a list")
    for item in work_items:
        if not isinstance(item, dict):
            raise TypeError("each work experience item must be a JSON object")
        item.setdefault("company_name", _text(item.pop("company", "")))
        item.setdefault("job_title", _text(item.pop("position", "")))
        item.setdefault("job_type", _text(item.pop("type", "")))
        item["date_range"] = _date_range(item)
        item["details"] = _normalize_details(item.get("details", item.pop("content", [])))
        item["content_blocks"] = _normalize_project_blocks(
            item.get("content_blocks"), item["details"], experience_kind="work",
        )
    normalized["work_experience"] = work_items

    project_items = normalized.get("project_experience") or []
    if not isinstance(project_items, list):
        raise TypeError("project_experience must be a list")
    for item in project_items:
        if not isinstance(item, dict):
            raise TypeError("each project experience item must be a JSON object")
        item.setdefault("project_name", _text(item.pop("name", "")))
        item["role"] = _text(item.get("role"))
        item["date_range"] = _date_range(item)
        item["details"] = _normalize_details(item.get("details", item.pop("content", [])))
        item["content_blocks"] = _normalize_project_blocks(item.get("content_blocks"), item["details"])
    normalized["project_experience"] = project_items

    others = normalized.get("others")
    if not isinstance(others, dict):
        others = {}
    for key in ("skills", "certificates", "languages"):
        others[key] = _string_list(others.get(key))

    # 解析器旧版本会仅凭内容语义，把原“专业技能”栏目中的 CET、语言或
    # 认证拆到新栏目。若技能原文自身明确包含对应标签，则把被拆出的内容
    # 归回专业技能，优先保持上传文件的栏目边界。
    # 仅对旧解析数据执行历史归类修复。新版编辑器会显式写入 formatting_version=3，
    # 其中 languages/certificates 是用户确认过的栏目，保存时不得再次挪到 skills。
    if int(normalized.get("formatting_version") or 0) < 2:
        skill_text = "\n".join(others["skills"])
        for field, hint in (("languages", _LANGUAGE_SKILL_HINT_RE), ("certificates", _CERTIFICATE_SKILL_HINT_RE)):
            if others[field] and hint.search(skill_text):
                for value in others[field]:
                    if not any(value in skill or skill in value for skill in others["skills"]):
                        others["skills"].append(value)
                others[field] = []
    normalized["others"] = others

    had_custom_sections = "custom_sections" in normalized
    custom_sections = _normalize_custom_sections(normalized.get("custom_sections"))
    retained_custom_sections: list[dict] = []
    for section in custom_sections:
        if section["title"].strip().lower() in _SYSTEM_METADATA_KEYS:
            continue
        if _SKILL_SECTION_RE.fullmatch(section["title"].strip()):
            for skill in section["items"]:
                if skill not in others["skills"]:
                    others["skills"].append(skill)
        else:
            retained_custom_sections.append(section)
    custom_sections = retained_custom_sections
    # Preserve model-provided/legacy top-level textual sections that are not
    # part of the canonical schema. This is the final safety net against data
    # loss when a resume contains a novel heading.
    for key in list(normalized):
        if key in _KNOWN_TOP_LEVEL:
            continue
        value = normalized.pop(key)
        if str(key).strip().lower() in _SYSTEM_METADATA_KEYS:
            continue
        if isinstance(value, (str, list)):
            _append_custom_section(custom_sections, str(key).strip(), value)
    if custom_sections or had_custom_sections:
        normalized["custom_sections"] = custom_sections
    else:
        normalized.pop("custom_sections", None)

    return normalized
