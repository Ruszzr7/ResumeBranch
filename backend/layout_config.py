"""Versioned, deterministic resume layout configuration.

The conversation model may choose values from this contract, but renderers only
consume normalized values from this module.  Arbitrary CSS/HTML is never stored.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


LAYOUT_SCHEMA_VERSION = 2

SECTION_IDS = (
    "education",
    "skills",
    "research_interests",
    "honors",
    "work_experience",
    "internship_experience",
    "project_experience",
    "custom_sections",
    "others",
    "self_evaluation",
)

DEFAULT_LAYOUT_CONFIG: dict[str, Any] = {
    "version": LAYOUT_SCHEMA_VERSION,
    "global": {
        "density": "compact",
        "fontSize": 10.5,
        "lineHeight": 1.32,
        "moduleMargin": 0.45,
        "marginVertical": 8.0,
        "marginHorizontal": 9.0,
        "titleStyle": "underline",
        "sectionOrder": [
            "education",
            "skills",
            "research_interests",
            "honors",
            "work_experience",
            "project_experience",
            "custom_sections",
            "others",
            "self_evaluation",
        ],
        "hiddenSections": [],
        "splitWorkExperience": False,
        "titleOverrides": {},
    },
    "basics": {
        "preset": "centered",
        "contactLayout": "inline",
        "photoPosition": "right",
        "hiddenFields": [],
    },
    "education": {
        "preset": "classic",
        "schoolTagStyle": "filled",
        "metricsPlacement": "below",
        "hiddenMetrics": [],
        "thesisDisplay": "expanded",
    },
    "work_experience": {
        "preset": "classic",
        "detailsStyle": "bullets",
        "datePosition": "right",
        "showJobType": True,
    },
    "project_experience": {
        "preset": "classic",
        "detailsStyle": "bullets",
        "datePosition": "right",
        "showRole": True,
        "showDate": True,
    },
    "others": {
        "preset": "inline",
        "fieldOrder": ["certificates", "languages"],
        "hiddenFields": [],
        "separator": "pipe",
    },
    "self_evaluation": {
        "preset": "paragraphs",
    },
}

DENSITY_VALUES = {
    "compact": {"fontSize": 10.5, "lineHeight": 1.32, "moduleMargin": 0.45},
    "standard": {"fontSize": 10.5, "lineHeight": 1.42, "moduleMargin": 0.65},
    "comfortable": {"fontSize": 11.0, "lineHeight": 1.55, "moduleMargin": 0.9},
}

LAYOUT_TEMPLATES = {
    "classic-professional": {
        "label": "经典专业",
        "density": "standard",
        "global": {"titleStyle": "underline", "marginVertical": 10.0, "marginHorizontal": 10.0},
        "basics": {"preset": "centered", "contactLayout": "inline"},
        "education": {"preset": "classic", "schoolTagStyle": "outline", "metricsPlacement": "below"},
        "work_experience": {"preset": "classic", "detailsStyle": "bullets", "datePosition": "right"},
        "project_experience": {"preset": "classic", "detailsStyle": "bullets", "datePosition": "right"},
        "others": {"preset": "inline", "separator": "dot"},
        "self_evaluation": {"preset": "paragraphs"},
    },
    "modern-clean": {
        "label": "简洁现代",
        "density": "standard",
        "global": {"titleStyle": "plain", "marginVertical": 10.0, "marginHorizontal": 10.0},
        "basics": {"preset": "left-aligned", "contactLayout": "inline"},
        "education": {"preset": "three-column", "schoolTagStyle": "text", "metricsPlacement": "info-column"},
        "work_experience": {"preset": "classic", "detailsStyle": "bullets", "datePosition": "right"},
        "project_experience": {"preset": "classic", "detailsStyle": "bullets", "datePosition": "right"},
        "others": {"preset": "inline", "separator": "dot"},
        "self_evaluation": {"preset": "paragraphs"},
    },
    "compact-tech": {
        "label": "紧凑技术",
        "density": "compact",
        "global": {"titleStyle": "plain", "marginVertical": 8.5, "marginHorizontal": 9.0},
        "basics": {"preset": "left-aligned", "contactLayout": "inline"},
        "education": {"preset": "compact", "schoolTagStyle": "outline", "metricsPlacement": "with-degree"},
        "work_experience": {"preset": "compact", "detailsStyle": "bullets", "datePosition": "right"},
        "project_experience": {"preset": "compact", "detailsStyle": "bullets", "datePosition": "right"},
        "others": {"preset": "tags", "separator": "dot"},
        "self_evaluation": {"preset": "compact"},
    },
}

ENUMS = {
    ("global", "density"): set(DENSITY_VALUES),
    ("global", "titleStyle"): {"underline", "plain"},
    ("basics", "preset"): {"centered", "left-aligned"},
    ("basics", "contactLayout"): {"inline", "stacked"},
    ("basics", "photoPosition"): {"right", "hidden"},
    ("education", "preset"): {"classic", "compact", "three-column"},
    ("education", "schoolTagStyle"): {"filled", "outline", "text", "hidden"},
    ("education", "metricsPlacement"): {"below", "with-degree", "info-column"},
    ("education", "thesisDisplay"): {"expanded", "compact", "hidden"},
    ("work_experience", "preset"): {"classic", "compact"},
    ("work_experience", "detailsStyle"): {"bullets", "paragraph"},
    ("work_experience", "datePosition"): {"right", "inline"},
    ("project_experience", "preset"): {"classic", "compact"},
    ("project_experience", "detailsStyle"): {"bullets", "paragraph"},
    ("project_experience", "datePosition"): {"right", "inline"},
    ("others", "preset"): {"inline", "tags", "stacked"},
    ("others", "separator"): {"pipe", "dot"},
    ("self_evaluation", "preset"): {"paragraphs", "bullets", "compact"},
}

ALLOWED_HIDDEN_FIELDS = {
    "basics": {"gender", "birth_date", "phone", "email", "target_position", "photo", "additional_fields"},
    "education": {"gpa", "ranking", "average_score"},
    "others": {"skills", "certificates", "languages"},
}

MODULE_LABELS = {
    "global": "全局排版",
    "basics": "基本信息",
    "education": "教育经历",
    "skills": "专业技能",
    "research_interests": "研究方向",
    "honors": "主要荣誉",
    "work_experience": "工作/实习经历",
    "project_experience": "项目经历",
    "custom_sections": "自定义栏目",
    "others": "其他信息",
    "self_evaluation": "自我评价",
}

VALUE_LABELS = {
    "compact": "紧凑", "standard": "标准", "comfortable": "舒展",
    "underline": "强调标题", "plain": "简洁标题",
    "centered": "居中式", "left-aligned": "左对齐式",
    "inline": "同行", "stacked": "纵向", "right": "右侧", "hidden": "隐藏",
    "classic": "经典", "three-column": "三列", "filled": "实心标签",
    "outline": "描边标签", "text": "普通文字", "below": "独立下一行",
    "with-degree": "与学历专业同行", "info-column": "信息列",
    "expanded": "完整展示", "bullets": "圆点列表", "paragraph": "普通段落",
    "paragraphs": "分段", "tags": "标签", "pipe": "竖线分隔", "dot": "圆点分隔",
}

FIELD_LABELS = {
    ("global", "density"): "整体密度",
    ("global", "fontSize"): "字体大小",
    ("global", "lineHeight"): "行间距",
    ("global", "moduleMargin"): "模块间距",
    ("global", "marginVertical"): "上下页边距",
    ("global", "marginHorizontal"): "左右页边距",
    ("global", "titleStyle"): "模块标题样式",
    ("global", "sectionOrder"): "模块顺序",
    ("global", "hiddenSections"): "隐藏模块",
    ("global", "splitWorkExperience"): "工作与实习拆分",
    ("global", "titleOverrides"): "模块标题名称",
    ("basics", "preset"): "基本信息布局",
    ("basics", "contactLayout"): "联系方式排列",
    ("basics", "photoPosition"): "照片位置",
    ("basics", "hiddenFields"): "隐藏字段",
    ("education", "preset"): "教育信息布局",
    ("education", "schoolTagStyle"): "学校标签样式",
    ("education", "metricsPlacement"): "成绩信息位置",
    ("education", "hiddenMetrics"): "隐藏成绩项",
    ("education", "thesisDisplay"): "论文展示方式",
    ("work_experience", "preset"): "工作经历布局",
    ("work_experience", "detailsStyle"): "工作描述样式",
    ("work_experience", "datePosition"): "工作日期位置",
    ("work_experience", "showJobType"): "显示工作类型",
    ("project_experience", "preset"): "项目经历布局",
    ("project_experience", "detailsStyle"): "项目描述样式",
    ("project_experience", "datePosition"): "项目日期位置",
    ("project_experience", "showRole"): "显示项目角色",
    ("project_experience", "showDate"): "显示项目日期",
    ("others", "preset"): "其他信息布局",
    ("others", "fieldOrder"): "信息顺序",
    ("others", "hiddenFields"): "隐藏字段",
    ("others", "separator"): "信息分隔符",
    ("self_evaluation", "preset"): "自我评价布局",
}

ITEM_LABELS = {
    **MODULE_LABELS,
    "internship_experience": "实习经历",
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
    "average_score": "平均分",
}


def _display_layout_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "、".join(ITEM_LABELS.get(str(item), VALUE_LABELS.get(str(item), str(item))) for item in value) or "无"
    if isinstance(value, dict):
        return "、".join(f"{ITEM_LABELS.get(str(key), str(key))}：{item}" for key, item in value.items()) or "无"
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


def normalize_layout_config(value: dict | None) -> dict:
    """Normalize unknown/partial input into the complete v1 contract."""
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

    for section, key in ENUMS:
        _enum(result, section, key)

    global_config = result["global"]
    global_config["fontSize"] = _bounded_number(global_config.get("fontSize"), 9, 14, 11)
    global_config["lineHeight"] = _bounded_number(global_config.get("lineHeight"), 1.1, 2.2, 1.6)
    global_config["moduleMargin"] = _bounded_number(global_config.get("moduleMargin"), 0.25, 2, 1)
    global_config["marginVertical"] = _bounded_number(global_config.get("marginVertical"), 3, 12, 9)
    global_config["marginHorizontal"] = _bounded_number(global_config.get("marginHorizontal"), 3, 12, 9)
    global_config["splitWorkExperience"] = bool(global_config.get("splitWorkExperience"))

    order = [item for item in global_config.get("sectionOrder", []) if item in SECTION_IDS]
    if not global_config["splitWorkExperience"]:
        order = [item for item in order if item != "internship_experience"]
    elif "internship_experience" not in order:
        work_index = order.index("work_experience") + 1 if "work_experience" in order else 0
        order.insert(work_index, "internship_experience")
    required = [item for item in SECTION_IDS if item != "internship_experience" or global_config["splitWorkExperience"]]
    insertion_points = {
        "skills": "education",
        "research_interests": "skills",
        "honors": "research_interests",
        "custom_sections": "project_experience",
    }
    for item in required:
        if item in order:
            continue
        anchor = insertion_points.get(item)
        if anchor in order:
            order.insert(order.index(anchor) + 1, item)
        else:
            order.append(item)
    global_config["sectionOrder"] = order
    global_config["hiddenSections"] = list(dict.fromkeys(
        item for item in global_config.get("hiddenSections", []) if item in SECTION_IDS
    ))
    title_overrides = global_config.get("titleOverrides")
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
    if basics["photoPosition"] == "hidden" and "photo" not in basics["hiddenFields"]:
        basics["hiddenFields"].append("photo")
    if "photo" in basics["hiddenFields"]:
        basics["photoPosition"] = "hidden"

    education = result["education"]
    if education["preset"] == "three-column":
        education["metricsPlacement"] = "info-column"
    elif education["metricsPlacement"] == "info-column":
        education["metricsPlacement"] = "below" if education["preset"] == "classic" else "with-degree"

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
    return result


def apply_density(config: dict, density: str) -> dict:
    result = normalize_layout_config(config)
    if density not in DENSITY_VALUES:
        return result
    result["global"]["density"] = density
    result["global"].update(DENSITY_VALUES[density])
    return normalize_layout_config(result)


def apply_layout_template(config: dict | None, template_id: str) -> dict:
    """Apply a curated visual bundle while preserving content visibility and section order."""
    template = LAYOUT_TEMPLATES.get(template_id)
    if template is None:
        return normalize_layout_config(config)
    result = apply_density(config or {}, template["density"])
    for section in ("global", "basics", "education", "work_experience", "project_experience", "others", "self_evaluation"):
        result[section].update(deepcopy(template.get(section, {})))
    return normalize_layout_config(result)


def layout_digest_payload(config: dict | None) -> dict:
    return normalize_layout_config(config)


def build_layout_changes(before: dict | None, after: dict | None) -> list[dict]:
    """Build module-level atomic confirmation groups."""
    old = normalize_layout_config(before)
    new = normalize_layout_config(after)
    changes = []
    for section in ("global", "basics", "education", "work_experience", "project_experience", "others", "self_evaluation"):
        if old[section] == new[section]:
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
    for section in ("global", "basics", "education", "work_experience", "project_experience", "others", "self_evaluation"):
        if f"layout-{section}" in selected:
            old[section] = deepcopy(new[section])
    return normalize_layout_config(old)


def reset_layout_section(config: dict | None, section: str | None = None) -> dict:
    result = normalize_layout_config(config)
    if not section or section == "all":
        return default_layout_config()
    if section not in DEFAULT_LAYOUT_CONFIG or section == "version":
        return result
    result[section] = deepcopy(DEFAULT_LAYOUT_CONFIG[section])
    return normalize_layout_config(result)
