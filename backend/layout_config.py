"""Versioned, deterministic resume layout configuration.

The conversation model may choose values from this contract, but renderers only
consume normalized values from this module.  Arbitrary CSS/HTML is never stored.
"""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

from .inline_formatting import (
    is_fully_bold_inline,
    join_inline_with_inherited_separator,
    plain_inline_text,
)
from .resume_contract import normalize_content_block


LAYOUT_SCHEMA_VERSION = 10
# Physical clearance between the photo bottom and the first visible section
# divider for browser/PDF geometry.  Word keeps its own table-specific cap.
PHOTO_BOTTOM_GAP_MM = 1.5

FONT_SIZE_LIMITS: dict[str, tuple[float, float]] = {
    "name": (12.0, 20.0),
    "sectionTitle": (9.0, 16.0),
    "entryTitle": (8.5, 14.0),
    "meta": (8.0, 11.5),
    "body": (8.0, 11.5),
    "label": (8.0, 12.0),
}


def resolve_content_block_flow(block: dict[str, Any] | None = None) -> dict[str, Any]:
    """Describe whether a semantic content label shares the content line."""
    block = normalize_content_block(block or {}, keep_empty=True) or {}
    block_type = block["type"]
    label = block["label"]
    semantic_role = block["semantic_role"]
    requires_label = semantic_role != "generic" or bool(label)
    # A labeled list has two visible hierarchy levels: the outer semantic
    # label and its child bullets/numbers. Paragraph labels remain at level 1,
    # as do generic lists without an outer label.
    if requires_label and label and block_type in {"numbered_list", "bullet_list"}:
        content_indent_levels = 2
    else:
        content_indent_levels = (
            1 if requires_label or block_type in {"numbered_list", "bullet_list"}
            else 0
        )
    placement = "none" if not label else ("inline" if block_type == "paragraph" else "separate")
    return {
        "type": block_type,
        "label": label,
        "semanticRole": semantic_role,
        "requiresLabel": requires_label,
        "visible": not requires_label or bool(label),
        "labelMarker": "bullet" if requires_label and label else "none",
        "contentIndentLevels": content_indent_levels,
        "labelPlacement": placement,
        "labelBold": block.get("label_bold") is not False,
    }


def format_compact_academic_metric(
    item: dict[str, Any] | None,
    hidden_metrics: set[str] | list[str] | tuple[str, ...] = (),
) -> str:
    """Format compact education metrics once for all renderers."""
    item = item or {}
    hidden = set(hidden_metrics)
    metric = ""
    if item.get("gpa") and "gpa" not in hidden:
        metric = str(item["gpa"])
        if item.get("gpa_scale"):
            metric = join_inline_with_inherited_separator(
                [metric, item["gpa_scale"]], "/"
            )
    if item.get("ranking") and "ranking" not in hidden:
        ranking = str(item["ranking"]).strip().strip("()（）")
        ranking = (
            f"**({plain_inline_text(ranking)})**"
            if is_fully_bold_inline(ranking)
            else f"({ranking})"
        )
        metric = join_inline_with_inherited_separator(
            [metric, ranking], " "
        )
    return metric


def is_compact_academic_metric_leading_bold(
    item: dict[str, Any] | None,
    hidden_metrics: set[str] | list[str] | tuple[str, ...] = (),
) -> bool:
    """Return whether the GPA field immediately after the major is bold.

    The total scale after the slash and the later ranking are independent
    fields; neither can decide the separator between the major and GPA.
    """
    item = item or {}
    hidden = set(hidden_metrics)
    if item.get("gpa") and "gpa" not in hidden:
        return is_fully_bold_inline(item["gpa"])
    return False


def _semantic_font_sizes(body_size: float) -> dict[str, float]:
    """Return the v4 visual hierarchy expressed as explicit v5 roles."""
    return {
        "name": 14.0,
        "sectionTitle": body_size + 2.0,
        "entryTitle": body_size + 1.0,
        "meta": body_size,
        "body": body_size,
        "label": body_size,
    }

TYPOGRAPHY_PRESETS: dict[str, dict[str, Any]] = {
    "microsoft-office": {
        "latinFont": "Times New Roman",
        "eastAsiaFont": "Microsoft YaHei",
        "latinFallbackFonts": ["Liberation Serif"],
        "fallbackFonts": ["Noto Sans CJK SC", "sans-serif"],
    },
}

SECTION_IDS = (
    "education",
    "honors",
    "publications",
    "research_interests",
    "skills",
    "work_experience",
    "project_experience",
    "custom_sections",
    "others",
    "self_evaluation",
)
EDUCATION_CHILD_SECTION_IDS = (
    "education_supplement",
    "honors",
    "publications",
    "research_interests",
    "others",
)
_CUSTOM_SECTION_MODULE_RE = re.compile(r"^custom_sections:(\d+)$")


def custom_section_module_id(index: int) -> str:
    return f"custom_sections:{max(0, int(index))}"


def custom_section_index(module_id: object) -> int | None:
    match = _CUSTOM_SECTION_MODULE_RE.fullmatch(str(module_id or ""))
    return int(match.group(1)) if match else None


def is_custom_section_module(module_id: object) -> bool:
    return custom_section_index(module_id) is not None


def _is_valid_section_id(value: object) -> bool:
    return str(value) in SECTION_IDS or is_custom_section_module(value)

MODULE_COMPONENTS: dict[str, tuple[str, ...]] = {
    "basics": ("name", "target_position", "personal_meta", "contact", "additional_fields", "photo"),
    "education": ("school", "school_tags", "degree", "major", "metrics", "date", "theses"),
    "skills": ("items",),
    "research_interests": ("items",),
    "honors": ("items",),
    "publications": ("items",),
    "work_experience": ("organization", "position", "job_type", "date", "content"),
    "project_experience": ("project_name", "role", "date", "content"),
    "custom_sections": ("items",),
    "others": ("certificates", "languages"),
    "self_evaluation": ("items",),
}

REQUIRED_COMPONENTS = {
    "basics": {"name"},
    "education": {"school"},
    "skills": {"items"},
    "research_interests": {"items"},
    "honors": {"items"},
    "publications": {"items"},
    "work_experience": {"organization", "content"},
    "project_experience": {"project_name", "content"},
    "custom_sections": {"items"},
    "others": set(),
    "self_evaluation": {"items"},
}

LONG_TEXT_COMPONENTS = {
    ("education", "theses"),
    ("work_experience", "content"),
    ("project_experience", "content"),
    ("skills", "items"),
    ("research_interests", "items"),
    ("honors", "items"),
    ("publications", "items"),
    ("custom_sections", "items"),
    ("self_evaluation", "items"),
}

DEFAULT_COMPONENT_ROWS: dict[str, list[dict[str, Any]]] = {
    "basics": [
        {"cells": [{"components": ["name"], "flow": "stacked", "width": "fill", "alignment": "left"}, {"components": ["photo"], "flow": "stacked", "width": "content", "alignment": "right"}]},
        {"cells": [{"components": ["target_position"], "flow": "stacked", "width": "fill", "alignment": "left"}]},
        {"cells": [{"components": ["personal_meta", "contact", "additional_fields"], "flow": "inline", "width": "fill", "alignment": "left"}]},
    ],
    "education": [
        {"cells": [{"components": ["school", "school_tags"], "flow": "inline", "width": "content", "alignment": "left"}, {"components": ["degree", "major", "metrics"], "flow": "inline", "width": "fill", "alignment": "left"}, {"components": ["date"], "flow": "inline", "width": "content", "alignment": "right"}]},
        {"cells": [{"components": ["theses"], "flow": "stacked", "width": "fill", "alignment": "justify"}]},
    ],
    "work_experience": [
        {"cells": [{"components": ["organization", "position", "job_type"], "flow": "inline", "width": "fill", "alignment": "left"}, {"components": ["date"], "flow": "inline", "width": "content", "alignment": "right"}]},
        {"cells": [{"components": ["content"], "flow": "stacked", "width": "fill", "alignment": "justify"}]},
    ],
    "project_experience": [
        {"cells": [{"components": ["project_name", "role"], "flow": "inline", "width": "fill", "alignment": "left"}, {"components": ["date"], "flow": "inline", "width": "content", "alignment": "right"}]},
        {"cells": [{"components": ["content"], "flow": "stacked", "width": "fill", "alignment": "justify"}]},
    ],
    "skills": [{"cells": [{"components": ["items"], "flow": "stacked", "width": "fill", "alignment": "justify"}]}],
    "research_interests": [{"cells": [{"components": ["items"], "flow": "stacked", "width": "fill", "alignment": "justify"}]}],
    "honors": [{"cells": [{"components": ["items"], "flow": "stacked", "width": "fill", "alignment": "justify"}]}],
    "publications": [{"cells": [{"components": ["items"], "flow": "stacked", "width": "fill", "alignment": "justify"}]}],
    "custom_sections": [{"cells": [{"components": ["items"], "flow": "stacked", "width": "fill", "alignment": "justify"}]}],
    # Keep certificates and languages on separate semantic lines.  Entries
    # within each field still use the configured separator.
    "others": [
        {"cells": [{"components": ["certificates"], "flow": "stacked", "width": "fill", "alignment": "left"}]},
        {"cells": [{"components": ["languages"], "flow": "stacked", "width": "fill", "alignment": "left"}]},
    ],
    "self_evaluation": [{"cells": [{"components": ["items"], "flow": "stacked", "width": "fill", "alignment": "justify"}]}],
}


def _module_contract(module_id: str, **values: Any) -> dict[str, Any]:
    return {
        "titleStyle": None,
        "titleAlignment": None,
        "paragraphSpacing": 0.09,
        "itemSpacing": 0.22,
        "contentBlockSpacing": 0.14,
        "rowSpacing": 0.0,
        # Marker columns provide their own hanging indent. Module indentation
        # is an additional user-controlled offset and therefore defaults to 0.
        "indentLevel": 0,
        "hiddenComponents": [],
        "componentRows": deepcopy(DEFAULT_COMPONENT_ROWS[module_id]),
        **values,
    }

DEFAULT_LAYOUT_CONFIG: dict[str, Any] = {
    "version": LAYOUT_SCHEMA_VERSION,
    "typography": {
        "preset": "microsoft-office",
        **deepcopy(TYPOGRAPHY_PRESETS["microsoft-office"]),
        "fontSizes": _semantic_font_sizes(9.0),
    },
    "global": {
        "density": "compact",
        "fontSize": 9.0,
        "lineHeight": 1.25,
        "moduleMargin": 0.5,
        "marginVertical": 8.5,
        "marginHorizontal": 9.0,
        "titleStyle": "underline",
        "sectionOrder": [
            "education",
            "honors",
            "publications",
            "research_interests",
            "skills",
            "work_experience",
            "project_experience",
            "custom_sections",
            "others",
            "self_evaluation",
        ],
        "hiddenSections": [],
        "titleOverrides": {},
        "sectionPlacements": {},
    },
    "basics": _module_contract("basics",
        photoPosition="right",
        photoHeightMm=26.0,
        photoWidthMm=21.0,
        hiddenFields=[],
    ),
    "education": _module_contract("education",
        schoolTagStyle="text",
        hiddenMetrics=[],
        thesisDisplay="expanded",
        supplementListStyle="bullet",
        childSectionOrder=["education_supplement", "honors", "publications", "research_interests", "others"],
    ),
    "skills": _module_contract("skills", listStyle="bullet"),
    "research_interests": _module_contract("research_interests", listStyle="bullet"),
    "honors": _module_contract("honors", listStyle="bullet"),
    "publications": _module_contract("publications", listStyle="bullet"),
    "work_experience": _module_contract("work_experience",
        detailsStyle="bullets",
        datePosition="right",
        showJobType=True,
    ),
    "project_experience": _module_contract("project_experience",
        detailsStyle="bullets",
        datePosition="right",
        showRole=True,
        showDate=True,
    ),
    "custom_sections": _module_contract("custom_sections", listStyle="bullet"),
    "others": _module_contract("others",
        fieldOrder=["skills", "certificates", "languages"],
        hiddenFields=[],
        separator="dot",
    ),
    "self_evaluation": _module_contract("self_evaluation", listStyle="paragraph"),
}

DENSITY_VALUES = {
    "compact": {"fontSize": 9.0, "lineHeight": 1.25, "moduleMargin": 0.5},
    "standard": {"fontSize": 9.5, "lineHeight": 1.25, "moduleMargin": 0.65},
    "comfortable": {"fontSize": 10.0, "lineHeight": 1.45, "moduleMargin": 0.8},
}

ENUMS = {
    ("typography", "preset"): set(TYPOGRAPHY_PRESETS),
    ("global", "density"): set(DENSITY_VALUES),
    ("global", "titleStyle"): {"underline", "plain"},
    ("basics", "photoPosition"): {"right", "hidden"},
    ("education", "schoolTagStyle"): {"filled", "outline", "text", "hidden"},
    ("education", "thesisDisplay"): {"expanded", "compact", "hidden"},
    ("education", "supplementListStyle"): {"paragraph", "bullet", "numbered"},
    ("work_experience", "detailsStyle"): {"bullets", "paragraph"},
    ("work_experience", "datePosition"): {"right", "inline"},
    ("project_experience", "detailsStyle"): {"bullets", "paragraph"},
    ("project_experience", "datePosition"): {"right", "inline"},
    ("others", "separator"): {"pipe", "dot"},
}

ALLOWED_HIDDEN_FIELDS = {
    "basics": {"gender", "birth_date", "phone", "email", "target_position", "photo", "additional_fields"},
    "education": {"gpa", "ranking"},
    "others": {"skills", "certificates", "languages"},
}

MODULE_LABELS = {
    "typography": "字体",
    "global": "全局排版",
    "basics": "基本信息",
    "education": "教育经历",
    "skills": "专业技能",
    "research_interests": "研究方向",
    "honors": "主要荣誉",
    "publications": "论文",
    "work_experience": "工作/实习经历",
    "project_experience": "项目经历",
    "custom_sections": "自定义栏目",
    "others": "其他信息",
    "self_evaluation": "自我评价",
}

VALUE_LABELS = {
    "compact": "紧凑", "standard": "标准", "comfortable": "舒展",
    "underline": "强调标题", "plain": "简洁标题",
    "left-aligned": "左对齐式",
    "inline": "同行", "stacked": "纵向", "right": "右侧", "hidden": "隐藏",
    "classic": "经典", "three-column": "三列", "filled": "实心标签",
    "outline": "描边标签", "text": "普通文字", "below": "独立下一行",
    "with-degree": "与学历专业同行", "info-column": "信息列",
    "expanded": "完整展示", "bullets": "圆点列表", "bullet": "分点", "bullet_list": "分点",
    "numbered": "编号", "numbered_list": "编号", "paragraph": "普通段落",
    "tech_stack": "技术栈", "introduction": "项目简介", "responsibilities": "项目职责", "generic": "普通内容",
    "education_supplement": "教育经历补充", "honors": "主要荣誉", "publications": "论文",
    "research_interests": "研究方向", "others": "其他信息",
    "standalone": "独立栏目",
    "paragraphs": "分段", "tags": "标签", "pipe": "竖线分隔", "dot": "圆点分隔",
}

FIELD_LABELS = {
    ("typography", "preset"): "字体方案",
    ("typography", "fontSizes"): "分角色字号",
    ("global", "density"): "整体密度",
    ("global", "fontSize"): "字体大小",
    ("global", "lineHeight"): "行间距",
    ("global", "moduleMargin"): "模块间距",
    ("global", "marginVertical"): "上下页边距",
    ("global", "marginHorizontal"): "左右页边距",
    ("global", "titleStyle"): "模块标题样式",
    ("global", "sectionOrder"): "模块顺序",
    ("global", "hiddenSections"): "隐藏模块",
    ("global", "titleOverrides"): "模块标题名称",
    ("global", "sectionPlacements"): "模块归属位置",
    ("basics", "photoPosition"): "照片位置",
    ("basics", "hiddenFields"): "隐藏字段",
    ("education", "schoolTagStyle"): "学校标签样式",
    ("education", "hiddenMetrics"): "隐藏成绩项",
    ("education", "thesisDisplay"): "论文展示方式",
    ("education", "supplementListStyle"): "教育经历补充分点形式",
    ("education", "childSectionOrder"): "教育经历子模块顺序",
    ("skills", "listStyle"): "专业技能展示形式",
    ("research_interests", "listStyle"): "研究方向展示形式",
    ("honors", "listStyle"): "主要荣誉展示形式",
    ("publications", "listStyle"): "论文展示形式",
    ("work_experience", "detailsStyle"): "工作描述样式",
    ("work_experience", "datePosition"): "工作日期位置",
    ("work_experience", "showJobType"): "显示工作类型",
    ("project_experience", "detailsStyle"): "项目描述样式",
    ("project_experience", "datePosition"): "项目日期位置",
    ("project_experience", "showRole"): "显示项目角色",
    ("project_experience", "showDate"): "显示项目日期",
    ("custom_sections", "listStyle"): "自定义栏目展示形式",
    ("others", "fieldOrder"): "信息顺序",
    ("others", "hiddenFields"): "隐藏字段",
    ("others", "separator"): "信息分隔符",
    ("self_evaluation", "listStyle"): "自我评价展示形式",
}

ITEM_LABELS = {
    **MODULE_LABELS,
    "skills": "技能",
    "certificates": "证书",
    "languages": "语言",
    "gender": "性别",
    "phone": "电话",
    "email": "邮箱",
    "target_position": "目标岗位",
    "photo": "照片",
    "gpa": "GPA",
    "ranking": "排名",
}


def _display_layout_value(value: Any, field_key: str = "") -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "、".join(
            "自定义栏目" if is_custom_section_module(item)
            else ITEM_LABELS.get(str(item), VALUE_LABELS.get(str(item), str(item)))
            for item in value
        ) or "无"
    if isinstance(value, dict):
        if field_key == "titleOverrides":
            return "、".join(
                f"{ITEM_LABELS.get(str(key), str(key))}："
                f"{str(item.get('zh') or item.get('en') or '').strip()}"
                for key, item in value.items()
                if isinstance(item, dict) and (item.get("zh") or item.get("en"))
            ) or "无"
        placement_labels = {"standalone": "独立栏目", "education": "并入教育经历"} if field_key == "sectionPlacements" else {}
        return "、".join(
            f"{ITEM_LABELS.get(str(key), str(key))}：{placement_labels.get(str(item), VALUE_LABELS.get(str(item), str(item)))}"
            for key, item in value.items()
        ) or "无"
    return VALUE_LABELS.get(str(value), str(value))


def default_layout_config() -> dict:
    return deepcopy(DEFAULT_LAYOUT_CONFIG)


def _merge_known(target: dict, supplied: dict, template: dict) -> None:
    for key, default_value in template.items():
        if key not in supplied:
            continue
        value = supplied[key]
        if isinstance(default_value, dict) and isinstance(value, dict):
            _merge_known(target[key], value, default_value)
        else:
            target[key] = deepcopy(value)


def _enum(config: dict, section: str, key: str) -> None:
    allowed = ENUMS[(section, key)]
    if config[section].get(key) not in allowed:
        config[section][key] = deepcopy(DEFAULT_LAYOUT_CONFIG[section][key])


def _bounded_number(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return min(max(number, minimum), maximum)


def _half_point(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    bounded = _bounded_number(value, minimum, maximum, fallback)
    # Values are positive. Explicit half-up rounding matches JavaScript's
    # Math.round so browser and backend normalization cannot disagree at .25.
    return math.floor(bounded * 2 + 0.5) / 2


def _legacy_component_rows(module_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate v1-v6 presets into the renderer-neutral v7 row contract."""
    rows = deepcopy(DEFAULT_COMPONENT_ROWS[module_id])
    if module_id == "work_experience" and config.get("datePosition") == "inline":
        rows[0] = {"cells": [{"components": ["organization", "position", "job_type", "date"], "flow": "inline", "width": "fill", "alignment": "left"}]}
    if module_id == "project_experience" and config.get("datePosition") == "inline":
        rows[0] = {"cells": [{"components": ["project_name", "role", "date"], "flow": "inline", "width": "fill", "alignment": "left"}]}
    return rows


def _normalize_component_rows(module_id: str, supplied: Any, fallback: list[dict[str, Any]], hidden: set[str]) -> list[dict[str, Any]]:
    allowed = set(MODULE_COMPONENTS[module_id])
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    candidates = supplied if isinstance(supplied, list) else []
    for raw_row in candidates[:12]:
        if not isinstance(raw_row, dict) or not isinstance(raw_row.get("cells"), list):
            continue
        cells = []
        for raw_cell in raw_row["cells"][:3]:
            if not isinstance(raw_cell, dict):
                continue
            components = []
            for component in raw_cell.get("components", []):
                if component in allowed and component not in hidden and component not in seen:
                    components.append(component)
            if not components:
                continue
            contains_long_text = any((module_id, component) in LONG_TEXT_COMPONENTS for component in components)
            # Long prose/list components always occupy a full-width cell. This
            # is the common subset that remains editable and stable in Word.
            if contains_long_text:
                components = [component for component in components if (module_id, component) in LONG_TEXT_COMPONENTS]
                alignment = raw_cell.get("alignment") if raw_cell.get("alignment") in {"left", "justify"} else "justify"
                width = "fill"
                flow = "stacked"
            else:
                alignment = raw_cell.get("alignment") if raw_cell.get("alignment") in {"left", "center", "right"} else "left"
                width = raw_cell.get("width") if raw_cell.get("width") in {"content", "fill", "equal"} else "fill"
                flow = raw_cell.get("flow") if raw_cell.get("flow") in {"inline", "stacked"} else "inline"
            if "photo" in components:
                components = ["photo"]
                width, flow, alignment = "content", "stacked", "right"
            seen.update(components)
            cells.append({
                "components": components,
                "flow": flow,
                "width": width,
                "alignment": alignment,
            })
        if cells:
            # A long text cell cannot share its row with narrow metadata cells.
            long_cell = next((cell for cell in cells if any((module_id, item) in LONG_TEXT_COMPONENTS for item in cell["components"])), None)
            rows.append({"cells": [long_cell] if long_cell else cells})

    missing = [component for component in MODULE_COMPONENTS[module_id] if component not in seen and component not in hidden]
    if missing:
        for fallback_row in fallback:
            cells = []
            for fallback_cell in fallback_row["cells"]:
                components = [item for item in fallback_cell["components"] if item in missing]
                if components:
                    cells.append({**deepcopy(fallback_cell), "components": components})
                    for item in components:
                        if item in missing:
                            missing.remove(item)
            if cells:
                rows.append({"cells": cells})
    return rows or deepcopy(fallback)


def _normalize_other_component_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep certificate and language values on two separate renderer rows."""
    cell_by_component: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        for cell in row.get("cells", []):
            for component in cell.get("components", []):
                cell_by_component.setdefault(component, cell)
    defaults = DEFAULT_COMPONENT_ROWS["others"]
    normalized = []
    for index, component in enumerate(("certificates", "languages")):
        source = cell_by_component.get(component, defaults[index]["cells"][0])
        normalized.append({
            "cells": [{
                **deepcopy(source),
                "components": [component],
                "flow": "stacked",
                "width": "fill",
                "alignment": "left",
            }]
        })
    return normalized


def _normalize_module_contract(result: dict[str, Any], source: dict | None, supplied_version: int) -> None:
    source = source if isinstance(source, dict) else {}
    for module_id in MODULE_COMPONENTS:
        module = result[module_id]
        # Section title styling and alignment are document-wide rules. Legacy
        # per-module overrides are accepted on input but deliberately cleared.
        module["titleStyle"] = None
        module["titleAlignment"] = None
        module["paragraphSpacing"] = _bounded_number(module.get("paragraphSpacing"), 0, 1.5, 0.09)
        module["itemSpacing"] = _bounded_number(module.get("itemSpacing"), 0, 2, 0.22)
        module["contentBlockSpacing"] = _bounded_number(module.get("contentBlockSpacing"), 0, 2, 0.14)
        module["rowSpacing"] = _bounded_number(module.get("rowSpacing"), 0, 2, 0)
        try:
            indent = int(module.get("indentLevel", 0))
        except (TypeError, ValueError):
            indent = 0
        module["indentLevel"] = min(max(indent, 0), 3)
        if module_id == "education":
            if module.get("supplementListStyle") not in {"paragraph", "bullet", "numbered"}:
                module["supplementListStyle"] = DEFAULT_LAYOUT_CONFIG["education"]["supplementListStyle"]
        hidden = {
            component for component in module.get("hiddenComponents", [])
            if component in MODULE_COMPONENTS[module_id] and component not in REQUIRED_COMPONENTS[module_id]
        }
        module["hiddenComponents"] = [item for item in MODULE_COMPONENTS[module_id] if item in hidden]
        fallback = _legacy_component_rows(module_id, module) if supplied_version < 7 else deepcopy(DEFAULT_COMPONENT_ROWS[module_id])
        raw_module = source.get(module_id) if isinstance(source.get(module_id), dict) else {}
        raw_rows = raw_module.get("componentRows") if supplied_version >= 7 else fallback
        if module_id in {"basics", "education"}:
            raw_rows = deepcopy(DEFAULT_COMPONENT_ROWS[module_id])
        module["componentRows"] = _normalize_component_rows(module_id, raw_rows, fallback, hidden)
        if module_id == "others":
            module["componentRows"] = _normalize_other_component_rows(module["componentRows"])


def normalize_layout_config(value: dict | None) -> dict:
    """Normalize unknown/partial input into the complete current contract."""
    try:
        supplied_version = int(value.get("version", 1)) if isinstance(value, dict) else LAYOUT_SCHEMA_VERSION
    except (TypeError, ValueError):
        supplied_version = 1
    result = default_layout_config()
    if isinstance(value, dict):
        _merge_known(result, value, DEFAULT_LAYOUT_CONFIG)
    result["version"] = LAYOUT_SCHEMA_VERSION

    # v1 的默认排版在中文一页简历中留白过多。仅迁移仍保持旧默认值的
    # 任务，用户主动调整过的字号、行距和间距继续原样保留。
    if supplied_version < 2 and isinstance(value, dict):
        supplied_global = value.get("global") if isinstance(value.get("global"), dict) else {}
        old_defaults = {"fontSize": 11.0, "lineHeight": 1.6, "moduleMargin": 1.0, "marginVertical": 9.0}
        if all(float(supplied_global.get(key, expected)) == expected for key, expected in old_defaults.items()):
            result["global"].update({
                "density": "compact", "fontSize": 10.5, "lineHeight": 1.32,
                "moduleMargin": 0.45, "marginVertical": 8.0,
            })

    # v1-v3 exposed the root CSS size as "fontSize" while most body copy was
    # rendered at 0.8em. v4 makes the control truthful: fontSize is the actual
    # body size, and the remaining hierarchy is resolved as semantic tokens.
    if supplied_version < 4:
        legacy_global = result["global"]
        supplied_global = value.get("global") if isinstance(value, dict) and isinstance(value.get("global"), dict) else {}
        legacy_font_size = float(legacy_global["fontSize"] if "fontSize" in supplied_global else 10.5)
        legacy_global["fontSize"] = (
            9.0 if legacy_font_size == 10.5
            else round(legacy_font_size * 0.8 * 2) / 2
        )
        legacy_line_height = float(legacy_global["lineHeight"] if "lineHeight" in supplied_global else 1.32)
        legacy_module_margin = float(legacy_global["moduleMargin"] if "moduleMargin" in supplied_global else 0.45)
        if legacy_line_height == 1.32:
            legacy_global["lineHeight"] = 1.28
        if legacy_module_margin == 0.45:
            legacy_global["moduleMargin"] = 0.55

    for section, key in ENUMS:
        _enum(result, section, key)

    global_config = result["global"]
    global_config["fontSize"] = _half_point(global_config.get("fontSize"), 8, 11.5, 9)

    # v6 keeps the standard resume density compact enough for the established
    # one-page export baseline. Only the old standard preset value is migrated;
    # other user-defined line heights remain untouched.
    if (
        supplied_version < 6
        and global_config.get("density") == "standard"
        and float(global_config.get("lineHeight", 0)) == 1.35
    ):
        global_config["lineHeight"] = 1.28

    # v5 records every semantic font size explicitly. Existing configurations
    # resolve to exactly the same v4 hierarchy, while global.fontSize remains
    # the backwards-compatible body-size field.
    supplied_typography = (
        value.get("typography")
        if isinstance(value, dict) and isinstance(value.get("typography"), dict)
        else {}
    )
    supplied_font_sizes = supplied_typography.get("fontSizes")
    if supplied_version < 5 or not isinstance(supplied_font_sizes, dict):
        result["typography"]["fontSizes"] = _semantic_font_sizes(global_config["fontSize"])
    font_sizes = result["typography"]["fontSizes"]
    defaults = _semantic_font_sizes(global_config["fontSize"])
    for role, (minimum, maximum) in FONT_SIZE_LIMITS.items():
        font_sizes[role] = _half_point(font_sizes.get(role), minimum, maximum, defaults[role])
    # global.fontSize remains canonical for the body role so older callers that
    # update this field continue to behave as before.
    font_sizes["body"] = global_config["fontSize"]

    # Font names are resolved from a curated preset rather than accepting
    # arbitrary model/user strings. This keeps browser, PDF and DOCX exports on
    # exactly the same known typefaces.
    typography = result["typography"]
    typography.update(deepcopy(TYPOGRAPHY_PRESETS[typography["preset"]]))

    global_config["lineHeight"] = _bounded_number(global_config.get("lineHeight"), 1.0, 1.8, 1.25)
    global_config["moduleMargin"] = _bounded_number(global_config.get("moduleMargin"), 0.1, 1.0, 0.5)
    global_config["marginVertical"] = _bounded_number(global_config.get("marginVertical"), 3, 12, 9)
    global_config["marginHorizontal"] = _bounded_number(global_config.get("marginHorizontal"), 3, 12, 9)
    old_default_order = [
        "education", "skills", "research_interests", "honors", "publications",
        "work_experience", "project_experience", "custom_sections", "others", "self_evaluation",
    ]
    if supplied_version < 8 and global_config.get("sectionOrder") == old_default_order:
        global_config["sectionOrder"] = list(DEFAULT_LAYOUT_CONFIG["global"]["sectionOrder"])
    order = list(dict.fromkeys(
        item for item in global_config.get("sectionOrder", []) if _is_valid_section_id(item)
    ))
    required = list(SECTION_IDS)
    has_custom_section_modules = any(is_custom_section_module(item) for item in order)
    insertion_points = {
        "honors": "education",
        "publications": "honors",
        "research_interests": "publications",
        "skills": "research_interests",
        "custom_sections": "project_experience",
    }
    for item in required:
        if item == "custom_sections" and has_custom_section_modules:
            continue
        if item in order:
            continue
        anchor = insertion_points.get(item)
        if anchor in order:
            order.insert(order.index(anchor) + 1, item)
        else:
            order.append(item)
    global_config["sectionOrder"] = order
    global_config["hiddenSections"] = list(dict.fromkeys(
        item for item in global_config.get("hiddenSections", []) if _is_valid_section_id(item)
    ))
    supplied_global_config = value.get("global") if isinstance(value, dict) and isinstance(value.get("global"), dict) else {}
    title_overrides = supplied_global_config.get("titleOverrides", global_config.get("titleOverrides"))
    clean_titles = {}
    if isinstance(title_overrides, dict):
        for section, translations in title_overrides.items():
            if section not in SECTION_IDS or not isinstance(translations, dict):
                continue
            clean = {
                language: str(text).strip()[:40]
                for language, text in translations.items()
                if language in {"zh", "en"} and str(text).strip()
            }
            if clean:
                clean_titles[section] = clean
    global_config["titleOverrides"] = clean_titles

    for section, allowed in ALLOWED_HIDDEN_FIELDS.items():
        key = "hiddenMetrics" if section == "education" else "hiddenFields"
        result[section][key] = list(dict.fromkeys(
            item for item in result[section].get(key, []) if item in allowed
        ))

    basics = result["basics"]
    supplied_basics = value.get("basics") if isinstance(value, dict) and isinstance(value.get("basics"), dict) else {}
    basics["photoWidthMm"] = _bounded_number(basics.get("photoWidthMm"), 15, 30, 21)
    basics["photoHeightMm"] = _bounded_number(
        basics.get("photoHeightMm") if "photoHeightMm" in supplied_basics else basics["photoWidthMm"] * 26 / 21,
        18, 45, 26,
    )
    if basics["photoPosition"] == "hidden" and "photo" not in basics["hiddenFields"]:
        basics["hiddenFields"].append("photo")
    if "photo" in basics["hiddenFields"]:
        basics["photoPosition"] = "hidden"

    others = result["others"]
    fields = [item for item in others.get("fieldOrder", []) if item in ALLOWED_HIDDEN_FIELDS["others"]]
    for item in ("skills", "certificates", "languages"):
        if item not in fields:
            fields.append(item)
    others["fieldOrder"] = fields

    for key in ("showJobType",):
        result["work_experience"][key] = bool(result["work_experience"].get(key))
    for key in ("showRole", "showDate"):
        result["project_experience"][key] = bool(result["project_experience"].get(key))
    placements = supplied_global_config.get("sectionPlacements", global_config.get("sectionPlacements"))
    placements = placements if isinstance(placements, dict) else {}
    global_config["sectionPlacements"] = {
        section: "education"
        for section in ("research_interests", "honors", "publications", "others")
        if placements.get(section) == "education"
    }

    # Education supplement and modules merged into education have their own
    # sibling order.  Older layouts had no persisted child list, so derive the
    # merged-module portion from the existing top-level order while keeping the
    # supplement at the top as the established default.
    supplied_education = value.get("education") if isinstance(value, dict) and isinstance(value.get("education"), dict) else {}
    supplied_child_order = supplied_education.get("childSectionOrder")
    if isinstance(supplied_child_order, list):
        child_order = [
            item for item in dict.fromkeys(supplied_child_order)
            if item in EDUCATION_CHILD_SECTION_IDS
        ]
    else:
        child_order = ["education_supplement"] + [
            item for item in global_config["sectionOrder"]
            if item in EDUCATION_CHILD_SECTION_IDS and item != "education_supplement"
        ]
    for item in EDUCATION_CHILD_SECTION_IDS:
        if item not in child_order:
            child_order.append(item)
    result["education"]["childSectionOrder"] = child_order

    for section in ("skills", "research_interests", "honors", "publications", "custom_sections", "self_evaluation"):
        allowed_styles = {"paragraph", "bullet", "numbered"}
        if result[section].get("listStyle") not in allowed_styles:
            result[section]["listStyle"] = DEFAULT_LAYOUT_CONFIG[section]["listStyle"]
    _normalize_module_contract(result, value, supplied_version)
    return result


def resolve_module_layout(config: dict | None, module_id: str) -> dict[str, Any]:
    """Resolve one module without introducing a second line-height source."""
    normalized = normalize_layout_config(config)
    resolved_module_id = "custom_sections" if is_custom_section_module(module_id) else module_id
    if resolved_module_id not in MODULE_COMPONENTS:
        raise KeyError(module_id)
    module = deepcopy(normalized[resolved_module_id])
    module["resolvedTitleStyle"] = module["titleStyle"] or normalized["global"]["titleStyle"]
    module["resolvedTitleAlignment"] = module["titleAlignment"] or "left"
    module["resolvedLineHeight"] = normalized["global"]["lineHeight"]
    return module


def component_position(config: dict | None, module_id: str, component_id: str) -> tuple[int, int] | None:
    module = resolve_module_layout(config, module_id)
    if component_id in module["hiddenComponents"]:
        return None
    for row_index, row in enumerate(module["componentRows"]):
        for cell_index, cell in enumerate(row["cells"]):
            if component_id in cell["components"]:
                return row_index, cell_index
    return None


def resolve_layout_tokens(config: dict | None = None, style: dict | None = None) -> dict[str, Any]:
    """Resolve renderer-independent typography and spacing values.

    The persisted configuration keeps user-friendly multipliers (for example
    ``moduleMargin``). Renderers consume the physical point/mm values returned
    here so browser preview, Chromium PDF and Word do not invent separate formulas.
    """
    normalized = normalize_layout_config(config)
    global_config = normalized["global"]
    typography = normalized["typography"]
    overrides = style if isinstance(style, dict) else {}

    font_size = _bounded_number(overrides.get("fontSize", global_config["fontSize"]), 8, 11.5, global_config["fontSize"])
    line_height = _bounded_number(overrides.get("lineHeight", global_config["lineHeight"]), 1.0, 1.8, global_config["lineHeight"])
    module_margin = _bounded_number(overrides.get("moduleMargin", global_config["moduleMargin"]), 0.1, 1.0, global_config["moduleMargin"])
    font_sizes = typography["fontSizes"]
    body_font_size = font_size
    meta_font_size = font_sizes["meta"]
    entry_title_font_size = font_sizes["entryTitle"]
    section_title_font_size = font_sizes["sectionTitle"]
    name_font_size = font_sizes["name"]
    label_font_size = font_sizes["label"]

    return {
        "fontPreset": typography["preset"],
        "latinFont": typography["latinFont"],
        "eastAsiaFont": typography["eastAsiaFont"],
        "latinFallbackFonts": deepcopy(typography["latinFallbackFonts"]),
        "fallbackFonts": deepcopy(typography["fallbackFonts"]),
        "fontFamilyCss": ", ".join([
            f'"{typography["latinFont"]}"',
            *(f'"{font}"' for font in typography["latinFallbackFonts"]),
            f'"{typography["eastAsiaFont"]}"',
            *(f'"{font}"' if font != "sans-serif" else font for font in typography["fallbackFonts"]),
        ]),
        "fontSizePt": font_size,
        "bodyFontSizePt": body_font_size,
        "metaFontSizePt": meta_font_size,
        "entryTitleFontSizePt": entry_title_font_size,
        "sectionTitleFontSizePt": section_title_font_size,
        "nameFontSizePt": name_font_size,
        "labelFontSizePt": label_font_size,
        "bodyFontWeight": 400,
        "metaFontWeight": 400,
        "entryTitleFontWeight": 700,
        "sectionTitleFontWeight": 700,
        "nameFontWeight": 700,
        "labelFontWeight": 700,
        "letterSpacingPt": 0.0,
        "lineHeight": line_height,
        "bodyLineHeightPt": body_font_size * line_height,
        "metaLineHeightPt": meta_font_size * line_height,
        "entryTitleLineHeightPt": entry_title_font_size * line_height,
        "sectionTitleLineHeightPt": section_title_font_size * line_height,
        "nameLineHeightPt": name_font_size * line_height,
        "moduleMargin": module_margin,
        "moduleSpacingPt": font_size * module_margin,
        "headerNameAfterPt": body_font_size * 0.27,
        "sectionTitleAfterPt": body_font_size * 0.25,
        "sectionTitleBorderGapPt": section_title_font_size * 0.1,
        "itemSpacingPt": body_font_size * 0.22,
        "paragraphSpacingPt": body_font_size * 0.09,
        "contentBlockSpacingPt": body_font_size * 0.14,
        "contentLabelSpacingPt": body_font_size * 0.06,
        "numberedItemSpacingPt": body_font_size * 0.08,
        # All body lists share one text column. Markers may differ, but the
        # first character and every wrapped line begin at this physical point.
        "listTextIndentPt": body_font_size * 1.55,
        "listMarkerGapPt": body_font_size * 0.25,
        "educationMiddleMinMm": 30.0,
        "educationColumnBreathingMm": 4.0,
        # photoWidthMm is retained for old layout clients. The actual width is
        # derived by each renderer from photoHeightMm and the imported image
        # aspect ratio.
        "photoWidthMm": normalized["basics"]["photoWidthMm"],
        "photoHeightMm": normalized["basics"]["photoHeightMm"],
        "marginTopMm": _bounded_number(overrides.get("marginTop", global_config["marginVertical"]), 3, 12, global_config["marginVertical"]),
        "marginBottomMm": _bounded_number(overrides.get("marginBottom", global_config["marginVertical"]), 3, 12, global_config["marginVertical"]),
        "marginLeftMm": _bounded_number(overrides.get("marginLeft", global_config["marginHorizontal"]), 3, 12, global_config["marginHorizontal"]),
        "marginRightMm": _bounded_number(overrides.get("marginRight", global_config["marginHorizontal"]), 3, 12, global_config["marginHorizontal"]),
        "modules": {
            module_id: {
                "paragraphSpacingPt": body_font_size * normalized[module_id]["paragraphSpacing"],
                "itemSpacingPt": body_font_size * normalized[module_id]["itemSpacing"],
                "contentBlockSpacingPt": body_font_size * normalized[module_id]["contentBlockSpacing"],
                "rowSpacingPt": body_font_size * normalized[module_id]["rowSpacing"],
                "indentPt": body_font_size * 1.55 * normalized[module_id]["indentLevel"],
            }
            for module_id in MODULE_COMPONENTS
        },
    }


def estimate_text_width_pt(value: object, font_size_pt: float) -> float:
    """Estimate one unbroken label using shared Latin/East Asian metrics.

    The result is not used to lay out body prose.  It only chooses a stable
    physical width for the centered education metadata group before all three
    renderers perform their own final glyph shaping.
    """
    units = 0.0
    for char in str(value or ""):
        codepoint = ord(char)
        if (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0xFF00 <= codepoint <= 0xFFEF
        ):
            units += 1.0
        elif char.isspace():
            units += 0.28
        elif char.isupper():
            units += 0.62
        elif char.islower():
            units += 0.52
        elif char.isdigit():
            units += 0.56
        else:
            units += 0.35
    return units * float(font_size_pt)


def resolve_education_column_widths(
    tokens: dict[str, Any],
    *,
    schools: list[str],
    dates: list[str],
    degree_majors: list[str],
    compact_metrics: list[str],
) -> dict[str, float]:
    """Resolve the content-led middle column, then split remaining width equally."""
    printable_mm = 210.0 - tokens["marginLeftMm"] - tokens["marginRightMm"]
    label_size = tokens["labelFontSizePt"]
    entry_size = tokens["entryTitleFontSizePt"]
    breathing_mm = tokens["educationColumnBreathingMm"]

    # Determine the middle column from its own field-label content first. The
    # side columns only constrain it when preserving their minimum readable
    # width would otherwise be impossible. This keeps degree/major/metrics
    # together as the dominant width decision, while always leaving equal
    # widths on the left and right.
    middle_needed_mm = tokens["educationMiddleMinMm"]
    for degree_major, metric in zip(degree_majors, compact_metrics):
        display_value = f"{degree_major} · {metric}" if metric else degree_major
        width_pt = estimate_text_width_pt(display_value, label_size) * 1.08
        middle_needed_mm = max(middle_needed_mm, width_pt * 25.4 / 72.0 + breathing_mm)

    side_needed_mm = max(
        36.0,
        max((estimate_text_width_pt(value, entry_size) for value in schools), default=0.0) * 25.4 / 72.0,
        max((estimate_text_width_pt(value, label_size) for value in dates), default=0.0) * 25.4 / 72.0,
    ) + breathing_mm

    # Keep the middle content-led width whenever possible. If the requested
    # middle width cannot coexist with both side minima, reduce it only to the
    # remaining width after reserving those side minima; unavoidable extreme
    # cases still retain the configured middle minimum.
    middle_max_mm = max(tokens["educationMiddleMinMm"], printable_mm - side_needed_mm * 2)
    middle_mm = min(middle_needed_mm, middle_max_mm)
    side_mm = max(0.0, (printable_mm - middle_mm) / 2.0)
    return {
        "sideMm": side_mm,
        "middleMm": middle_mm,
    }


def resolve_photo_height_mm(
    resume_data: dict[str, Any] | None,
    config: dict[str, Any] | None,
    tokens: dict[str, Any],
    *,
    photo_present: bool | None = None,
) -> float:
    """Keep a top-right photo inside the first header-to-section frame.

    The photo is absolutely positioned, so it must not create a blank header
    simply because its configured height is larger than the basic-information
    text. Estimate the same first-section frame used by the renderers and cap
    only the height; width remains derived from the imported aspect ratio.
    """
    data = resume_data if isinstance(resume_data, dict) else {}
    basics = data.get("basics") if isinstance(data.get("basics"), dict) else {}
    if photo_present is None:
        photo_present = bool(basics.get("photo"))
    desired = float(tokens.get("photoHeightMm") or 26.0)
    if not photo_present:
        return desired

    layout = normalize_layout_config(config)
    global_config = layout["global"]
    hidden = set(global_config.get("hiddenSections") or [])
    others = data.get("others") if isinstance(data.get("others"), dict) else {}
    has_values = lambda value: isinstance(value, list) and any(str(item or "").strip() for item in value)

    def section_has_content(section: str) -> bool:
        custom_index = custom_section_index(section)
        if custom_index is not None:
            custom_sections = data.get("custom_sections") or []
            if custom_index >= len(custom_sections) or not isinstance(custom_sections[custom_index], dict):
                return False
            custom = custom_sections[custom_index]
            return bool(str(custom.get("title") or "").strip()) and has_values(custom.get("items"))
        if section == "education":
            return bool(data.get("education"))
        if section == "skills":
            return has_values(others.get("skills"))
        if section in {"research_interests", "honors", "publications", "self_evaluation"}:
            return has_values(data.get(section))
        if section == "work_experience":
            return bool(data.get("work_experience"))
        if section == "project_experience":
            return bool(data.get("project_experience"))
        if section == "custom_sections":
            return any(
                isinstance(item, dict)
                and str(item.get("title") or "").strip()
                and has_values(item.get("items"))
                for item in (data.get("custom_sections") or [])
            )
        if section == "others":
            return any(has_values(others.get(key)) for key in ("certificates", "languages"))
        return False

    if not any(
        section_has_content(section)
        and section not in hidden
        and (not is_custom_section_module(section) or "custom_sections" not in hidden)
        for section in global_config.get("sectionOrder") or []
    ):
        return desired

    printable_width_pt = max(1.0, (210.0 - tokens["marginLeftMm"] - tokens["marginRightMm"]) * 72.0 / 25.4)
    try:
        ratio = float(basics.get("photo_aspect_ratio") or 21.0 / 26.0)
    except (TypeError, ValueError):
        ratio = 21.0 / 26.0
    ratio = min(3.0, max(0.2, ratio))
    photo_width_pt = desired * ratio * 72.0 / 25.4
    text_width_pt = max(120.0, printable_width_pt - photo_width_pt)

    def line_count(value: object, font_size: float) -> int:
        text = str(value or "").replace("**", "").strip()
        if not text:
            return 0
        return max(1, math.ceil(estimate_text_width_pt(text, font_size) / text_width_pt))

    name_lines = line_count(basics.get("name"), tokens["nameFontSizePt"])
    target_lines = line_count(basics.get("target_position"), tokens["metaFontSizePt"])
    contact_values = [basics.get(key) for key in ("gender", "birth_date", "phone", "email")]
    contact_values.extend(
        item.get("label") or item.get("value")
        for item in (basics.get("additional_fields") or [])
        if isinstance(item, dict) and (item.get("label") or item.get("value"))
    )
    contact_lines = line_count(" | ".join(str(value) for value in contact_values if value), tokens["metaFontSizePt"])
    header_pt = (
        name_lines * tokens["nameLineHeightPt"]
        + (tokens["headerNameAfterPt"] if name_lines else 0)
        + target_lines * tokens["metaLineHeightPt"]
        + contact_lines * tokens["metaLineHeightPt"]
        # Include the next section title line so the photo reaches the divider
        # instead of ending at the bottom of the text header.  A small fixed
        # gap below the image keeps it visually clear of the rule.
        + tokens["moduleSpacingPt"]
        + tokens["bodyFontSizePt"] * 0.35
        + tokens["sectionTitleLineHeightPt"]
    )
    # Keep a physical safety gap so renderer-specific font rasterization and
    # Word table row boxes cannot let the image touch or overlap the divider.
    available_mm = header_pt * 25.4 / 72.0 - PHOTO_BOTTOM_GAP_MM
    return round(max(10.0, min(desired, available_mm)), 2)


def apply_density(config: dict, density: str) -> dict:
    result = normalize_layout_config(config)
    if density not in DENSITY_VALUES:
        return result
    result["global"]["density"] = density
    result["global"].update(DENSITY_VALUES[density])
    result["typography"]["fontSizes"] = _semantic_font_sizes(DENSITY_VALUES[density]["fontSize"])
    return normalize_layout_config(result)


def build_layout_changes(before: dict | None, after: dict | None) -> list[dict]:
    """Build module-level atomic confirmation groups."""
    old = normalize_layout_config(before)
    new = normalize_layout_config(after)
    changes = []
    for section in ("global", *MODULE_COMPONENTS):
        typography_changed = section == "global" and old["typography"] != new["typography"]
        if old[section] == new[section] and not typography_changed:
            continue
        details = []
        for key in sorted(set(old[section]) | set(new[section])):
            if old[section].get(key) == new[section].get(key):
                continue
            before_value = old[section].get(key)
            after_value = new[section].get(key)
            details.append({
                "field": key,
                "field_label": FIELD_LABELS.get((section, key), key),
                "before": before_value,
                "after": after_value,
                "before_display": _display_layout_value(before_value, key),
                "after_display": _display_layout_value(after_value, key),
            })
        if typography_changed:
            before_value = old["typography"]["fontSizes"]
            after_value = new["typography"]["fontSizes"]
            details.append({
                "field": "typography.fontSizes",
                "field_label": FIELD_LABELS[("typography", "fontSizes")],
                "before": before_value,
                "after": after_value,
                "before_display": _display_layout_value(before_value),
                "after_display": _display_layout_value(after_value),
            })
        changes.append({
            "id": f"layout-{section}",
            "kind": "layout",
            "module": section,
            "label": f"{MODULE_LABELS[section]}布局",
            "details": details,
        })
    return changes


def apply_layout_change_groups(base: dict | None, candidate: dict | None, selected_ids: list[str]) -> dict:
    old = normalize_layout_config(base)
    new = normalize_layout_config(candidate)
    selected = set(selected_ids)
    for section in ("global", *MODULE_COMPONENTS):
        if f"layout-{section}" in selected:
            old[section] = deepcopy(new[section])
            if section == "global":
                # Density/template changes and their semantic type scale are
                # one atomic visual decision during confirmation.
                old["typography"] = deepcopy(new["typography"])
    return normalize_layout_config(old)


def reset_layout_section(config: dict | None, section: str | None = None) -> dict:
    result = normalize_layout_config(config)
    if not section or section == "all":
        return default_layout_config()
    if section not in DEFAULT_LAYOUT_CONFIG or section == "version":
        return result
    result[section] = deepcopy(DEFAULT_LAYOUT_CONFIG[section])
    return normalize_layout_config(result)
