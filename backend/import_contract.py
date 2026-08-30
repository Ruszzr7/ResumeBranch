"""Source-aware import normalization and quality checks.

The parser may return a syntactically valid object that is still too empty to
replace the user's resume.  Import policy belongs here rather than in the API
route so draft preview, confirmation, and any future parser adapter share the
same loss-prevention rules.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable

from .inline_formatting import parse_inline_bold, plain_inline_text, serialize_inline_bold
from .resume_data import normalize_resume_data


IMPORT_CONTRACT_VERSION = 4
MIN_IMPORT_TEXT_VOLUME = 60
IDENTITY_FIELDS = ("name", "phone", "email")
PROJECT_CONTENT_LABELS = {
    "tech_stack": "技术栈",
    "introduction": "项目简介",
    "responsibilities": "项目职责",
}
WORK_CONTENT_LABELS = {
    "introduction": "工作简介",
    "responsibilities": "工作职责",
}


def _plain_import_text(value: Any) -> str:
    """Remove storage-only bold markers from a fixed-format import field."""
    return plain_inline_text(value).strip()


def _default_bold_import_text(value: Any) -> str:
    """Apply the product default bold weight to one fixed title field."""
    text = _plain_import_text(value)
    return f"**{text}**" if text else ""


def _preserve_content_import_text(value: Any) -> str:
    """Preserve source-level inline bold spans in a free-form value."""
    text = str(value or "").strip()
    if not text:
        return ""
    return serialize_inline_bold(parse_inline_bold(text)).strip()


def _normalize_free_list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([value] if value else [])
    result: list[str] = []
    for item in values:
        text = _preserve_content_import_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _strip_job_type_suffix(value: Any, job_type: Any) -> str:
    """Avoid showing a work type twice in the position and type columns."""
    text = _plain_import_text(value)
    kind = _plain_import_text(job_type)
    if not text or not kind:
        return text
    if text == kind:
        return ""
    pattern = rf"\s*[（(]\s*{re.escape(kind)}\s*[）)]\s*$"
    return re.sub(pattern, "", text).strip()


def _apply_import_formatting_contract(data: dict[str, Any]) -> None:
    """Apply stable import typography without changing user edit semantics."""
    basics = data.get("basics") or {}
    for key in ("name", "target_position"):
        basics[key] = _default_bold_import_text(basics.get(key))
    for key in ("gender", "birth_date", "phone", "email"):
        basics[key] = _plain_import_text(basics.get(key))
    for field in basics.get("additional_fields") or []:
        if isinstance(field, dict):
            field["label"] = _plain_import_text(field.get("label"))
            field["value"] = _plain_import_text(field.get("value"))

    for education in data.get("education") or []:
        education["school_name"] = _default_bold_import_text(education.get("school_name"))
        for key in ("degree", "major", "gpa", "gpa_scale", "ranking"):
            education[key] = _plain_import_text(education.get(key))
        education["date_range"] = [_plain_import_text(value) for value in education.get("date_range") or []]
        education["school_tags"] = [_plain_import_text(value) for value in education.get("school_tags") or []]
        for thesis in education.get("theses") or []:
            if isinstance(thesis, dict):
                thesis["title"] = _preserve_content_import_text(thesis.get("title"))
                thesis["details"] = _normalize_free_list(thesis.get("details"))

    for key in ("education_supplement", "research_interests", "honors", "publications", "self_evaluation"):
        data[key] = _normalize_free_list(data.get(key))

    for item in data.get("work_experience") or []:
        item["job_type"] = _plain_import_text(item.get("job_type"))
        item["company_name"] = _default_bold_import_text(
            _strip_job_type_suffix(item.get("company_name"), item.get("job_type"))
        )
        item["job_title"] = _default_bold_import_text(
            _strip_job_type_suffix(item.get("job_title"), item.get("job_type"))
        )
        item["date_range"] = [_plain_import_text(value) for value in item.get("date_range") or []]
        for block in item.get("content_blocks") or []:
            if not isinstance(block, dict):
                continue
            block["label"] = _plain_import_text(block.get("label"))
            role = block.get("semantic_role")
            if role in WORK_CONTENT_LABELS:
                if not block["label"]:
                    block["label"] = WORK_CONTENT_LABELS[role]
                block["label_bold"] = True
            if role == "responsibilities" and block.get("type") == "bullet_list":
                block["type"] = "numbered_list"
            block["text"] = _preserve_content_import_text(block.get("text"))
            block["items"] = _normalize_free_list(block.get("items"))

    for item in data.get("project_experience") or []:
        item["project_name"] = _default_bold_import_text(item.get("project_name"))
        item["role"] = _plain_import_text(item.get("role"))
        item["date_range"] = [_plain_import_text(value) for value in item.get("date_range") or []]
        for block in item.get("content_blocks") or []:
            if not isinstance(block, dict):
                continue
            block["label"] = _plain_import_text(block.get("label"))
            role = block.get("semantic_role")
            if role in PROJECT_CONTENT_LABELS:
                if not block["label"]:
                    block["label"] = PROJECT_CONTENT_LABELS[role]
                block["label_bold"] = True
            if role == "responsibilities" and block.get("type") == "bullet_list":
                block["type"] = "numbered_list"
            block["text"] = _preserve_content_import_text(block.get("text"))
            block["items"] = _normalize_free_list(block.get("items"))

    others = data.get("others") or {}
    for key in ("skills", "certificates", "languages"):
        others[key] = _normalize_free_list(others.get(key))
    if isinstance(others.get("field_labels"), dict):
        for key in ("certificates", "languages"):
            others["field_labels"][key] = _plain_import_text(others["field_labels"].get(key))

    for section in data.get("custom_sections") or []:
        if isinstance(section, dict):
            section["title"] = _default_bold_import_text(section.get("title"))
            section["items"] = _normalize_free_list(section.get("items"))


@dataclass(frozen=True)
class ImportQuality:
    """Stable, user-safe diagnostics for an imported structured resume."""

    accepted: bool
    text_volume: int
    identity_fields: tuple[str, ...]
    structured_sections: tuple[str, ...]
    warning: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "text_volume": self.text_volume,
            "identity_fields": list(self.identity_fields),
            "structured_sections": list(self.structured_sections),
            "warning": self.warning,
            "contract_version": IMPORT_CONTRACT_VERSION,
        }


def assess_import_quality(data: dict[str, Any]) -> ImportQuality:
    """Assess whether an import contains enough evidence to replace a resume."""
    payload = json.dumps(data or {}, ensure_ascii=False).replace('"', '').replace(':', '')
    basics = data.get("basics") if isinstance(data, dict) else {}
    basics = basics if isinstance(basics, dict) else {}
    identity = tuple(
        field for field in IDENTITY_FIELDS if str(basics.get(field) or "").strip()
    )
    section_keys = (
        "education", "research_interests", "honors", "publications",
        "work_experience", "project_experience", "custom_sections",
        "others", "self_evaluation",
    )
    sections = tuple(
        key for key in section_keys
        if data.get(key) and (not isinstance(data.get(key), list) or len(data[key]) > 0)
    )
    accepted = len(payload) >= MIN_IMPORT_TEXT_VOLUME and bool(identity)
    warning = "" if accepted else "解析结果缺少足够的简历内容，请更换更清晰的文件或解析模型后重试。"
    return ImportQuality(accepted, len(payload), identity, sections, warning)


def finalize_import_resume(
    raw_data: dict[str, Any],
    validator: Callable[..., dict[str, Any]],
) -> tuple[dict[str, Any], ImportQuality]:
    """Normalize, validate, and apply only product-level import defaults.

    The validator is injected to keep this module independent from the agent's
    Pydantic model and therefore safe for API, tests, and future parser adapters.
    """
    if not isinstance(raw_data, dict):
        raise ValueError("解析结果不是有效的简历对象")
    normalized = validator(normalize_resume_data(raw_data), include_defaults=True)
    if not isinstance(normalized, dict):
        raise ValueError("解析结果不是有效的简历对象")

    _apply_import_formatting_contract(normalized)
    normalized["formatting_version"] = 4

    quality = assess_import_quality(normalized)
    if not quality.accepted:
        raise ValueError(quality.warning)
    return normalized, quality
