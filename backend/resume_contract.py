"""Canonical contracts for structured resume content.

This module is deliberately renderer-agnostic.  Import, editing, agent
validation, and export code all use the same small vocabulary for experience
content blocks, so a value received from an older parser cannot silently turn
into a different visual structure in another layer.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


CONTENT_BLOCK_TYPES = ("paragraph", "numbered_list", "bullet_list")
CONTENT_BLOCK_SEMANTIC_ROLES = ("tech_stack", "introduction", "responsibilities", "generic")
CONTENT_BLOCK_TYPE_LABELS = {
    "paragraph": "段落",
    "bullet_list": "分点",
    "numbered_list": "编号",
}
CONTENT_BLOCK_ROLE_LABELS = {
    "tech_stack": "技术栈",
    "introduction": "简介",
    "responsibilities": "职责",
    "generic": "其他内容",
}
CONTENT_BLOCK_ROLE_LABELS_BY_ROOT = {
    "work_experience": {
        "introduction": "工作简介",
        "responsibilities": "工作职责",
        "generic": "其他工作内容",
    },
    "project_experience": {
        "tech_stack": "技术栈",
        "introduction": "项目简介",
        "responsibilities": "项目职责",
        "generic": "其他项目内容",
    },
}
CONTENT_BLOCK_ROLE_DESCRIPTORS = {
    "tech_stack": {
        "label": "技术栈",
        "roots": ["project_experience"],
        "meaning": "项目中明确标注的技术、工具或技术选型内容",
    },
    "introduction": {
        "label": "简介",
        "labels_by_root": {
            "work_experience": "工作简介",
            "project_experience": "项目简介",
        },
        "roots": ["work_experience", "project_experience"],
        "meaning": "一段经历的背景、目标或概述",
    },
    "responsibilities": {
        "label": "职责",
        "labels_by_root": {
            "work_experience": "工作职责",
            "project_experience": "项目职责",
        },
        "roots": ["work_experience", "project_experience"],
        "meaning": "一段经历中的职责、行动或成果条目",
    },
    "generic": {
        "label": "其他内容",
        "labels_by_root": {
            "work_experience": "其他工作内容",
            "project_experience": "其他项目内容",
        },
        "roots": ["work_experience", "project_experience"],
        "meaning": "无法或无需映射到其他语义角色的经历正文；可新增多个，自定义标签可留空且空标签正文仍显示和导出",
    },
}
CONTENT_BLOCK_TYPE_DESCRIPTORS = {
    "paragraph": "段落正文使用 text",
    "bullet_list": "分点正文使用 items",
    "numbered_list": "编号正文使用 items",
}
DEFAULT_CONTENT_BLOCK_TYPES = {
    "tech_stack": "paragraph",
    "introduction": "paragraph",
    "responsibilities": "numbered_list",
    "generic": "bullet_list",
}
class ProjectContentBlock(BaseModel):
    """A semantic block used by work and project experiences."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["paragraph", "numbered_list", "bullet_list"] = Field(
        default="paragraph", description="段落、编号列表或普通分点列表"
    )
    semantic_role: Literal["tech_stack", "introduction", "responsibilities", "generic"] | None = Field(
        default=None, description="稳定语义角色；旧数据缺省时由类型和标签兼容推断"
    )
    label: str = Field(default="", description="用户当前看到的内容块名称；generic 可留空且正文仍显示，其他语义角色空标签时正文不显示或导出")
    label_bold: bool = Field(default=True, description="语义标签是否加粗")
    text: str = Field(default="", description="paragraph 类型的正文")
    items: list[str] = Field(default_factory=list, description="列表类型的逐条内容，不包含序号")
    # These fields are parser-only evidence.  normalize_content_block consumes
    # them and never persists or renders them, but the extraction model needs a
    # way to describe where the source document's visual group changes.
    source_layout_group: str = Field(
        default="",
        exclude=True,
        description="仅供解析阶段使用的连续视觉组标识；不要写入最终简历数据",
    )
    source_indent_level: int | None = Field(
        default=None,
        exclude=True,
        description="仅供解析阶段使用的相对缩进层级；无法确认时留空",
    )
    source_marker_type: Literal["paragraph", "bullet", "numbered", ""] = Field(
        default="",
        exclude=True,
        description="仅供解析阶段使用的原始段落/分点/编号形式；不要写入最终简历数据",
    )


# The normalized resume already has a stable data shape.  This operation
# contract describes the subset that the conversation edit skill may mutate;
# it is intentionally separate from the natural-language parser.  Prompt
# generation and execution validation both consume these definitions so a
# field shape is not re-described for individual evaluation cases.
RESUME_EDIT_CONTRACT_VERSION = "2"
RESUME_EDIT_ROOTS = (
    "basics",
    "education",
    "education_supplement",
    "research_interests",
    "honors",
    "publications",
    "work_experience",
    "project_experience",
    "custom_sections",
    "others",
    "self_evaluation",
)

RESUME_EDIT_PATH_GROUPS: dict[str, dict[str, Any]] = {
    "basics": {
        "scalar_fields": [
            "name", "gender", "birth_date", "phone", "email",
            "target_position", "photo",
        ],
        "list_fields": {"additional_fields": "additional_basic_field"},
    },
    "education[]": {
        "scalar_fields": ["school_name", "major", "degree", "gpa", "gpa_scale", "ranking"],
        "list_fields": {
            "date_range": "string",
            "school_tags": "string",
            "theses": "thesis",
        },
    },
    "work_experience[]": {
        "scalar_fields": ["company_name", "job_title", "job_type"],
        "list_fields": {"date_range": "string", "content_blocks": "content_block"},
    },
    "project_experience[]": {
        "scalar_fields": ["project_name", "role"],
        "list_fields": {"date_range": "string", "content_blocks": "content_block"},
    },
    "others": {
        "scalar_fields": [],
        "list_fields": {
            "skills": "string", "certificates": "string", "languages": "string",
        },
    },
    "top_level_lists": {
        "list_fields": {
            "education": "education_experience",
            "education_supplement": "string",
            "research_interests": "string",
            "honors": "string",
            "publications": "string",
            "work_experience": "work_experience",
            "project_experience": "project_experience",
            "custom_sections": "custom_section",
            "self_evaluation": "string",
        },
    },
}

RESUME_EXPERIENCE_SHAPES: dict[str, dict[str, Any]] = {
    "education_experience": {
        "root": "education",
        "identity_field": "school_name",
        "scalar_fields": ["school_name", "major", "degree", "gpa", "gpa_scale", "ranking"],
        "list_fields": {"date_range": "string", "school_tags": "string", "theses": "thesis"},
    },
    "work_experience": {
        "root": "work_experience",
        "identity_field": "company_name",
        "scalar_fields": ["company_name", "job_title", "job_type"],
        "list_fields": {"date_range": "string", "content_blocks": "content_block"},
        "content_block_roles": ["introduction", "responsibilities", "generic"],
    },
    "project_experience": {
        "root": "project_experience",
        "identity_field": "project_name",
        "scalar_fields": ["project_name", "role"],
        "list_fields": {"date_range": "string", "content_blocks": "content_block"},
        "content_block_roles": list(CONTENT_BLOCK_SEMANTIC_ROLES),
    },
}
RESUME_EXPERIENCE_SHAPES_BY_ROOT = {
    spec["root"]: shape for shape, spec in RESUME_EXPERIENCE_SHAPES.items()
}

RESUME_EDIT_OPERATION_RULES = (
    "path 第一段必须是规范化简历根字段；不存在的包装字段不是操作路径",
    "set/replace 可写入契约声明的简历根字段、目标字段或列表项，所有值都必须通过对应 Schema 校验",
    "append/insert 只能作用于契约声明的列表字段，move 只能作用于列表本身",
    "列表元素和对象字段必须符合声明的规范结构；不做自然语言解析、猜测或自动修复",
    "内容块的 semantic_role 只表达内容含义，不决定展示形式；type 必须保留当前形式或遵循用户明确要求，三种形式均可用于允许的语义角色；work_experience 与 project_experience 均可 append/insert 多个 generic，generic 的 label 可为空且正文仍显示和导出",
    "经历内容块索引必须以当前规范化简历中的实际 content_blocks 为准；空的编辑器输入位置不代表持久化数据中存在占位元素",
    "对象的可选字段只有在用户明确要求该属性时才能提交；未明确要求时必须省略并继承当前值或系统默认值",
    "内容通过所属上级模块路径、当前显示标签和稳定内部语义共同定位；修改显示标签不得改变 semantic_role，target_semantic_role 可作为当前状态断言，无法唯一定位时应先澄清",
)


def build_resume_edit_contract() -> dict[str, Any]:
    """Return the machine-readable contract shared by prompt and validator."""
    return {
        "contract_version": RESUME_EDIT_CONTRACT_VERSION,
        "path_namespace": {
            "roots": list(RESUME_EDIT_ROOTS),
            "indexed_segment": "列表索引使用 field[index]，索引必须指向当前数据中的元素",
        },
        "operation_shape": {
            "required_fields": ["op", "path"],
            "allowed_fields": [
                "op", "path", "value", "index", "from_index", "to_index",
                "target_semantic_role",
            ],
            "op_values": ["set", "replace", "append", "insert", "remove", "move"],
            "path_rule": "path 必须指向当前规范化简历或排版配置中存在的目标",
            "value_required_for": ["set", "replace", "append", "insert"],
            "index_required_for": ["insert"],
            "move_fields": ["from_index", "to_index"],
        },
        "optional_field_policy": {
            "emit_only_when_explicitly_requested": True,
            "when_omitted": "继承当前值或系统默认值",
            "infer_or_repeat_defaults": False,
        },
        "supplement_semantics": {
            "education_supplement": {
                "path": "education_supplement",
                "label": "教育经历补充",
                "shape": "string_list",
                "meaning": "教育经历栏目内、下一个顶层栏目之前没有独立标题的补充内容",
            },
            "work_experience.generic": {
                "path": "work_experience[index].content_blocks[index]",
                "label": "其他工作内容",
                "shape": "content_block",
                "meaning": "工作经历中的补充正文；可有零个或多个用户自定义 label，label 可为空且空标签正文仍显示和导出，semantic_role 始终为 generic",
            },
            "project_experience.generic": {
                "path": "project_experience[index].content_blocks[index]",
                "label": "其他项目内容",
                "shape": "content_block",
                "meaning": "项目经历中的补充正文；可有零个或多个用户自定义 label，label 可为空且空标签正文仍显示和导出，semantic_role 始终为 generic",
            },
        },
        "path_groups": RESUME_EDIT_PATH_GROUPS,
        "root_value_shapes": {
            "basics": {
                "type": "object",
                "scalar_fields": list(RESUME_EDIT_PATH_GROUPS["basics"]["scalar_fields"]),
                "list_fields": dict(RESUME_EDIT_PATH_GROUPS["basics"]["list_fields"]),
                "preserved_numeric_fields": ["photo_aspect_ratio"],
                "additional_properties": False,
            },
            "others": {
                "type": "object",
                "list_fields": dict(RESUME_EDIT_PATH_GROUPS["others"]["list_fields"]),
                "optional_objects": {"field_labels": ["certificates", "languages"]},
                "additional_properties": False,
            },
            "top_level_lists": dict(RESUME_EDIT_PATH_GROUPS["top_level_lists"]["list_fields"]),
        },
        "value_shapes": {
            "string": {"type": "string"},
            "string_list": {"type": "array", "items": "string"},
            **{
                shape: {
                    "type": "object",
                    "required_non_empty": [spec["identity_field"]],
                    "scalar_fields": list(spec["scalar_fields"]),
                    "list_fields": dict(spec["list_fields"]),
                    **(
                        {"content_block_roles": list(spec["content_block_roles"])}
                        if "content_block_roles" in spec else {}
                    ),
                    "additional_properties": False,
                }
                for shape, spec in RESUME_EXPERIENCE_SHAPES.items()
            },
            "custom_section": {
                "type": "object",
                "required": {"title": "string", "items": "string_list"},
                "optional": {"list_style": ["paragraph", "bullet", "numbered"]},
                "additional_properties": False,
            },
            "content_block": {
                "type": "object",
                "allowed_fields": [
                    "type", "semantic_role", "label", "label_bold", "text", "items",
                ],
                "types": list(CONTENT_BLOCK_TYPES),
                "semantic_roles": list(CONTENT_BLOCK_SEMANTIC_ROLES),
                "type_descriptions": dict(CONTENT_BLOCK_TYPE_DESCRIPTORS),
                "role_descriptions": {
                    role: dict(descriptor)
                    for role, descriptor in CONTENT_BLOCK_ROLE_DESCRIPTORS.items()
                },
                "type_selection": "semantic_role 不绑定 type；paragraph 使用 text，bullet_list/numbered_list 使用 items，具体形式按当前内容或用户明确要求",
            },
            "thesis": {
                "type": "object",
                "required": {"title": "string", "details": "string_list"},
                "additional_properties": False,
            },
            "additional_basic_field": {
                "type": "object",
                "required": {"label": "string", "value": "string"},
                "additional_properties": False,
            },
        },
        "operation_rules": list(RESUME_EDIT_OPERATION_RULES),
    }


def build_resume_edit_contract_text() -> str:
    """Return a compact model-facing representation without case examples."""
    return (
        "【简历编辑操作契约】只能提交以下机器可读契约允许的规范化路径和值形状；"
        "它只描述可执行操作，不是自然语言修改指令。\n"
        f"{json.dumps(build_resume_edit_contract(), ensure_ascii=False, separators=(',', ':'))}"
    )


def canonical_resume_contract_path(tokens: tuple[str | int, ...]) -> tuple[str, ...]:
    """Normalize list indexes so value validation follows field shape."""
    return tuple("[]" if isinstance(token, int) else token for token in tokens)


def _contract_require_string(value: Any, *, path: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"修改值不符合字段结构：{path}")


def _contract_require_string_list(value: Any, *, path: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"修改值不符合列表字段结构：{path}")


def _contract_validate_custom_section(value: Any, *, path: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"自定义栏目必须使用 title/items 结构：{path}")
    if set(value) - {"title", "items", "list_style"}:
        raise ValueError(f"自定义栏目包含不支持的字段：{path}")
    if not isinstance(value.get("title"), str) or not value["title"].strip():
        raise ValueError(f"自定义栏目缺少有效 title：{path}")
    _contract_require_string_list(value.get("items"), path=f"{path}.items")
    if not value["items"]:
        raise ValueError(f"自定义栏目缺少有效 items：{path}")
    if "list_style" in value and value["list_style"] not in {"paragraph", "bullet", "numbered"}:
        raise ValueError(f"自定义栏目 list_style 无效：{path}")


def _contract_validate_content_block(
    value: Any,
    *,
    path: str,
    experience_root: str = "",
) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"内容块必须是结构化对象：{path}")
    allowed = {
        "type", "semantic_role", "label", "label_bold", "text", "items",
    }
    if set(value) - allowed:
        raise ValueError(f"内容块包含不支持的字段：{path}")
    if "type" in value and not isinstance(value["type"], str):
        raise ValueError(f"内容块 type 无效：{path}")
    if "semantic_role" in value and value["semantic_role"] is not None and not isinstance(value["semantic_role"], str):
        raise ValueError(f"内容块 semantic_role 无效：{path}")
    for key in ("label", "text"):
        if key in value:
            _contract_require_string(value[key], path=f"{path}.{key}")
    if "label_bold" in value and not isinstance(value["label_bold"], bool):
        raise ValueError(f"内容块 label_bold 无效：{path}")
    if "items" in value:
        _contract_require_string_list(value["items"], path=f"{path}.items")
    try:
        ProjectContentBlock.model_validate(value)
    except Exception as exc:
        raise ValueError(f"内容块不符合规范结构：{path}") from exc
    if experience_root == "work_experience" and value.get("semantic_role") == "tech_stack":
        raise ValueError(f"工作经历不支持项目技术栈内容块：{path}")


def _contract_validate_thesis(value: Any, *, path: str) -> None:
    if not isinstance(value, dict) or set(value) - {"title", "details"}:
        raise ValueError(f"论文条目不符合规范结构：{path}")
    _contract_require_string(value.get("title", ""), path=f"{path}.title")
    _contract_require_string_list(value.get("details", []), path=f"{path}.details")


def _contract_validate_additional_basic_field(value: Any, *, path: str) -> None:
    if not isinstance(value, dict) or set(value) - {"label", "value"}:
        raise ValueError(f"基本信息附加字段不符合规范结构：{path}")
    _contract_require_string(value.get("label", ""), path=f"{path}.label")
    _contract_require_string(value.get("value", ""), path=f"{path}.value")


def _contract_validate_root_object(root: str, value: Any, *, path: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"修改值必须是对象：{path}")
    if root == "basics":
        allowed = {
            *RESUME_EDIT_PATH_GROUPS["basics"]["scalar_fields"],
            "additional_fields", "photo_aspect_ratio",
        }
        if set(value) - allowed:
            raise ValueError(f"基本信息包含不支持的字段：{path}")
        for field in RESUME_EDIT_PATH_GROUPS["basics"]["scalar_fields"]:
            if field in value:
                _contract_require_string(value[field], path=f"{path}.{field}")
        if "photo_aspect_ratio" in value and not (
            isinstance(value["photo_aspect_ratio"], (int, float))
            and not isinstance(value["photo_aspect_ratio"], bool)
        ):
            raise ValueError(f"基本信息照片比例必须是数值：{path}.photo_aspect_ratio")
        additional_fields = value.get("additional_fields", [])
        if not isinstance(additional_fields, list):
            raise ValueError(f"基本信息附加字段必须是列表：{path}.additional_fields")
        for index, item in enumerate(additional_fields):
            _contract_validate_additional_basic_field(
                item, path=f"{path}.additional_fields[{index}]",
            )
        return
    if root == "others":
        if set(value) - {"skills", "certificates", "languages", "field_labels"}:
            raise ValueError(f"证书与语言信息包含不支持的字段：{path}")
        for field in ("skills", "certificates", "languages"):
            _contract_require_string_list(value.get(field, []), path=f"{path}.{field}")
        field_labels = value.get("field_labels", {})
        if not isinstance(field_labels, dict) or set(field_labels) - {"certificates", "languages"}:
            raise ValueError(f"证书与语言标签不符合规范结构：{path}.field_labels")
        for field, label in field_labels.items():
            _contract_require_string(label, path=f"{path}.field_labels.{field}")
        return
    raise ValueError(f"修改路径不属于对象根字段契约：{path}")


def _contract_validate_experience(value: Any, shape: str, *, path: str) -> None:
    spec = RESUME_EXPERIENCE_SHAPES[shape]
    if not isinstance(value, dict):
        raise ValueError(f"经历条目必须是结构化对象：{path}")
    allowed = set(spec["scalar_fields"]) | set(spec["list_fields"])
    if set(value) - allowed:
        raise ValueError(f"经历条目包含不支持的字段：{path}")
    identity_field = spec["identity_field"]
    identity = value.get(identity_field)
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError(f"经历条目缺少有效 {identity_field}：{path}")
    for field in spec["scalar_fields"]:
        if field in value:
            _contract_require_string(value[field], path=f"{path}.{field}")
    for field, item_shape in spec["list_fields"].items():
        if field not in value:
            continue
        items = value[field]
        if not isinstance(items, list):
            raise ValueError(f"经历字段必须是列表：{path}.{field}")
        for index, item in enumerate(items):
            item_path = f"{path}.{field}[{index}]"
            if item_shape == "string":
                _contract_require_string(item, path=item_path)
            elif item_shape == "thesis":
                _contract_validate_thesis(item, path=item_path)
            elif item_shape == "content_block":
                _contract_validate_content_block(
                    item,
                    path=item_path,
                    experience_root=spec["root"],
                )


def _contract_list_item_shape(canonical: tuple[str, ...]) -> str | None:
    for field, shape in (
        ("custom_sections", "custom_section"),
        ("content_blocks", "content_block"),
        ("theses", "thesis"),
        ("additional_fields", "additional_basic_field"),
    ):
        if canonical[-2:] == (field, "[]"):
            return shape
    leaf = canonical[-1] if canonical else ""
    if leaf == "custom_sections":
        return "custom_section"
    if leaf == "content_blocks":
        return "content_block"
    if leaf == "theses":
        return "thesis"
    if leaf == "additional_fields":
        return "additional_basic_field"
    if leaf in {
        "education_supplement", "research_interests", "honors", "publications",
        "self_evaluation", "date_range", "school_tags", "items",
        "skills", "certificates", "languages",
    }:
        return "string"
    if canonical and canonical[0] in RESUME_EXPERIENCE_SHAPES_BY_ROOT and canonical[1:] in {(), ("[]",)}:
        return RESUME_EXPERIENCE_SHAPES_BY_ROOT[canonical[0]]
    return None


_CONTRACT_STRUCTURED_FIELDS: dict[str, dict[str, str]] = {
    "custom_section": {"title": "scalar", "items": "string", "list_style": "scalar"},
    "content_block": {
        "type": "scalar", "semantic_role": "scalar", "label": "scalar",
        "label_bold": "scalar", "text": "scalar", "items": "string",
    },
    "thesis": {"title": "scalar", "details": "string"},
    "additional_basic_field": {"label": "scalar", "value": "scalar"},
}


def _contract_structured_path(
    shape: str,
    suffix: tuple[str, ...],
) -> tuple[str, str] | None:
    """Return (path kind, item shape) for a structured list branch."""
    fields = _CONTRACT_STRUCTURED_FIELDS.get(shape, {})
    if not suffix:
        return "item", shape
    field = suffix[0]
    field_shape = fields.get(field)
    if field_shape is None:
        return None
    if field_shape == "string":
        if len(suffix) == 1:
            return "list", "string"
        if suffix == (field, "[]"):
            return "item", "string"
        return None
    return ("field", "scalar") if len(suffix) == 1 else None


def _contract_structured_scalar_shape(
    canonical: tuple[str, ...],
) -> tuple[str, str] | None:
    """Return the structured item type and field for a scalar leaf."""
    if len(canonical) < 3:
        return None
    field = canonical[-1]
    for list_field, shape in (
        ("custom_sections", "custom_section"),
        ("content_blocks", "content_block"),
        ("theses", "thesis"),
        ("additional_fields", "additional_basic_field"),
    ):
        for index in range(len(canonical) - 1):
            if canonical[index:index + 2] == (list_field, "[]") and field in _CONTRACT_STRUCTURED_FIELDS[shape]:
                if index + 2 == len(canonical) - 1:
                    return shape, field
    return None


def _contract_validate_structured_scalar(
    canonical: tuple[str, ...],
    value: Any,
    *,
    path: str,
) -> None:
    descriptor = _contract_structured_scalar_shape(canonical)
    if descriptor is None:
        return
    shape, field = descriptor
    if shape == "content_block":
        if field == "type" and value not in CONTENT_BLOCK_TYPES:
            raise ValueError(f"内容块 type 不在契约允许范围内：{path}")
        if field == "semantic_role" and value not in (*CONTENT_BLOCK_SEMANTIC_ROLES, None):
            raise ValueError(f"内容块 semantic_role 不在契约允许范围内：{path}")
        if field == "semantic_role" and canonical[0] == "work_experience" and value == "tech_stack":
            raise ValueError(f"工作经历不支持项目技术栈内容块：{path}")
        if field == "label_bold" and not isinstance(value, bool):
            raise ValueError(f"内容块 label_bold 必须是布尔值：{path}")
        if field not in {"type", "semantic_role", "label_bold"}:
            _contract_require_string(value, path=path)
    elif shape == "custom_section" and field == "list_style":
        if value not in {"paragraph", "bullet", "numbered"}:
            raise ValueError(f"自定义栏目 list_style 不在契约允许范围内：{path}")
    else:
        _contract_require_string(value, path=path)


def _contract_path_shape(canonical: tuple[str, ...]) -> tuple[str, str] | None:
    """Resolve a canonical operation path through the declarative registry."""
    if not canonical or canonical[0] not in RESUME_EDIT_ROOTS:
        return None
    root = canonical[0]
    rest = canonical[1:]
    if root == "basics":
        if not rest:
            return "root", "object"
        group = RESUME_EDIT_PATH_GROUPS["basics"]
        if rest[0] in group["scalar_fields"] and len(rest) == 1:
            return "field", "scalar"
        if rest[0] == "additional_fields":
            if len(rest) == 1:
                return "list", "additional_basic_field"
            if rest[1] == "[]":
                return _contract_structured_path("additional_basic_field", rest[2:])
        return None
    if root == "others":
        if not rest:
            return "root", "object"
        if len(rest) == 1 and rest[0] in RESUME_EDIT_PATH_GROUPS["others"]["list_fields"]:
            return "list", "string"
        if len(rest) == 2 and rest[1] == "[]" and rest[0] in RESUME_EDIT_PATH_GROUPS["others"]["list_fields"]:
            return "item", "string"
        return None
    top_level = RESUME_EDIT_PATH_GROUPS["top_level_lists"]["list_fields"]
    if root in top_level:
        shape = top_level[root]
        if not rest:
            return "list", shape
        if rest[0] != "[]":
            return None
        if shape == "string":
            return ("item", "string") if len(rest) == 1 else None
        if shape in _CONTRACT_STRUCTURED_FIELDS:
            return _contract_structured_path(shape, rest[1:])
        if len(rest) == 1:
            return "item", shape
        group = RESUME_EDIT_PATH_GROUPS.get(f"{root}[]")
        if group is None or len(rest) < 2:
            return None
        field = rest[1]
        if len(rest) == 2 and field in group["scalar_fields"]:
            return "field", "scalar"
        if field in group["list_fields"]:
            item_shape = group["list_fields"][field]
            if len(rest) == 2:
                return "list", item_shape
            if rest[2] != "[]":
                return None
            if item_shape == "string":
                return ("item", "string") if len(rest) == 3 else None
            return _contract_structured_path(item_shape, rest[3:])
        return None
    return None


def validate_resume_operation_path(
    tokens: tuple[str | int, ...],
    *,
    operation: str,
    path: str,
) -> None:
    """Reject paths and list operations outside the resume edit contract."""
    canonical = canonical_resume_contract_path(tokens)
    descriptor = _contract_path_shape(canonical)
    if descriptor is None:
        raise ValueError(f"修改路径不属于简历编辑契约：{path}")
    kind, _shape = descriptor
    if operation in {"append", "insert", "move"} and kind != "list":
        raise ValueError(f"列表操作必须作用于契约声明的列表路径：{path}")
    if operation == "remove" and len(tokens) == 1:
        raise ValueError(f"不能删除简历根栏目：{path}")
    if operation in {"set", "replace"}:
        if kind == "root":
            raise ValueError(f"整体对象必须拆分为最小可写字段：{path}")
        if kind == "item" and (
            _shape in RESUME_EXPERIENCE_SHAPES
            or _shape in _CONTRACT_STRUCTURED_FIELDS
        ):
            raise ValueError(f"结构化对象必须拆分为最小可写字段：{path}")


def validate_resume_operation_item(value: Any, tokens: tuple[str | int, ...], *, path: str) -> None:
    """Validate one list element according to the canonical path shape."""
    canonical = canonical_resume_contract_path(tokens)
    shape = _contract_list_item_shape(canonical)
    if shape == "custom_section":
        _contract_validate_custom_section(value, path=path)
    elif shape == "content_block":
        _contract_validate_content_block(
            value,
            path=path,
            experience_root=canonical[0] if canonical else "",
        )
    elif shape == "thesis":
        _contract_validate_thesis(value, path=path)
    elif shape == "additional_basic_field":
        _contract_validate_additional_basic_field(value, path=path)
    elif shape == "string":
        _contract_require_string(value, path=path)
    elif shape in RESUME_EXPERIENCE_SHAPES:
        _contract_validate_experience(value, shape, path=path)
    elif shape is None and not isinstance(value, (str, dict, list, int, float, bool)):
        raise ValueError(f"列表项不符合规范结构：{path}")


def validate_resume_operation_value(
    current: Any,
    value: Any,
    tokens: tuple[str | int, ...],
    *,
    path: str,
) -> None:
    """Validate a set/replace value against the canonical field contract."""
    canonical = canonical_resume_contract_path(tokens)
    descriptor = _contract_path_shape(canonical)
    if descriptor is None:
        raise ValueError(f"修改路径不属于简历编辑契约：{path}")
    kind, shape = descriptor
    if kind == "root":
        _contract_validate_root_object(canonical[0], value, path=path)
        return
    if kind == "item":
        if shape in RESUME_EXPERIENCE_SHAPES:
            raise ValueError(f"结构化列表项必须定位到具体字段：{path}")
        if shape == "string":
            _contract_require_string(value, path=path)
        elif shape in _CONTRACT_STRUCTURED_FIELDS:
            validate_resume_operation_item(value, tokens, path=path)
        return
    if kind == "field":
        _contract_validate_structured_scalar(canonical, value, path=path)
    if kind == "list":
        _contract_require_string_list(value, path=path) if shape == "string" else None
        if shape != "string":
            if not isinstance(value, list):
                raise ValueError(f"修改值必须是列表：{path}")
            for index, item in enumerate(value):
                item_tokens = (*tokens, index)
                validate_resume_operation_item(item, item_tokens, path=f"{path}[{index}]")
        return
    if canonical[-2:] in {
        ("custom_sections", "[]"), ("content_blocks", "[]"),
        ("theses", "[]"), ("additional_fields", "[]"),
    }:
        validate_resume_operation_item(value, tokens, path=path)
        return
    if canonical and canonical[-1] == "[]":
        raise ValueError(f"结构化列表项必须定位到具体字段：{path}")
    if isinstance(current, list):
        if not isinstance(value, list):
            raise ValueError(f"修改值必须是列表：{path}")
        for index, item in enumerate(value):
            validate_resume_operation_item(item, tokens, path=f"{path}[{index}]")
        return
    if isinstance(current, dict):
        if not isinstance(value, dict):
            raise ValueError(f"修改值必须是对象：{path}")
        return
    if isinstance(current, bool):
        valid = isinstance(value, bool)
    elif isinstance(current, str):
        valid = isinstance(value, str)
    elif isinstance(current, (int, float)) and not isinstance(current, bool):
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        valid = value is None or isinstance(value, type(current))
    if not valid:
        raise ValueError(f"修改值类型与目标字段不一致：{path}")


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
    "工作简介": "introduction",
    "项目简介": "introduction",
    "项目背景": "introduction",
    "项目概述": "introduction",
    "responsibilities": "responsibilities",
    "responsibility": "responsibilities",
    "duty": "responsibilities",
    "duties": "responsibilities",
    "主要职责": "responsibilities",
    "工作职责": "responsibilities",
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


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


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
    has_explicit_semantic_role = isinstance(raw, Mapping) and bool(_text(raw.get("semantic_role")))
    if semantic_role == "generic":
        if label_role == "generic":
            # An explicitly authored generic label is a real visible submodule
            # name (for example “项目成果”), not parser decoration.
            if not has_explicit_semantic_role:
                label = ""
        elif label and not has_explicit_semantic_role:
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


def _order_project_content_blocks(
    blocks: list[dict[str, Any]],
    *,
    experience_kind: str,
) -> list[dict[str, Any]]:
    """Keep the authored project block order intact.

    The module-order dialog is the single place that changes this list.  The
    contract must therefore be order-preserving; sorting by semantic role
    would silently undo an explicit user arrangement on every render/save.
    """
    return blocks


def normalize_content_blocks(
    value: Any,
    *,
    experience_kind: str = "project",
) -> list[dict[str, Any]]:
    """Normalize explicit semantic content blocks."""
    experience_root = "work_experience" if experience_kind == "work" else "project_experience"
    contextual_labels = CONTENT_BLOCK_ROLE_LABELS_BY_ROOT[experience_root]
    entries: list[tuple[Any, dict[str, Any], tuple[str, int | None, str]]] = []
    if isinstance(value, list):
        for raw in value:
            block = normalize_content_block(raw)
            if block is not None:
                if experience_kind == "work":
                    if block["semantic_role"] == "introduction" and block["label"] == "项目简介":
                        block["label"] = contextual_labels["introduction"]
                    elif block["semantic_role"] == "responsibilities" and block["label"] == "项目职责":
                        block["label"] = contextual_labels["responsibilities"]
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
            "label": contextual_labels["responsibilities"],
            "label_bold": True,
            "text": "",
            "items": items,
        }

    def append_responsibilities(block: dict[str, Any]) -> None:
        if (
            result
            and result[-1]["semantic_role"] == "responsibilities"
            and result[-1]["label"] == contextual_labels["responsibilities"]
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
    return _order_project_content_blocks(result, experience_kind=experience_kind)
