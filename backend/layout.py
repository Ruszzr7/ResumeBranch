"""Shared automatic page-layout rules for resume preview and exports."""

import re


_BREAK_KEY_RE = re.compile(
    r"^(?:education|work_experience|project_experience):\d+$|^(?:others|self_evaluation)$"
)


def normalize_page_mode(value) -> str:
    """Legacy compatibility: page count is now always automatic."""
    return "auto"


def page_limit(value) -> int:
    return 2


def enforce_page_limit(value, actual_pages: int) -> None:
    if actual_pages > 2:
        raise ValueError("当前内容超出两页，请精简内容或调整排版后再导出")


def normalize_source_page_count(value) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def normalize_page_break(value) -> str:
    key = str(value or "").strip()
    return key if _BREAK_KEY_RE.fullmatch(key) else ""


def apply_page_mode_defaults(style: dict | None) -> dict:
    result = dict(style or {})
    result["pageMode"] = "auto"
    result["sourcePageCount"] = normalize_source_page_count(result.get("sourcePageCount"))
    result["pageBreakBefore"] = normalize_page_break(result.get("pageBreakBefore"))
    return result
