"""Canonical persisted resume schema and validation boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .resume_contract import ProjectContentBlock


def _clean_string_list(value):
    if not isinstance(value, list):
        return value
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            result.append(item)
            continue
        text = item.strip()
        if text and text not in result:
            result.append(text)
    return result


class ResumeModel(BaseModel):
    """Base model for persisted resume data."""

    model_config = ConfigDict(extra="forbid")


class AdditionalBasicField(ResumeModel):
    """A user-defined basic-information field."""

    label: str = Field(default="", description="字段名称，例如籍贯、政治面貌")
    value: str = Field(default="", description="字段原文")


class BasicInfo(ResumeModel):
    """Basic resume information."""

    name: str = Field(default="", description="姓名")
    gender: str = Field(default="", description="性别")
    birth_date: str = Field(default="", description="出生年月或出生日期，忠实保留原文")
    phone: str = Field(default="", description="手机号")
    email: str = Field(default="", description="邮箱")
    target_position: str = Field(default="", description="期望岗位")
    photo: str = Field(default="", description="证件照 data URL；文档解析时留空")
    photo_aspect_ratio: float | None = Field(
        default=None,
        ge=0.2,
        le=3.0,
        description="证件照宽高比；没有照片比例时省略",
    )
    additional_fields: list[AdditionalBasicField] = Field(
        default_factory=list,
        description="其他基本信息，每项为 label、value 字符串，例如籍贯、政治面貌",
    )

    @field_validator("additional_fields", mode="before")
    @classmethod
    def remove_empty_additional_fields(cls, value):
        if not isinstance(value, list):
            return value
        return [
            item for item in value
            if not isinstance(item, dict)
            or str(item.get("label") or "").strip()
            or str(item.get("value") or "").strip()
        ]


class Thesis(ResumeModel):
    """Thesis information attached to one education entry."""

    title: str = Field(default="", description="论文标题；原文没有时留空")
    details: list[str] = Field(default_factory=list, description="论文详细内容")

    _clean_details = field_validator("details", mode="before")(_clean_string_list)


class Education(ResumeModel):
    """Education entry."""

    school_name: str = Field(default="", description="学校名称；原文没有时留空")
    major: str = Field(default="", description="专业；原文没有时留空")
    degree: str = Field(default="", description="学历；原文没有时留空")
    date_range: list[str] = Field(default_factory=list, description="就读时间；原文没有时留空")
    school_tags: list[str] = Field(default_factory=list, description="学校性质标签")
    gpa: str = Field(default="", description="平均绩点，例如 3.72")
    gpa_scale: str = Field(default="", description="绩点满分，例如 4.0")
    ranking: str = Field(default="", description="专业或年级排名，例如 前10%")
    theses: list[Thesis] = Field(default_factory=list, description="论文列表")

    _clean_lists = field_validator("date_range", "school_tags", mode="before")(_clean_string_list)


class WorkExperience(ResumeModel):
    """Work-experience entry."""

    company_name: str = Field(default="", description="公司名称；原文没有时留空")
    job_title: str = Field(default="", description="职位名称；原文没有时留空")
    date_range: list[str] = Field(default_factory=list, description="就职时间；原文没有时留空")
    job_type: str = Field(default="", description="工作类型；原文没有明确标注时必须留空，不得推断")
    content_blocks: list[ProjectContentBlock] = Field(
        default_factory=list,
        description="工作简介、工作职责及零个或多个其他工作内容语义块；其他工作内容可带自定义标签或留空，空标签正文仍显示和导出；按当前 content_blocks 顺序保存；每种内容均可按原文或用户要求使用段落、分点或编号形式；工作经历不使用项目技术栈角色",
    )


class ProjectExperience(ResumeModel):
    """Project-experience entry."""

    project_name: str = Field(default="", description="项目名称；原文没有时留空")
    role: str = Field(default="", description="项目角色；原文未提供时必须留空")
    date_range: list[str] = Field(default_factory=list, description="项目时间")
    content_blocks: list[ProjectContentBlock] = Field(
        default_factory=list,
        description="技术栈、项目简介、项目职责及零个或多个其他项目内容语义块；其他项目内容可带自定义标签或留空，空标签正文仍显示和导出；按当前 content_blocks 顺序保存，语义角色与段落、分点、编号形式相互独立",
    )


class Others(ResumeModel):
    """Skills, certificates, and languages."""

    skills: list[str] = Field(default_factory=list, description="原简历顶层专业技能、技能特长或技术栈栏目的全部条目；项目经历内部技术栈写入项目 content_blocks")
    certificates: list[str] = Field(default_factory=list, description="仅提取原简历独立证书或资格栏目中的条目")
    languages: list[str] = Field(default_factory=list, description="仅提取原简历独立语言或外语能力栏目中的条目")
    field_labels: dict[Literal["certificates", "languages"], str] | None = Field(
        default=None,
        description="证书与语言栏目的可选用户标题",
    )

    _clean_lists = field_validator("skills", "certificates", "languages", mode="before")(_clean_string_list)


class CustomSection(ResumeModel):
    """A source section that cannot be mapped to a fixed module."""

    title: str = Field(default="", description="原栏目标题")
    items: list[str] = Field(default_factory=list, description="按原阅读顺序保留的内容")
    list_style: Literal["paragraph", "bullet", "numbered"] | None = Field(
        default=None,
        description="该自定义栏目的可选列表样式",
    )

    _clean_items = field_validator("items", mode="before")(_clean_string_list)


class Resume(ResumeModel):
    """The only persisted resume data structure."""

    formatting_version: int = Field(
        default=0,
        description="内联文字格式协议版本；4 表示当前固定字段和局部粗体协议",
    )
    basics: BasicInfo = Field(default_factory=BasicInfo, description="基本信息")
    education: list[Education] = Field(default_factory=list, description="教育背景")
    education_supplement: list[str] = Field(
        default_factory=list,
        description="教育经历补充；无独立标题的补充内容，按原顺序逐条保存",
    )
    research_interests: list[str] = Field(default_factory=list, description="研究方向或研究兴趣")
    honors: list[str] = Field(default_factory=list, description="荣誉、奖项、奖学金")
    publications: list[str] = Field(default_factory=list, description="论文")
    work_experience: list[WorkExperience] = Field(default_factory=list, description="工作经历")
    project_experience: list[ProjectExperience] = Field(default_factory=list, description="项目经历")
    custom_sections: list[CustomSection] = Field(default_factory=list, description="无法安全映射的原始栏目")
    others: Others = Field(default_factory=Others, description="其他信息")
    self_evaluation: list[str] = Field(default_factory=list, description="自我评价")

    _clean_lists = field_validator(
        "education_supplement",
        "research_interests",
        "honors",
        "publications",
        "self_evaluation",
        mode="before",
    )(_clean_string_list)


def validate_resume_data(data: dict) -> dict:
    """Validate and serialize resume data into the canonical persisted shape."""

    if not isinstance(data, dict):
        raise TypeError("resume data must be a JSON object")
    return Resume.model_validate(data).model_dump(exclude_none=True)
