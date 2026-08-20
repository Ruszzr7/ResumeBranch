"""Single source of truth for the layout abilities exposed to the model.

The persisted layout schema is deliberately richer than the set of layout
changes that can be safely requested from a conversation.  This module keeps
those two concerns explicit:

* the capability manifest tells the model what the renderer and the UI can
  actually express;
* the validator rejects a structured edit that falls outside that manifest.

It imports the schema constants instead of copying their enum values, so a
schema change cannot silently leave the prompt and the edit boundary out of
sync.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .layout_config import (
    ALLOWED_HIDDEN_FIELDS,
    ENUMS,
    MODULE_COMPONENTS,
    MODULE_LABELS,
    SECTION_IDS,
    normalize_layout_config,
)


LAYOUT_CAPABILITY_VERSION = "1"

# These are the paths that the conversation edit skill may mutate.  The
# remaining normalized fields are renderer state or compatibility fields and
# are intentionally read-only to the conversation model.
EDITABLE_GLOBAL_FIELDS = {
    "density",
    "lineHeight",
    "moduleMargin",
    "marginVertical",
    "marginHorizontal",
    "titleStyle",
    "sectionOrder",
    "hiddenSections",
    "splitWorkExperience",
    "titleOverrides",
    "sectionPlacements",
}

EDITABLE_MODULE_FIELDS: dict[str, set[str]] = {
    "basics": {"preset", "contactLayout", "photoPosition", "photoHeightMm", "hiddenFields"},
    "education": {
        "preset", "schoolTagStyle", "metricsPlacement", "hiddenMetrics",
        "thesisDisplay", "supplementListStyle",
    },
    "skills": {"listStyle"},
    "research_interests": {"listStyle"},
    "honors": {"listStyle"},
    "publications": {"listStyle"},
    "work_experience": {"preset", "detailsStyle", "datePosition", "showJobType"},
    "internship_experience": {"preset", "detailsStyle", "datePosition", "showJobType"},
    "project_experience": {"preset", "detailsStyle", "datePosition", "showRole", "showDate"},
    "custom_sections": {"listStyle"},
    "others": {"preset", "fieldOrder", "hiddenFields", "separator"},
    "self_evaluation": {"preset", "listStyle"},
}

# Values for fields whose enum is not represented by layout_config.ENUMS.
EXTRA_ENUMS: dict[tuple[str, str], set[str]] = {
    ("skills", "listStyle"): {"paragraph", "bullet", "numbered"},
    ("research_interests", "listStyle"): {"paragraph", "bullet", "numbered"},
    ("honors", "listStyle"): {"paragraph", "bullet", "numbered"},
    ("publications", "listStyle"): {"paragraph", "bullet", "numbered"},
    ("custom_sections", "listStyle"): {"paragraph", "bullet", "numbered"},
    ("self_evaluation", "listStyle"): {"paragraph", "bullet", "numbered"},
    ("work_experience", "detailsStyle"): {"bullets", "paragraph"},
    ("internship_experience", "detailsStyle"): {"bullets", "paragraph"},
    ("project_experience", "detailsStyle"): {"bullets", "paragraph"},
}

RANGES: dict[tuple[str, str], tuple[float, float]] = {
    ("global", "lineHeight"): (1.0, 1.8),
    ("global", "moduleMargin"): (0.1, 1.0),
    ("global", "marginVertical"): (3.0, 12.0),
    ("global", "marginHorizontal"): (3.0, 12.0),
    ("basics", "photoHeightMm"): (18.0, 45.0),
}

STEPS: dict[tuple[str, str], float] = {
    ("global", "lineHeight"): 0.05,
    ("global", "moduleMargin"): 0.1,
    ("global", "marginVertical"): 0.25,
    ("global", "marginHorizontal"): 0.25,
}

LIST_FIELDS: dict[tuple[str, str], set[str]] = {
    ("global", "sectionOrder"): set(SECTION_IDS),
    ("global", "hiddenSections"): set(SECTION_IDS),
    ("basics", "hiddenFields"): set(ALLOWED_HIDDEN_FIELDS["basics"]),
    ("education", "hiddenMetrics"): set(ALLOWED_HIDDEN_FIELDS["education"]),
    ("others", "fieldOrder"): set(ALLOWED_HIDDEN_FIELDS["others"]),
    ("others", "hiddenFields"): set(ALLOWED_HIDDEN_FIELDS["others"]),
}

OBJECT_FIELDS = {
    ("global", "titleOverrides"),
    ("global", "sectionPlacements"),
}

_PATH_SEGMENT_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<indexes>(?:\[\d+\])*)$")
_INDEX_RE = re.compile(r"\[(\d+)\]")


def _enum_values(section: str, field: str) -> list[str]:
    values = ENUMS.get((section, field), EXTRA_ENUMS.get((section, field), set()))
    return sorted(str(value) for value in values)


def _module_manifest(module_id: str) -> dict[str, Any]:
    fields = sorted(EDITABLE_MODULE_FIELDS.get(module_id, set()))
    values = {
        field: _enum_values(module_id, field)
        for field in fields
        if _enum_values(module_id, field)
    }
    ranges = {
        field: {"min": minimum, "max": maximum}
        for (section, field), (minimum, maximum) in RANGES.items()
        if section == module_id
    }
    return {
        "label": MODULE_LABELS.get(module_id, module_id),
        "components": list(MODULE_COMPONENTS.get(module_id, ())),
        "editable_fields": fields,
        "allowed_values": values,
        "allowed_ranges": ranges,
    }


def build_layout_capability_manifest() -> dict[str, Any]:
    """Return the renderer/UI capability contract as JSON-serializable data."""
    return {
        "capability_version": LAYOUT_CAPABILITY_VERSION,
        "scope": {
            "global": {
                "editable_fields": sorted(EDITABLE_GLOBAL_FIELDS),
                "allowed_values": {
                    field: _enum_values("global", field)
                    for field in sorted(EDITABLE_GLOBAL_FIELDS)
                    if _enum_values("global", field)
                },
                "allowed_ranges": {
                    field: {
                        "min": minimum,
                        "max": maximum,
                        **({"step": STEPS[(section, field)]} if (section, field) in STEPS else {}),
                    }
                    for (section, field), (minimum, maximum) in RANGES.items()
                    if section == "global"
                },
            },
            "modules": {
                module_id: _module_manifest(module_id)
                for module_id in MODULE_COMPONENTS
                if module_id != "typography"
            },
        },
        "content_forms": {
            "paragraph": "一个连续段落；编辑框中的换行保持为左对齐软换行，不产生新分点",
            "bullet": "每个换行条目渲染为一个圆点分点",
            "numbered": "每个换行条目渲染为一个带空格的编号分点",
        },
        "semantic_content_rules": {
            "experience_content": ["introduction", "responsibilities", "generic"],
            "introduction": "项目简介，默认段落",
            "responsibilities": "项目职责，默认编号",
            "generic": "普通内容，默认分点",
            "education_supplement": "教育经历补充，不显示独立模块标题",
            "merged_sections": "并入教育经历的研究方向、主要荣誉、论文、其他信息不再显示自己的顶层标题",
        },
        "module_content_arrangements": {
            "skills": "专业技能支持段落、分点、编号；每个技能条目内部可保留作者输入的换行",
            "research_interests": "研究方向支持段落、分点、编号",
            "honors": "主要荣誉支持段落、分点、编号",
            "publications": "论文支持段落、分点、编号",
            "custom_sections": "自定义栏目内容支持段落、分点、编号",
            "self_evaluation": "自我评价支持段落、分点、编号",
            "work_experience": "工作内容由项目简介、项目职责、普通内容三种内容块组成；职责默认编号，普通内容默认分点",
            "internship_experience": "实习内容由项目简介、项目职责、普通内容三种内容块组成；职责默认编号，普通内容默认分点",
            "project_experience": "项目内容由项目简介、项目职责、普通内容三种内容块组成；职责默认编号，普通内容默认分点",
            "others": "证书和语言各自独立一行，条目之间使用分隔符，不提供长文本换行",
            "education": "教育经历为学校、学历/专业/成绩、日期三栏；教育经历补充使用 education.supplementListStyle",
        },
        "global_rules": [
            "lineHeight 是全局行距；模块不能单独覆盖行距",
            "moduleMargin 是全局模块间距；模块不能单独设置另一份模块间距",
            "titleStyle 是全局统一的模块标题样式",
            "sectionOrder 只排列实际有内容且未并入教育经历的顶层模块",
            "sectionPlacements 只支持独立栏目或并入教育经历",
            "照片位于基本信息右上方，photoHeightMm 控制高度，宽度由原图比例计算",
        ],
        "read_only_layout_state": [
            "typography.fontSizes（字号通过专用排版设置调整）",
            "typography 字体名称与字体文件",
            "global.fontSize（字号通过专用排版设置调整）",
            "basics.photoWidthMm（由导入照片的原始比例与高度计算）",
            "各模块 componentRows（由稳定预设生成，不接受任意坐标）",
            "各模块 paragraphSpacing/itemSpacing/contentBlockSpacing/rowSpacing/indentLevel",
            "version 以及任何未列入 editable_fields 的字段",
        ],
        "unsupported": [
            "任意画布坐标、自由拖拽坐标或 CSS/HTML",
            "任意字体文件、任意字体名称或逐字符字体规则",
            "为某一个模块单独覆盖全局行距或模块间距",
            "创造 schema 未声明的新模块、字段或内容类型",
        ],
    }


def _path_tokens(path: Any) -> tuple[str | int, ...]:
    value = str(path or "").strip()
    if not value or value.startswith("/") or ".." in value or "__" in value:
        raise ValueError("路径无效")
    tokens: list[str | int] = []
    for segment in value.split("."):
        match = _PATH_SEGMENT_RE.fullmatch(segment)
        if not match:
            raise ValueError("路径无效")
        tokens.append(match.group("key"))
        tokens.extend(int(index) for index in _INDEX_RE.findall(match.group("indexes")))
    return tuple(tokens)


def _field_tokens(tokens: tuple[str | int, ...]) -> tuple[str, str] | None:
    if len(tokens) < 2 or not isinstance(tokens[0], str) or not isinstance(tokens[1], str):
        return None
    return tokens[0], tokens[1]


def _validate_number(value: Any, minimum: float, maximum: float, path: str) -> None:
    if isinstance(value, bool):
        raise ValueError(f"{path} 必须是数值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} 必须是数值") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{path} 必须在 {minimum:g} 到 {maximum:g} 之间")
    step = STEPS.get((path.split(".", 1)[0], path.split(".", 1)[1])) if "." in path else None
    if step:
        # Avoid rejecting a value such as 8.5 because of binary floating point
        # representation.  The UI exposes these fields on fixed slider steps.
        origin = minimum
        quotient = (number - origin) / step
        if abs(quotient - round(quotient)) > 1e-6:
            raise ValueError(f"{path} 必须按 {step:g} 的步长设置")


def _validate_list_value(
    section: str,
    field: str,
    value: Any,
    path: str,
    *,
    current_layout: dict[str, Any] | None = None,
) -> None:
    allowed = set(LIST_FIELDS[(section, field)])
    if section == "global" and field == "sectionOrder" and current_layout:
        if not current_layout.get("global", {}).get("splitWorkExperience"):
            allowed.discard("internship_experience")
    if not isinstance(value, list):
        raise ValueError(f"{path} 必须是列表")
    if any(str(item) not in allowed for item in value):
        raise ValueError(f"{path} 含有当前排版不支持的模块或字段")
    if (section, field) in {
        ("global", "sectionOrder"),
        ("global", "hiddenSections"),
    } and len(set(value)) != len(value):
        raise ValueError(f"{path} 不能包含重复项")


def _validate_object_value(section: str, field: str, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{path} 必须是对象")
    if (section, field) == ("global", "titleOverrides"):
        for module_id, translations in value.items():
            if module_id not in SECTION_IDS or not isinstance(translations, dict):
                raise ValueError(f"{path} 含有不支持的模块标题")
            for language, text in translations.items():
                if language not in {"zh", "en"} or not isinstance(text, str) or not text.strip() or len(text.strip()) > 40:
                    raise ValueError(f"{path} 的标题文字无效")
    elif (section, field) == ("global", "sectionPlacements"):
        allowed_modules = {"research_interests", "honors", "publications", "others"}
        if any(module_id not in allowed_modules or placement != "education" for module_id, placement in value.items()):
            raise ValueError(f"{path} 只支持将指定模块并入教育经历")


def _validate_scalar_value(section: str, field: str, value: Any, path: str) -> None:
    enum_values = ENUMS.get((section, field), EXTRA_ENUMS.get((section, field)))
    if enum_values is not None:
        if value not in enum_values:
            raise ValueError(f"{path} 的值不在支持范围内")
        return
    if (section, field) in RANGES:
        _validate_number(value, *RANGES[(section, field)], path)
        return
    if field in {"splitWorkExperience", "showJobType", "showRole", "showDate"}:
        if not isinstance(value, bool):
            raise ValueError(f"{path} 必须是布尔值")
        return
    if field == "photoPosition":
        return


def _validate_path_and_value(
    operation: dict[str, Any],
    *,
    current_layout: dict[str, Any] | None = None,
) -> tuple[str | int, ...]:
    path = str(operation.get("path", "") or "")
    try:
        tokens = _path_tokens(path)
    except ValueError as exc:
        raise ValueError(f"layout_operations 路径无效：{path}") from exc
    field_key = _field_tokens(tokens)
    if field_key is None:
        raise ValueError(f"layout_operations 不支持该路径：{path}")
    section, field = field_key
    if section == "typography":
        raise ValueError("字号和字体由专用排版设置管理，不能通过对话修改")
    if section == "global":
        allowed_fields = EDITABLE_GLOBAL_FIELDS
    elif section in EDITABLE_MODULE_FIELDS:
        allowed_fields = EDITABLE_MODULE_FIELDS[section]
    else:
        raise ValueError(f"layout_operations 不支持该模块：{section}")
    if field not in allowed_fields:
        raise ValueError(f"排版字段“{field}”不属于可执行的对话排版能力")

    operation_name = str(operation.get("op", operation.get("type", "")) or "").lower()
    suffix = tokens[2:]
    if field in {"sectionOrder", "hiddenSections", "hiddenFields", "hiddenMetrics", "fieldOrder"}:
        # A list field may be replaced as a whole or edited by index.  A move
        # operation must target the list itself.
        if (section, field) not in LIST_FIELDS:
            raise ValueError(f"排版列表字段“{path}”不属于可执行能力")
        if operation_name == "move" and suffix:
            raise ValueError(f"移动操作必须作用于完整列表：{path}")
        if suffix and (len(suffix) != 1 or not isinstance(suffix[0], int)):
            raise ValueError(f"排版列表路径无效：{path}")
        if operation_name in {"append", "insert"} and suffix:
            raise ValueError(f"新增操作必须作用于完整列表：{path}")
        if "value" in operation and operation_name in {"set", "replace"} and not suffix:
            _validate_list_value(
                section, field, operation["value"], path,
                current_layout=current_layout,
            )
        elif "value" in operation and operation_name in {"set", "replace"} and suffix:
            allowed = set(LIST_FIELDS[(section, field)])
            if section == "global" and field == "sectionOrder" and current_layout:
                if not current_layout.get("global", {}).get("splitWorkExperience"):
                    allowed.discard("internship_experience")
            if str(operation["value"]) not in allowed:
                raise ValueError(f"{path} 含有当前排版不支持的值")
        elif "value" in operation and operation_name in {"append", "insert"}:
            allowed = set(LIST_FIELDS[(section, field)])
            if section == "global" and field == "sectionOrder" and current_layout:
                if not current_layout.get("global", {}).get("splitWorkExperience"):
                    allowed.discard("internship_experience")
            if str(operation["value"]) not in allowed:
                raise ValueError(f"{path} 含有当前排版不支持的值")
        return tokens
    if (section, field) in OBJECT_FIELDS:
        if operation_name in {"set", "replace"} and not suffix:
            _validate_object_value(section, field, operation.get("value"), path)
        elif suffix:
            if len(suffix) != 2 or not isinstance(suffix[0], str) or not isinstance(suffix[1], str):
                raise ValueError(f"排版对象路径无效：{path}")
            if field == "titleOverrides" and suffix[0] not in SECTION_IDS:
                raise ValueError(f"{path} 含有不支持的模块标题")
            if field == "titleOverrides" and suffix[1] not in {"zh", "en"}:
                raise ValueError(f"{path} 只支持中文或英文标题")
            if field == "sectionPlacements":
                raise ValueError("sectionPlacements 请整体设置，不能写入未知子键")
        return tokens
    if suffix:
        raise ValueError(f"排版字段路径无效：{path}")
    if operation_name in {"set", "replace"} and "value" in operation:
        _validate_scalar_value(section, field, operation["value"], path)
    return tokens


def validate_layout_operations(
    operations: Any,
    current_layout: dict[str, Any] | None = None,
) -> None:
    """Reject layout operations outside the model-visible capability contract.

    Path existence and list index checks remain the responsibility of
    ``resume_edit`` because it owns the generic operation applicator.  This
    function validates the semantic boundary before that applicator runs.
    ``current_layout`` is accepted so callers can use the same normalized
    snapshot in future compatibility checks; it is intentionally not mutated.
    """
    if operations in (None, "", []):
        return
    if not isinstance(operations, (list, tuple)):
        raise ValueError("layout_operations 必须是结构化操作列表")
    normalized_layout = normalize_layout_config(current_layout) if current_layout is not None else None
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("layout_operations 中存在无效操作")
        operation_name = str(operation.get("op", operation.get("type", "")) or "").lower()
        if operation_name not in {"set", "replace", "append", "insert", "remove", "move"}:
            raise ValueError("layout_operations 操作类型无效")
        tokens = _validate_path_and_value(operation, current_layout=normalized_layout)
        section, field = _field_tokens(tokens)  # type: ignore[misc]
        if operation_name in {"append", "insert", "move"} and (section, field) not in LIST_FIELDS:
            raise ValueError(f"排版字段“{field}”不支持列表操作")


def build_layout_context_text(
    layout_data: dict[str, Any] | None,
    *,
    include_full_config: bool = False,
) -> str:
    """Build the model-facing capability + current-state context."""
    config = normalize_layout_config(layout_data or {})
    manifest = build_layout_capability_manifest()
    current = {
        "schema_version": config["version"],
        "global": {
            key: config["global"].get(key)
            for key in sorted(EDITABLE_GLOBAL_FIELDS)
        },
        "modules": {
            module_id: {
                key: config[module_id].get(key)
                for key in sorted(EDITABLE_MODULE_FIELDS.get(module_id, set()))
            }
            for module_id in MODULE_COMPONENTS
            if module_id != "typography"
        },
    }
    # The compact context exposes all supported paths and the editable current
    # values.  A layout task additionally receives the complete normalized
    # renderer config, including component rows and derived compatibility data.
    parts = [
        "【排版能力契约】以下能力来自当前 schema 与三端共享 renderer，模型只能提出契约中存在的修改。",
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        "【当前可编辑排版状态】",
        json.dumps(current, ensure_ascii=False, separators=(",", ":")),
    ]
    if include_full_config:
        parts.extend([
            "【当前完整归一化排版配置】这是当前数据库配置的完整只读快照；建议必须以此状态为准，不得根据历史对话臆测。",
            json.dumps(config, ensure_ascii=False, separators=(",", ":")),
        ])
    return "\n".join(parts)


__all__ = [
    "LAYOUT_CAPABILITY_VERSION",
    "build_layout_capability_manifest",
    "build_layout_context_text",
    "validate_layout_operations",
]
