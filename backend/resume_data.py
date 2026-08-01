"""Pure helpers for normalizing structured resume data."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


ACADEMIC_FIELD_ALIASES = {
    "gpa": ("GPA", "绩点", "平均绩点", "grade_point_average"),
    "gpa_scale": ("gpaScale", "gpa_max", "绩点满分", "满绩"),
    "ranking": ("rank", "class_rank", "专业排名", "排名"),
    "average_score": (
        "average",
        "averageScore",
        "weighted_average",
        "平均分",
        "加权平均分",
    ),
}

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


def normalize_resume_data(data: dict) -> dict:
    """Return a defensive copy with canonical academic-performance fields."""
    if not isinstance(data, dict):
        raise TypeError("resume data must be a JSON object")

    normalized = deepcopy(data)
    education_items = normalized.get("education")
    if education_items is None:
        normalized["education"] = []
        return normalized
    if not isinstance(education_items, list):
        raise TypeError("education must be a list")

    for education in education_items:
        if not isinstance(education, dict):
            raise TypeError("each education item must be a JSON object")

        for field in ACADEMIC_FIELD_ALIASES:
            education[field] = _take_alias(education, field)

        # Accept a combined value such as "3.72/4.0" in the canonical gpa field.
        combined_value, combined_scale = _extract_gpa(f"GPA {education['gpa']}")
        if combined_value:
            education["gpa"] = combined_value
            if combined_scale and not education["gpa_scale"]:
                education["gpa_scale"] = combined_scale

        _migrate_gpa_thesis(education)

    return normalized
