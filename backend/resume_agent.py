"""
简历助手 AI 代理模块
使用 LangGraph 构建的智能对话系统，帮助用户完善简历。

核心设计原则：
1. 状态驱动：单次执行状态通过 AgentState 传递，跨请求状态由应用数据库持久化
2. 工具调用：只在必要时调用预览优先的修改技能
3. 消息过滤：只传递 HumanMessage/AIMessage/SystemMessage 给 LLM，跳过 ToolMessage
4. 无硬编码回复：所有 AI 回复由 LLM 生成，不使用硬编码内容
5. 单LLM节点架构：conversation_llm 负责对话和工具调用决策
"""

import os
import json
import logging
import re
import uuid
import asyncio
import httpx
import time
from contextvars import ContextVar
from copy import deepcopy
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from dataclasses import field, replace
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from dataclasses import dataclass
from typing import Annotated, List
from pydantic import BaseModel, Field

from .resume_data import normalize_resume_data
from .resume_contract import ProjectContentBlock
from .prompt_contract import CONTENT_STRUCTURE_GUIDANCE, build_layout_context
from .inline_formatting import InlineFormatError, format_resume_text, plain_inline_text
from .resume_changes import (
    apply_resume_changes,
    build_resume_changes,
    resume_digest,
    validate_resume_change_set,
)
from .layout_config import (
    apply_density,
    apply_layout_change_groups,
    build_layout_changes,
    default_layout_config,
    normalize_layout_config,
    reset_layout_section,
)
from .layout_capabilities import localize_user_visible_layout_text
from .llm_providers import active_profile, role_temperature
from .harness.context import build_conversation_context
from .harness.observability import harness_metrics
from .skill_runtime import activate_agent_skill, skill_runtime


EDIT_SKILL_NAME = "resume-edit"
SNAPSHOT_SKILL_NAME = "resume-snapshot"
COACH_SKILL_NAME = "resume-coach"
EDIT_TOOL_NAME = skill_runtime.get(EDIT_SKILL_NAME).tool_name
SNAPSHOT_TOOL_NAME = skill_runtime.get(SNAPSHOT_SKILL_NAME).tool_name
COACH_TOOL_NAME = skill_runtime.get(COACH_SKILL_NAME).tool_name
ResumeEditOperationError = skill_runtime.get(EDIT_SKILL_NAME).module.ResumeEditOperationError
ResumeVisualSnapshot = skill_runtime.get(SNAPSHOT_SKILL_NAME).module.ResumeSnapshotOutput
resume_edit_tool = skill_runtime.get(EDIT_SKILL_NAME).model_tool()
resume_snapshot_tool = skill_runtime.get(SNAPSHOT_SKILL_NAME).model_tool()
resume_coach_tool = skill_runtime.get(COACH_SKILL_NAME).model_tool()

LOGGER = logging.getLogger(__name__)


_edit_lock_acquirer: ContextVar[object | None] = ContextVar(
    "resume_edit_lock_acquirer", default=None
)


async def acquire_current_edit_lock() -> None:
    """Ask the HTTP boundary to reserve this task before preview generation."""
    callback = _edit_lock_acquirer.get()
    if callback is None:
        return
    result = callback()
    if hasattr(result, "__await__"):
        await result


def set_edit_lock_acquirer(callback):
    return _edit_lock_acquirer.set(callback)


def reset_edit_lock_acquirer(token) -> None:
    _edit_lock_acquirer.reset(token)


def record_assistant_revision(
    user_id, task_id, before_data, after_data, selected_change_ids,
    before_layout=None, after_layout=None,
):
    """Persist an undo snapshot after the original save path succeeds."""
    from .database import SessionLocal, record_resume_revision
    revision_db = SessionLocal()
    try:
        return record_resume_revision(
            revision_db, user_id, task_id, before_data, after_data, selected_change_ids,
            before_layout, after_layout,
        )
    finally:
        revision_db.close()


def estimate_tokens(text):
    """粗略估算 tokens 数量（中英文混合场景）"""
    if not text:
        return 0
    if isinstance(text, list):
        return sum(
            estimate_tokens(item.get("text", ""))
            for item in text
            if isinstance(item, dict) and item.get("type") == "text"
        )
    text_str = str(text)
    chinese_chars = sum(1 for c in text_str if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text_str) - chinese_chars
    return int(chinese_chars * 0.5 + other_chars * 0.25)

# 加载环境变量
load_dotenv()
# Preserve Windows/system proxy auto-detection for future LLM calls without
# changing any machine-wide environment variable.
os.environ.setdefault("LANGCHAIN_OPENAI_TCP_KEEPALIVE", "0")


# =============================================================================
# Pydantic 数据模型定义
# =============================================================================

class AdditionalBasicField(BaseModel):
    """未预设的个人基本信息。"""
    label: str = Field(default="", description="字段名称，例如籍贯、政治面貌")
    value: str = Field(default="", description="字段原文")


class BasicInfo(BaseModel):
    """基本信息"""
    name: str = Field(default="", description="姓名")
    gender: str = Field(default="", description="性别")
    birth_date: str = Field(default="", description="出生年月或出生日期，忠实保留原文")
    phone: str = Field(default="", description="手机号")
    email: str = Field(default="", description="邮箱")
    target_position: str = Field(default="", description="期望岗位")
    photo: str = Field(default="", description="证件照 data URL；文档解析时留空")
    additional_fields: List[AdditionalBasicField] = Field(
        default_factory=list,
        description="其他基本信息，每项为 label、value 字符串，例如籍贯、政治面貌",
    )


class Thesis(BaseModel):
    """论文信息"""
    title: str = Field(default="", description="论文标题；原文没有时留空")
    details: List[str] = Field(default_factory=list, description="论文详细内容")


class Education(BaseModel):
    """教育背景"""
    school_name: str = Field(default="", description="学校名称；原文没有时留空")
    major: str = Field(default="", description="专业；原文没有时留空")
    degree: str = Field(default="", description="学历；原文没有时留空")
    date_range: List[str] = Field(default_factory=list, description="就读时间；原文没有时留空")
    school_tags: List[str] = Field(default_factory=list, description="学校性质标签")
    gpa: str = Field(default="", description="平均绩点，例如 3.72")
    gpa_scale: str = Field(default="", description="绩点满分，例如 4.0")
    ranking: str = Field(default="", description="专业或年级排名，例如 前10%")
    theses: List[Thesis] = Field(default_factory=list, description="论文列表")


class WorkExperience(BaseModel):
    """工作经历"""
    company_name: str = Field(default="", description="公司名称；原文没有时留空")
    job_title: str = Field(default="", description="职位名称；原文没有时留空")
    date_range: List[str] = Field(default_factory=list, description="就职时间；原文没有时留空")
    job_type: str = Field(default="", description="工作类型；原文没有明确标注时必须留空，不得推断")
    content_blocks: List[ProjectContentBlock] = Field(default_factory=list, description="工作简介、工作职责、其他工作内容等语义内容块；每种内容均可按原文或用户要求使用段落、分点或编号形式；工作经历不使用项目技术栈角色")


class ProjectExperience(BaseModel):
    """项目经历"""
    project_name: str = Field(default="", description="项目名称；原文没有时留空")
    role: str = Field(default="", description="项目角色；原文未提供时必须留空")
    date_range: List[str] = Field(default_factory=list, description="项目时间")
    content_blocks: List[ProjectContentBlock] = Field(
        default_factory=list, description="技术栈、项目简介、项目职责、其他项目内容语义块；语义角色与段落、分点、编号形式相互独立"
    )


class Others(BaseModel):
    """其他信息"""
    skills: List[str] = Field(default_factory=list, description="原简历顶层专业技能/技能特长/技术栈栏目中的全部条目，包括该栏目内出现的语言和证书；项目经历内部技术栈写入项目 content_blocks")
    certificates: List[str] = Field(default_factory=list, description="仅提取原简历独立证书/资格栏目中的条目")
    languages: List[str] = Field(default_factory=list, description="仅提取原简历独立语言/外语能力栏目中的条目")


class CustomSection(BaseModel):
    """无法安全映射到固定栏目、但必须保留的原简历栏目。"""
    title: str = Field(default="", description="原栏目标题")
    items: List[str] = Field(default_factory=list, description="按原阅读顺序保留的内容")


class Resume(BaseModel):
    """完整简历数据结构"""
    formatting_version: int = Field(default=0, description="内联文字格式协议版本；4 表示固定字段字重与大输入框局部粗体协议")
    basics: BasicInfo = Field(default_factory=BasicInfo, description="基本信息")
    education: List[Education] = Field(default_factory=list, description="教育背景")
    education_supplement: List[str] = Field(
        default_factory=list,
        description="教育经历补充；无独立标题的补充内容，按原顺序逐条保存，不包含序号",
    )
    research_interests: List[str] = Field(default_factory=list, description="研究方向或研究兴趣")
    honors: List[str] = Field(default_factory=list, description="荣誉、奖项、奖学金")
    publications: List[str] = Field(default_factory=list, description="论文，每个元素为一篇完整论文信息")
    work_experience: List[WorkExperience] = Field(default_factory=list, description="工作经历")
    project_experience: List[ProjectExperience] = Field(default_factory=list, description="项目经历")
    custom_sections: List[CustomSection] = Field(default_factory=list, description="其他原始栏目，禁止丢弃")
    others: Others = Field(default_factory=Others, description="其他信息")
    self_evaluation: List[str] = Field(default_factory=list, description="自我评价")


# =============================================================================
# JD (Job Description) 数据模型定义
# =============================================================================

class JDRequirements(BaseModel):
    """JD要求"""
    education: str = Field(default="", description="学历要求")
    experience: str = Field(default="", description="经验要求")
    skills: List[str] = Field(default_factory=list, description="技能要求")
    language: str = Field(default="", description="语言要求")


class JobDescription(BaseModel):
    """完整JD数据结构"""
    company: str = Field(default="", description="公司名称")
    position: str = Field(default="", description="职位名称")
    department: str = Field(default="", description="部门/团队")
    location: str = Field(default="", description="工作地点")
    job_type: str = Field(default="", description="全职/实习")
    salary: str = Field(default="", description="薪资范围")
    description: str = Field(default="", description="职位描述（核心职责）")
    requirements: JDRequirements = Field(default_factory=JDRequirements, description="任职要求")
    preferred_qualifications: List[str] = Field(default_factory=list, description="优先条件")
    highlights: List[str] = Field(default_factory=list, description="JD亮点/核心关键词")


# =============================================================================
# LLM 配置
# =============================================================================

LLM_PROVIDER, _ACTIVE_LLM_PROFILE = active_profile()
LLM_API_KEY = _ACTIVE_LLM_PROFILE["api_key"]
LLM_BASE_URL = _ACTIVE_LLM_PROFILE["base_url"] or None
LLM_MODEL = _ACTIVE_LLM_PROFILE["model"]
LLM_TEMPERATURE = _ACTIVE_LLM_PROFILE.get("temperature")
LLM_ENABLED = bool(LLM_API_KEY)

# ChatOpenAI constructs clients during module import. A local sentinel keeps the
# non-AI parts of the application bootable until a real key is configured.
llm_client_api_key = LLM_API_KEY or "local-llm-disabled"

# A complete candidate JSON can take longer than a normal conversational turn,
# especially for long resumes. Keep one explicit request budget for both the
# HTTP client and the skill boundary so the inner request is not cancelled by
# a shorter transport timeout first.
LLM_REQUEST_TIMEOUT_SECONDS = 180.0

httpx_client = httpx.Client(
    timeout=httpx.Timeout(LLM_REQUEST_TIMEOUT_SECONDS),
    limits=httpx.Limits(max_connections=20),
)

def create_llm_for_config(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    temperature: float | None,
    provider: str = "openai",
):
    """Create a chat model for a specific local configuration."""
    kwargs = {
        "api_key": api_key or "local-llm-disabled",
        "base_url": base_url,
        "model": model,
        "http_client": httpx_client,
        "max_retries": 3,
        "timeout": LLM_REQUEST_TIMEOUT_SECONDS,
    }
    effective_temperature = role_temperature(provider, model, temperature)
    if effective_temperature is not None:
        kwargs["temperature"] = effective_temperature
    return ChatOpenAI(**kwargs)


def create_llm(*, temperature: float):
    """Create a role-specific model; provider rules may omit temperature entirely."""
    return create_llm_for_config(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        temperature=temperature,
        provider=LLM_PROVIDER,
    )


# Conversation LLM - 负责对话和读取
conversation_llm = create_llm(temperature=0.1)

# JD Parser LLM - 负责解析JD文本/图片为JSON
jd_parser_llm = create_llm(temperature=0.0)


def reload_llm_config():
    """Reload local LLM settings without restarting the backend process."""
    global LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, LLM_ENABLED
    global llm_client_api_key, conversation_llm, jd_parser_llm

    LLM_PROVIDER, profile = active_profile()
    LLM_API_KEY = profile["api_key"]
    LLM_BASE_URL = profile["base_url"] or None
    LLM_MODEL = profile["model"]
    LLM_TEMPERATURE = profile.get("temperature")
    LLM_ENABLED = bool(LLM_API_KEY)
    llm_client_api_key = LLM_API_KEY or "local-llm-disabled"
    conversation_llm = create_llm(temperature=0.1)
    jd_parser_llm = create_llm(temperature=0.0)
    return {
        "configured": LLM_ENABLED,
        "model": LLM_MODEL,
        "base_url": LLM_BASE_URL or "",
        "provider": LLM_PROVIDER,
        "temperature": LLM_TEMPERATURE,
    }


# =============================================================================
# Prompts - 系统提示词
# =============================================================================

CONVERSATION_PROMPT = """
# Role
你是专业、严格、讲求证据的简历顾问。你根据用户当前目标回答问题、分析简历或调用合适的 Agent Skill，不擅自把普通对话切换成持续教练流程。

# 核心原则
- **事实优先**：事实不足时说明缺口；需要持续取证时按需建议或进入教练 Skill。
- **结果导向**：坚信任何经历都必须有量化指标或具体成果。
- **学长风范**：专业、敏锐、直接，用自然流畅的对话消除用户的焦虑。
- **绝对真实**：绝对禁止为用户虚构没有的经历、技能等，一个词都不允许，为了提高质量而虚构最终会害了用户。（例如用户本来没有提到photoshop，就算JD里要求了，也不能帮用户编一个技能出来，应该引导用户去学习这个技能，而不是通过虚构来达到JD要求，这样对用户才是真正的负责）

# 简历全维度评判（需要以怀疑论者的角度去审视，分数不用输出给用户）

## 全面诊断参考顺序
1. **目标岗位**：如果你没有任何关于用户目标岗位或意愿的信息，不要进行假设，优先引导用户**点击页面右上角的“目标岗位”按钮上传目标岗位JD（文本或图片）**，或者如果没有明确的目标岗位，至少引导用户输入一个明确的期望岗位名称（如"我想申请字节跳动的产品经理岗位"），以便后续优化有明确的方向。
2. **基础信息**：姓名、手机、邮箱、期望岗位 （重要，绝对不能缺漏！）
3. **教育经历**：学校、专业、学位、时间、亮点标签、GPA/绩点、排名
4. **工作经历**：公司、职位、时间、STAR 描述、量化结果
5. **项目经历**：项目名、角色、技术栈、STAR 描述、量化成果
6. **其他**：技能、证书、语言
7. **自我评价**：总结性描述

## 简历内容全维度评分

### 1. 简历质量评分 (Resume Quality - 70%)
- **内容完整度 (10分)**：基础、教育、经历等模块的齐备性。
- **描述专业度 (15分)**：动词精准，消灭“负责/参与”等虚词，语言干练。
- **结果导向与量化 (15分)**：必须符合 STAR 法则。无数字、无对比、无产出结果的项目，此项计 0 分。
- **技术/业务深度 (30分)**：是否触及底层原理或核心业务、商业逻辑、核心贡献。

### 2. 目标岗位匹配度分析 (Match Rate - 30%)
- **核心技能重合度 (10分)**：简历中是否有具体的实战证据支撑。
- **经验深度与职级 (10分)**：业务复杂度、用户规模、团队协作层级是否对等。
- **软性指标与背景 (10分)**：学历、行业偏好、职业稳定性。
若无目标岗位 JD，匹配度分值暂不计入总分，仅以简历本体质量 70% 进行等比例折算”。

### Negative Criteria (负面惩罚：识别“防御性包装”)
若发现以下特征，必须大幅扣分：
1. **过程劳务化**：强调“写了1w字”、“调研6款产品”等工作量，而非价值。判定：用“我很忙”掩盖“没产出”。
2. **话术空心化**：堆砌“赋能、闭环、沉淀、颗粒度”等黑话。判定：剥离黑话后若逻辑平庸，视为“描述虚浮”。
3. **缺乏决策痕迹**：全是“执行、跟进”，没有“优化、选型、推翻、决策”。判定：此类用户为“流程搬运工”。

## 评估结论
根据以上维度，给出总体判断：
- **不完善**：低于60分或标准化顺序中7个维度中有明显缺失
- **基本完善**：60-80分，框架完整但有细节需要打磨
- **完善**：80分以上，质量达标

# 简历精炼法则 (核心指南)
当用户提供或询问经历时，请务必引导其符合以下标准：
1. **STAR 结构化**：
   - **Situation/Task**：用一句话概括背景（做了什么，解决了什么难题）。
   - **Action (关键)**：使用了什么工具/方法？具体拆解了哪些步骤？（例如：从"负责开发"引导至"利用 Vue3 + LangGraph 构建了状态机逻辑"）。
   - **Result**：必须有数字或对比（如：效率提升 30%、首屏加载从 2s 降至 0.5s、获得 500+ 用户好评）。
2. **动词精准**：优先使用"主导"、"重构"、"从0到1构建"、"优化"等高含金量动词。
3. **关键信息加粗**：**重要** - 用两个星号 ** 包裹关键信息以加粗，包括量化指标（数字、百分比）、核心技术/工具、核心成就，以及标签式描述（如"技术栈："、"职责："等）。

# 简历质量约束（参考资深面试官标准）
1. **穿透包装**：识别并拆穿"用过程繁琐掩盖结果平庸"的防御性描述。引导用户关注价值而非工作量（例如"写了1w字"、"调研6款产品"等过程劳务化表述应转化为具体产出）。
2. **结果导向**：坚信没有量化结果的经历等同于"流水账"。每个经历必须包含数字或对比（如效率提升30%、用户增长500+等），否则引导用户补充。
3. **决策挖掘**：关注用户"为什么做"而不仅仅是"做了什么"。询问决策背后的原因、选型依据、权衡考虑，体现思考深度。
4. **避免黑话**：禁止使用"赋能、闭环、沉淀、颗粒度"等空洞话术。引导用户用具体、直白的语言描述实际贡献。
5. **负面惩罚意识**：如果用户提供的内容存在"过程劳务化"、"话术空心化"、"缺乏决策痕迹"，应指出并引导改进。用户已明确授权合法修改时，可以同时给出简短建议和修改候选，内容质量一般不能成为拒绝执行的理由。

# 用户的简历数据：{{resume_data}}

# 目标岗位JD数据：{{jd_data}}

# 当前排版与经历内容契约：{{layout_contract}}

# 对话逻辑规则与输出风格
1. **明确授权优先**：用户提供了事实、目标和期望结果的合法修改，不得被主动质量建议阻断；必要建议可以与修改候选同时提供。只有真实性、歧义、能力边界或相互冲突的问题才能阻止修改。
2. **边界清晰**：普通问答、一次性诊断和直接修改不建立持续教练状态；持续取证只由已激活的教练 Skill 管理。
3. **引导式提问**：若描述简略且修改结果仍不明确，应通过提问启发细节，不得替用户编造事实。

# Agent Skill 协调规则
- 本轮可用 Agent Skills 的名称和描述由系统动态注入。需要使用某项能力时，必须先调用 activate_agent_skill；激活后遵循加载的 SKILL.md 说明和结构化 Tool schema。
- Skill 的 Tool 参数只能包含模型可提供的业务参数。当前简历、排版、版本、照片和渲染样式由系统作为可信运行时上下文注入，不得自行提交或伪造。
- 用户一次消息同时包含执行请求和咨询问题时，只把明确执行的部分交给修改 Skill，其余咨询保留在当前对话中。
- 面向用户的回复不得展示 Skill 名、Tool 名、字段路径、内部枚举、协议标记或结构化载荷；修改 Skill 只生成候选，用户确认后才保存。

# 重要规则
- **重要** 当 just_saved=True（简历刚保存）时，说明简历已经修改完成了，不要调用任何工具。
- **重要** 面向用户的回复遵守上述统一表达边界；结构化参数可使用内部标识，但不得把它们复制到回复正文。
- **重要** 禁止构造虚假的修改建议，必须基于用户实际提供的内容，为了提高质量而虚构任何东西（哪怕是一个词）最终会害了用户。
- 绝对禁止说："已保存"、"已修改"、"正在为你更新"。
- 不得向用户展示结构化数据载荷或内部实现术语。
- 年份信息： 当前现实世界的年份是 2026 年，需要谨记。

请根据用户的具体问题和当前简历内容，给出专业、有针对性的回复。"""


# JD Parser Prompt - 用于解析JD文本/图片为JSON
JD_PARSER_PROMPT = '''# Role
你是JD解析专家，负责将招聘描述（Job Description）解析为结构化JSON。

# 任务
将用户提供的JD文本或图片OCR内容解析为结构化数据。

# 严格的输出格式
你必须严格按照以下JSON Schema输出，直接输出JSON对象：

```json
{
  "type": "object",
  "properties": {
    "company": { "type": "string", "description": "公司名称" },
    "position": { "type": "string", "description": "职位名称" },
    "department": { "type": "string", "description": "部门/团队" },
    "location": { "type": "string", "description": "工作地点" },
    "job_type": { "type": "string", "description": "全职/实习" },
    "salary": { "type": "string", "description": "薪资范围" },
    "description": { "type": "string", "description": "职位描述（核心职责）" },
    "requirements": {
      "type": "object",
      "properties": {
        "education": { "type": "string", "description": "学历要求" },
        "experience": { "type": "string", "description": "经验要求" },
        "skills": { "type": "array", "items": { "type": "string" }, "description": "技能要求" },
        "language": { "type": "string", "description": "语言要求" }
      }
    },
    "preferred_qualifications": { "type": "array", "items": { "type": "string" }, "description": "优先条件" },
    "highlights": { "type": "array", "items": { "type": "string" }, "description": "JD亮点/核心关键词" }
  },
  "required": ["company", "position"]
}
```

# 严格规则
1. **只输出JSON**，不要有任何解释、前缀、后缀、markdown代码块标记
2. **必须包含所有字段**，即使值为空字符串或空数组
3. **skills、preferred_qualifications、highlights 必须是数组格式**
4. 如果原始JD没有某字段，设置为空字符串 "" 或空数组 []
5. 绝对不要输出 ```json 或 ``` 标记
6. 绝对不要输出其他任何文字

# 示例
输入：字节跳动招聘高级产品经理，要求本科以上学历，3年以上经验
输出：{"company":"字节跳动","position":"高级产品经理","department":"","location":"","job_type":"全职","salary":"","description":"","requirements":{"education":"本科以上","experience":"3年以上","skills":[],"language":""},"preferred_qualifications":[],"highlights":[]}
'''


def build_resume_extract_prompt() -> str:
    """Return the single canonical prompt used for PDF and image imports."""
    return (
        "你是忠实、无损的简历文档解析器。完整读取所有页面；双栏或多栏页面必须先判断栏目边界，"
        "再按人类自然阅读顺序读取，不能把左右栏交叉拼接。\n"
        "【忠实性】逐字保留姓名、联系方式、学校、公司、职位、项目名、日期、数字、技术名词和每条可见描述；"
        "禁止总结、润色、改写、补全、合并不同经历或猜测不可见内容；原文没有明确出现的字段必须保持空值，尤其是工作类型，不得为了补全模板而猜测‘全职’或‘实习’。\n"
        "【字段映射】出生年月进入 basics.birth_date；其他未预设的个人字段进入 basics.additional_fields；"
        "研究方向进入 research_interests；奖学金、竞赛奖项和主要荣誉进入 honors；"
        "字段映射必须先遵循原简历的可见栏目边界，而不是仅凭内容语义重新分类：顶层专业技能、技能特长、技术栈栏目下的全部内容"
        "都进入 others.skills，即使其中包含 CET-4/CET-6、英语、证书或认证；只有原文存在独立的证书/资格栏目时才写入"
        "others.certificates，只有原文存在独立的语言/外语能力栏目时才写入 others.languages。禁止把原简历一个栏目拆成多个新栏目，"
        "也不要跨数组重复同一内容。若一个可见栏目标题同时包含语言、荣誉、奖项、论文或证书等多个类别，必须保留为一个"
        "custom_sections 项目，保留原标题和原阅读顺序，不得为了套用系统栏目而拆成多个数组。不能把顶层专业技能放入 custom_sections。项目经历内部若存在独立的‘技术栈’、‘技术选型’、‘使用技术’或‘技术工具’标题，才将该标题及其原文内容写入对应项目的 content_blocks，semantic_role=tech_stack；项目内部技术栈不能写入 others.skills，不能仅凭正文出现技术名词创建该块，"
        "也不能把荣誉混入 certificates。\n"
        "【文字格式】在生成 JSON 前先按页面阅读顺序在内部建立带字重的逐行转写。以下固定标题字段不受原文视觉字重影响，必须默认加粗：basics.name、basics.target_position、education.school_name、work_experience.company_name、work_experience.job_title、project_experience.project_name，以及技术栈、工作简介、工作职责、项目简介和项目职责的 label（label_bold=true）。以下固定字段必须保持普通字重，不得写 **：基本信息中的性别、出生年月、手机、邮箱和其他基本信息；教育经历中的学校标签、学历、专业、绩点、排名、日期；工作/实习经历中的工作类型、日期；项目经历中的角色、日期。"
        "其余编辑内容中的大输入框需保留段落内部真实存在的重点词汇粗体，但只保留原文有明确视觉证据的局部粗体：只有能确认原文字符确实使用粗体时，才使用成对的 **文字** 标记；段落或分点开头出现完整粗体片段并紧接冒号/中文冒号或其他分隔符（例如 **重点内容**：XXXXX）时，必须优先检查并保留开头实际粗体片段，这是高优先级的局部粗体证据；只标记冒号前实际粗体范围，不延伸到后文。不能因为是英文、缩写、技术名词、数字、百分比或看起来重要就推断加粗。无法确认时保持普通字重，宁可漏标也不要误标。列表按每一条独立判断，条目内部的局部粗体同样要保留。内容块的 label 不要写 ** 标记，使用 label_bold=true/false 表示标签字重；不要输出其他 Markdown 标记，列表序号不要写入 items。\n"
        + CONTENT_STRUCTURE_GUIDANCE
        + "\n"
        "只有上述已识别的语义标题才保留原文标题并设置 label_bold=true；generic 的 label 必须为空。语义标签为空表示保留内容但不显示，不能擅自补回默认标签；"
        "原文中的（1）（2）或 (1)(2) 等编号只作为 items 的边界，items 内不要重复序号。"
        "原文没有项目角色时 role 必须为空，禁止输出‘角色’、‘项目成员’等占位词。\n"
        "【教育经历边界】教育经历栏目下、下一个顶层栏目标题之前的无标题分点，必须按原顺序逐条写入顶层 education_supplement；不要因为内容像奖项、活动或成果就写入 honors。只有原文明确出现独立的荣誉/奖项/奖学金标题时，才写入 honors。\n"
        "【经历粒度】工作和项目经历的全部可见正文统一写入 content_blocks；没有语义标题的内容使用 semantic_role=generic，不能写入旧的 details 或其他未声明字段；"
        "论文完整内容在原文存在独立论文栏目时逐条写入顶层 publications；若论文与语言、荣誉、证书等共用一个可见栏目标题，"
        "混合栏目保留规则优先，此时整栏只能作为一个 custom_sections 项目保存，不得拆分。GPA、满分、排名进入对应字段。\n"
        "【兜底保留】任何不能可靠映射到固定字段的原栏目，都必须按原栏目标题和阅读顺序写入 custom_sections，"
        "绝对不能因为 Schema 没有同名字段而省略。不要重复写入已经映射的内容。\n"
        "固定字段的字重规则优先于原文视觉差异：即使原文把学历、专业或日期加粗，导入后也不要给这些固定字段写 **；用户需要时可在编辑内容中手动加粗。大输入框中的局部粗体仍按上一条规则保留。\n"
        "【输出】文件中不存在的字段使用空字符串或空数组；basics.photo 留空；formatting_version 固定为 4，"
        "以便没有明确粗体依据的字段保持普通字重。"
        "只输出符合下面 JSON Schema 的 JSON 对象，不要输出 Markdown、注释或其他文字。JSON Schema：\n"
        + json.dumps(Resume.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
    )



# =============================================================================
# LangChain Tools
# =============================================================================

@tool
def fix_unquoted_json_strings(content: str) -> str:
    """
    修复JSON中未转义的双引号问题。

    LLM在生成JSON时，可能会在字符串值内部使用双引号（如 "Pre-download"），
    但忘记转义成 \"。这个函数尝试检测并修复这种情况。
    """
    import re

    # 尝试直接解析
    try:
        json.loads(content)
        return content
    except json.JSONDecodeError:
        pass

    # 修复策略：使用更智能的方式处理
    # 遍历JSON，逐字符处理，跟踪是否在字符串内部
    result = []
    i = 0
    n = len(content)

    while i < n:
        char = content[i]

        # 检查是否是转义序列的一部分
        if char == '\\' and i + 1 < n:
            # 这是一个转义字符，保留它和下一个字符
            result.append(char)
            result.append(content[i + 1])
            i += 2
            continue

        if char == '"':
            # 找到引号，需要判断是字符串开始/结束，还是字符串内部的引号
            # 从当前位置向前查找，确定是否在字符串内部
            # 简化处理：如果前面有奇数个未转义的反斜杠，则是在字符串内部
            backslash_count = 0
            j = len(result) - 1
            while j >= 0 and result[j] == '\\':
                backslash_count += 1
                j -= 1

            if backslash_count % 2 == 1:
                # 在字符串内部的引号，需要转义
                result.append('\\"')
            else:
                # 字符串边界，保留原样
                result.append(char)
        else:
            result.append(char)

        i += 1

    fixed = ''.join(result)

    # 验证修复后的JSON
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        # 修复失败，返回原始内容（让后续报错更清晰）
        return content


def normalize_and_validate_resume(data: dict, *, include_defaults: bool = False) -> dict:
    """Normalize legacy fields and reject malformed model-generated resumes."""
    normalized = normalize_resume_data(data)
    validated = Resume.model_validate(normalized)
    return validated.model_dump() if include_defaults else normalized


@tool
def save_resume_tool(content: str = "", user_id: int = None, task_id: str = None) -> str:
    """
    旧版兼容工具：不要在正常对话中主动调用，正常修改必须交给 resume_edit。

    将格式化后的简历数据保存到数据库。

    Args:
        content: JSON 格式的简历数据
        user_id: 用户ID（从状态中传递）
    """
    import re
    from .tools import update_resume

    # 检查是否有用户ID
    if user_id is None:
        return "错误：无法确定用户身份，请确保已登录"

    # 清理 markdown 代码块标记
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    content = content.strip()

    # 提取 JSON 对象（如果包含其他文字）
    if not content.startswith('{'):
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            content = match.group()

    # 尝试解析JSON，如果失败则尝试修复后再次解析
    try:
        resume_data = json.loads(content)
    except json.JSONDecodeError as e:
        LOGGER.debug("简历 JSON 首次解析失败，尝试兼容修复")
        fixed_content = fix_unquoted_json_strings(content)
        try:
            resume_data = json.loads(fixed_content)
            LOGGER.debug("简历 JSON 兼容修复成功")
        except json.JSONDecodeError as e2:
            LOGGER.warning("简历 JSON 兼容修复失败: %s", e2)
            return f"保存失败：JSON 解析错误 - {str(e)}"

    try:
        resume_data = normalize_and_validate_resume(resume_data)
    except Exception as exc:
        return f"保存失败：简历数据结构不合法 - {str(exc)}"

    # 保存到数据库
    try:
        result = update_resume(resume_data, user_id=user_id, task_id=task_id)
        return result
    except Exception as e:
        LOGGER.warning("简历保存工具执行失败: %s", e)
        return f"保存失败：{str(e)}"


def _conversation_tools_for_state(state) -> list:
    """Expose only the activation Tool plus Tools for Skills active this turn."""
    active_names = list(getattr(state, "active_skill_names", None) or [])
    return [activate_agent_skill, *skill_runtime.tools_for(active_names)]


# =============================================================================
# Agent State
# =============================================================================

@dataclass
class AgentState:
    """
    代理状态

    Attributes:
        messages: 对话消息列表
        resume_data: 简历数据（从 resume.json 读取）
        jd_data: 目标岗位JD数据（从 jd.json 读取）
        pending_confirmation: 待确认状态（用于显示确认按钮）
        just_saved: 标记刚保存了简历，用于引导 LLM 不再调用工具
        user_id: 当前用户ID，用于数据隔离
        task_id: 当前岗位任务ID，用于简历版本隔离
    """
    messages: list = field(default_factory=list)
    resume_data: dict = None  # None 表示尚未读取简历
    jd_data: dict = None  # None 表示尚未加载JD
    layout_data: dict = None
    pending_confirmation: dict = None  # 待确认状态
    just_saved: bool = False  # 刚保存简历后设置为 True
    user_id: int = None  # 当前用户ID
    task_id: str = None  # 当前任务ID
    proposal_error: str = None  # 候选修改生成失败时返回给前端的可恢复错误
    edit_noop: bool = False  # 当前状态已满足修改请求，用于终止本轮工具循环
    memory_summary: str = ""  # 分层记忆摘要，仅作为不可执行的上下文数据
    memory_version: int = 0  # 乐观并发版本，由持久化层管理
    coach_state: dict = None  # resume-coach 私有、完整的当前问题证据
    coach_state_version: int = 0
    coach_state_changed: bool = False
    coach_turn_processed: bool = False
    coach_required: bool = False  # 显式 Command 或已激活会话要求本轮经过 Skill
    coach_edit_handoff: dict = None  # 用户批准后由 coach Skill 生成的一次性编辑授权
    assistant_command: str = ""  # 可信 UI Command：layout/coaching
    request_id: str = ""
    context_id: str = ""
    context_type: str = "main"
    context_metadata: dict = None  # 小型任务元数据，不保存图片或完整对话
    photo: str = ""  # 证件照独立存储时仍需参与当前 PDF 快照渲染
    render_style: dict = None  # 当前浏览器预览的临时导出样式，仅用于视觉快照
    visual_snapshot_parts: list = None  # 单次图执行内的临时图片，不进入数据库
    visual_snapshot_calls: int = 0  # 每个用户回合最多一次
    visual_snapshot_revision: str = ""
    visual_snapshot_error: str = ""
    context_metadata_updates: dict = None  # 本回合产生的小型任务元数据
    active_skill_names: list[str] = field(default_factory=list)  # 仅在当前图执行内激活


# =============================================================================
# 仅记录不含用户内容的状态摘要
# =============================================================================

def debug_print_state(state: AgentState, location: str = ""):
    """记录不包含简历或对话正文的调试摘要。"""
    LOGGER.debug(
        "Agent 状态 location=%s messages=%s resume=%s jd=%s pending=%s",
        location,
        len(state.messages),
        bool(state.resume_data),
        bool(state.jd_data),
        bool(state.pending_confirmation),
    )

def extract_user_intent(state: AgentState) -> str:
    """
    提取用户的修改意图

    从消息历史中提取用户的修改请求。
    将 HumanMessage 和 AIMessage 拼接成对话历史，让 LLM 判断修改意图。

    Args:
        state: 当前状态

    Returns:
        完整的对话历史文本
    """
    conversation_history = []
    for msg in state.messages:
        if isinstance(msg, HumanMessage):
            conversation_history.append(f"用户: {msg.content}")
        elif isinstance(msg, AIMessage):
            conversation_history.append(f"助手: {msg.content}")
        elif isinstance(msg, ToolMessage):
            tool_name = getattr(msg, 'name', 'unknown')
            conversation_history.append(f"[工具 {tool_name}]: {msg.content}")

    return "\n".join(conversation_history)


_CHANGE_ACTION_RE = re.compile(
    r"(?:修改|更改|改为|改成|替换|更新|填写|写入|新增|添加|删除|移除|补充|优化|调整|设置|设为|变更|"
    r"改写|重写|重新撰写|撰写|润色|重新组织|重组|精炼|扩写|缩写)"
)
_MISSION_POINT_RE = re.compile(
    r"(?:第\s*[0-9一二三四五六七八九十百]+\s*[点条项]|问题\s*[0-9一二三四五六七八九十百]+|上述|前面|这(?:一|几)点|该建议|这些建议)"
)
_MISSION_ACTION_RE = re.compile(
    r"(?:执行|应用|采纳|落实|采用|按(?:照)?|根据|修改|调整|改写|重写|改成|更新|删除|移除|补充|新增|恢复|移动|放到|并入)"
)
_ANALYSIS_INTENT_RE = re.compile(
    r"(?:诊断|点评|评估|审阅|审查|分析|拷打|追问|模拟面试官|修改建议|优化建议|"
    r"不足之处|不足|短板|问题在哪里|匹配度|怎么写|如何写|怎样写|怎么改|如何改|怎样改|如何修改|"
    r"怎么优化|如何优化|怎样优化|怎么完善|如何完善|怎样完善)"
)
_QUESTION_INTENT_RE = re.compile(r"[?？]|(?:怎么|如何|怎样|为什么|为何|是否|能否|可否|请问)")
_DIRECT_APPLY_RE = re.compile(
    r"(?:直接|立即|马上)(?:帮我|替我|给我)?(?:修改|优化|改写|重写|应用)|"
    r"(?:修改|优化|改写|重写)后(?:直接)?(?:应用|保存|写入)|(?:应用|保存|写入)(?:这些|上述|该)"
)
_EXPLICIT_CHANGE_AUTH_RE = re.compile(
    r"(?:把|将).{1,100}(?:改为|改成|替换为|更新为|设为|设置为|删除|移除|新增|添加|补充|移动|放到|并入)|"
    r"(?:基本信息|基本资料|联系方式|姓名|性别|年龄|出生年月|生日|电话|手机|邮箱|所在地|目标岗位|求职岗位|GPA|绩点|满绩|"
    r"排名|学校|专业|学历|学位|教育经历|教育背景|教育经历补充|主要荣誉|论文|研究方向|专业技能|工作经历|工作职责|实习经历|项目经历|项目经验|项目职责|项目|"
    r"公司|职位|研究兴趣|荣誉|奖项|技能|证书|语言|自定义栏目|自定义项目|证书与语言|自我评价|个人总结|其他信息|简历内容)"
    r".{0,30}(?:改为|改成|替换为|更新为|设为|设置为|删除|移除|新增|添加|补充)|"
    r"(?:执行|应用|采纳|落实|采用).{0,30}(?:第\s*[0-9一二三四五六七八九十百]+\s*[点条项]|上述|前面|该建议|这些建议)"
)
_AUTH_CLAUSE_SPLIT_RE = re.compile(
    r"[。！？!?；;\n]+|(?:然后|随后|接着|再|同时|另外|并且|并|回答后)(?=\s*(?:请)?(?:把|将))"
)
_RESUME_DATA_FIELD_RE = re.compile(
    r"(?:基本信息|基本资料|联系方式|姓名|性别|年龄|出生年月|生日|电话|手机|邮箱|所在地|目标岗位|求职岗位|GPA|绩点|满绩|"
    r"排名|学校|专业|学历|学位|教育经历|教育背景|教育经历补充|主要荣誉|论文|研究方向|专业技能|工作经历|工作职责|实习经历|项目经历|项目经验|项目职责|项目|"
    r"公司|职位|研究方向|研究兴趣|荣誉|奖项|技能|证书|语言|自定义栏目|自定义项目|证书与语言|自我评价|个人总结|其他信息|简历内容)"
)
_STYLE_ONLY_RE = re.compile(
    r"(?:字体|字号|颜色|填充|背景|边距|行距|间距|排版|页眉|页脚|标签样式)"
)
_INLINE_FORMAT_ACTION_RE = re.compile(
    r"(?:加粗|设为粗体|设置为粗体|取消加粗|取消粗体|去掉加粗|移除加粗|不再加粗|不加粗|"
    r"(?:改为|设为|设置为)(?:非粗体|普通字重)|恢复普通(?:字重)?)"
)
_INLINE_FORMAT_UNBOLD_RE = re.compile(
    r"(?:取消加粗|取消粗体|去掉加粗|移除加粗|不再加粗|不加粗|"
    r"(?:改为|设为|设置为)(?:非粗体|普通字重)|恢复普通(?:字重)?)"
)
_INLINE_FORMAT_QUOTE_RE = re.compile(r"[“\"‘'](.+?)[”\"’']")
_FONT_SIZE_CHANGE_RE = re.compile(
    r"(?:(?:修改|更改|调整|设置|改成|改为|调到|设为).{0,10}(?:字号|字体大小|\d+(?:\.5)?\s*(?:磅|pt))|"
    r"(?:字号|字体大小).{0,10}(?:修改|更改|调整|设置|改成|改为|调到|设为|\d+(?:\.5)?\s*(?:磅|pt)))",
    re.I,
)

def is_initial_mission_turn(state: AgentState) -> bool:
    """A mission is initial until it has produced its first assistant reply."""
    context_type = str(getattr(state, "context_type", "main") or "main").strip().lower()
    if context_type == "main":
        return False
    if context_type == "layout":
        metadata = getattr(state, "context_metadata", None) or {}
        if "initial_analysis_completed" in metadata:
            return not bool(metadata.get("initial_analysis_completed"))
        # Existing layout missions created before the marker was introduced
        # have already completed their initial command when they contain a
        # recommendation or any assistant reply. Do not restart them.
        if metadata.get("latest_recommendations"):
            return False
        return not any(
            isinstance(message, AIMessage)
            and str(getattr(message, "content", "") or "").strip()
            for message in state.messages or []
        )
    return not any(
        isinstance(message, AIMessage) and str(getattr(message, "content", "") or "").strip()
        for message in state.messages or []
    )


def should_force_initial_visual_snapshot(state: AgentState) -> bool:
    """The trusted layout Command guarantees snapshot Skill execution on entry."""
    return (
        str(getattr(state, "context_type", "main") or "main").strip().lower() == "layout"
        and (
            getattr(state, "assistant_command", "") == "layout"
            or is_initial_mission_turn(state)
        )
        and int(getattr(state, "visual_snapshot_calls", 0) or 0) == 0
        and not (getattr(state, "visual_snapshot_parts", None) or [])
    )


async def _render_current_visual_snapshot(state: AgentState) -> ResumeVisualSnapshot:
    snapshot = await skill_runtime.invoke(
        SNAPSHOT_SKILL_NAME,
        {"reason": "读取当前简历的真实 PDF 页面用于视觉判断"},
        {
            "resume_data": state.resume_data or {},
            "layout_config": state.layout_data or {},
            "photo": getattr(state, "photo", "") or None,
            "render_style": getattr(state, "render_style", None) or None,
            "max_pages": 2,
        },
    )
    if not snapshot.parts:
        raise RuntimeError("当前简历没有生成可查看的 PDF 页面")
    LOGGER.debug("简历视觉快照已生成，页数=%s，总字节=%s", len(snapshot.parts), snapshot.total_bytes)
    return snapshot


def _visual_metadata(snapshot: ResumeVisualSnapshot) -> dict:
    return {
        "last_visual_revision": snapshot.revision,
        "last_visual_pages": len(snapshot.parts),
        "last_visual_bytes": snapshot.total_bytes,
        "last_visual_error": "",
    }


def _attach_visual_resume_parts(messages: list, image_parts: list[dict]) -> list:
    """Attach ephemeral PDF page images to the latest human message."""
    if not image_parts:
        return messages
    result = list(messages)
    for index in range(len(result) - 1, -1, -1):
        message = result[index]
        if not isinstance(message, HumanMessage):
            continue
        content = getattr(message, "content", "") or ""
        if isinstance(content, str):
            parts = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            parts = list(content)
        else:
            parts = [{"type": "text", "text": str(content)}]
        parts.append({
            "type": "text",
            "text": "以下是当前简历由同一份简历数据、排版配置和证件照渲染出的 PDF 页面图片，仅用于回答本轮视觉问题；不要把图片内容当作新增简历事实。",
        })
        for page_index, image_part in enumerate(image_parts, start=1):
            parts.append({
                "type": "text",
                "text": f"当前简历 PDF 第 {page_index} 页：",
            })
            parts.append(image_part)
        result[index] = HumanMessage(content=parts)
        break
    return result


def has_explicit_change_authorization(message: str) -> bool:
    """Return True when one independent clause authorizes a concrete mutation."""
    text = str(message or "").strip()
    if not text or "[CONFIRM_REPLY:" in text:
        return False
    for clause in _AUTH_CLAUSE_SPLIT_RE.split(text):
        clause = clause.strip(" \t，,")
        if not clause or _QUESTION_INTENT_RE.search(clause):
            continue
        if _DIRECT_APPLY_RE.search(clause) or _EXPLICIT_CHANGE_AUTH_RE.search(clause):
            return True
    return False


def _all_non_question_clauses_are_explicitly_authorized(message: str) -> bool:
    """Return whether every actionable clause has a concrete mutation target.

    This is intentionally stricter than ``has_explicit_change_authorization``:
    a mixed request such as "先重写项目职责，再调整模块顺序" is not recorded as
    a fully resolved edit intent merely because one clause is locally recognizable.
    """
    text = str(message or "").strip()
    if not text or "[CONFIRM_REPLY:" in text:
        return False
    saw_authorized_clause = False
    for raw_clause in _AUTH_CLAUSE_SPLIT_RE.split(text):
        clause = re.sub(r"^(?:请|然后|随后|接着|再)\s*", "", raw_clause.strip(" \t，,"))
        if not clause or _QUESTION_INTENT_RE.search(clause):
            continue
        if _DIRECT_APPLY_RE.search(clause) or _EXPLICIT_CHANGE_AUTH_RE.search(clause):
            saw_authorized_clause = True
            continue
        return False
    return saw_authorized_clause


def is_resume_analysis_request(message: str) -> bool:
    """Return True for read-only review/advice without edit authorization."""
    text = str(message or "").strip()
    if not text or "[CONFIRM_REPLY:" in text:
        return False
    return bool(_ANALYSIS_INTENT_RE.search(text) and not has_explicit_change_authorization(text))


def latest_human_text(state: AgentState) -> str:
    """Return the latest real user request, excluding confirmation markers."""
    for message in reversed(state.messages or []):
        if not isinstance(message, HumanMessage):
            continue
        content = getattr(message, "content", "") or ""
        if isinstance(content, list):
            content = "\n".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        content = str(content).strip()
        if content and "[CONFIRM_REPLY:" not in content:
            return content
    return ""


def latest_human_message_text(state: AgentState) -> str:
    """Return the latest human message, including confirmation markers."""
    for message in reversed(state.messages or []):
        if not isinstance(message, HumanMessage):
            continue
        content = getattr(message, "content", "") or ""
        if isinstance(content, list):
            content = "\n".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        return str(content).strip()
    return ""


def is_explicit_resume_change_request(message: str) -> bool:
    """High-precision local fallback gate for explicit resume-data mutations."""
    text = str(message or "").strip()
    if not text or "[CONFIRM_REPLY:" in text:
        return False
    # "How should I improve this resume?" is consultation, not authorization
    # to generate or persist a mutation candidate.
    if is_resume_analysis_request(text):
        return False
    if not (
        _CHANGE_ACTION_RE.search(text)
        and _RESUME_DATA_FIELD_RE.search(text)
    ):
        return False
    # A request that only concerns presentation must stay in the normal dialog
    # path. Mixed data + presentation requests may still produce a data preview.
    data_without_style = _STYLE_ONLY_RE.sub("", text)
    return bool(_RESUME_DATA_FIELD_RE.search(data_without_style))


def is_mission_resume_edit_request(message: str, context_type: str = "main") -> bool:
    """Route a clear mission follow-up to the preview-first edit capability.

    A mission can contain analysis and recommendations as ordinary chat. Only
    an action verb paired with a point reference or a concrete resume field is
    treated as an edit request; this prevents a recommendation such as
    “分析第 1 点” from opening a confirmation preview.
    """
    text = str(message or "").strip()
    if not text or context_type in {"", "main"} or "[CONFIRM_REPLY:" in text:
        return False
    if not _MISSION_ACTION_RE.search(text):
        return False
    if _MISSION_POINT_RE.search(text):
        return True
    return bool(_RESUME_DATA_FIELD_RE.search(text))


def is_inline_format_request(message: str) -> bool:
    text = str(message or "").strip()
    return bool(text and "[CONFIRM_REPLY:" not in text and _INLINE_FORMAT_ACTION_RE.search(text))


def is_font_size_chat_change_request(message: str) -> bool:
    """Identify chat attempts that must be redirected to the bounded modal."""
    text = str(message or "").strip()
    return bool(text and "[CONFIRM_REPLY:" not in text and _FONT_SIZE_CHANGE_RE.search(text))


def build_inline_format_candidate(state: AgentState) -> tuple[dict, str, bool]:
    """Build one deterministic bold/unbold candidate without rewriting text."""
    request_text = latest_human_text(state)
    quoted = _INLINE_FORMAT_QUOTE_RE.findall(request_text)
    if not quoted:
        raise InlineFormatError("请用引号标出需要加粗或取消加粗的原文，例如：把实习经历中的“性能提升 35%”加粗。")
    quote = plain_inline_text(quoted[-1]).strip()
    bold = not bool(_INLINE_FORMAT_UNBOLD_RE.search(request_text))
    current = normalize_resume_data(state.resume_data or {})
    candidate, _reference = format_resume_text(
        current,
        quote,
        bold=bold,
        request_text=request_text,
    )
    return normalize_and_validate_resume(candidate), quote, bold


_LAYOUT_ACTION_RE = re.compile(
    r"(?:布局|排版|样式|位置|对齐|居中|左对齐|右边|同一行|分行|紧凑|舒展|"
    r"标签|黑底|描边|普通文字|隐藏|显示|顺序|放到|移到|标题|圆点|段落|恢复默认|重置)"
)
_LAYOUT_SECTION_NAMES = {
    "教育经历": "education", "教育背景": "education",
    "专业技能": "skills", "技能": "skills",
    "研究方向": "research_interests", "主要荣誉": "honors", "荣誉": "honors",
    "工作经历": "work_experience",
    "项目经历": "project_experience", "其他信息": "others",
    "技能证书": "others", "自我评价": "self_evaluation", "个人总结": "self_evaluation",
}


def is_explicit_layout_change_request(message: str) -> bool:
    text = str(message or "").strip()
    if not text or "[CONFIRM_REPLY:" in text:
        return False
    if is_resume_analysis_request(text):
        return False
    return bool(_LAYOUT_ACTION_RE.search(text))


def build_local_layout_candidate(state: AgentState) -> dict | None:
    """Map common natural-language layout requests to the bounded layout contract."""
    text = latest_human_text(state)
    if "引号" in text or not is_explicit_layout_change_request(text):
        return None
    current = normalize_layout_config(state.layout_data)
    candidate = deepcopy(current)
    recognized = False

    def match_layout(pattern: str, flags: int = 0):
        nonlocal recognized
        match = re.search(pattern, text, flags)
        if match:
            recognized = True
        return match

    if match_layout(
        r"(?:(?:使用|应用|切换到|改成|换成).{0,4}默认(?:排版|布局|样式|风格)|"
        r"(?:恢复|重置)(?:整份简历|全局)?(?:为)?默认(?:排版|布局|样式|风格)?(?:[。！!]|$))",
    ):
        candidate = default_layout_config()
        candidate["basics"] = deepcopy(current["basics"])

    reset_match = match_layout(r"(?:恢复|重置)(?:(教育经历|工作经历|项目经历|其他信息|自我评价))?(?:布局|排版|样式)?(?:为)?默认")
    if reset_match:
        name = reset_match.group(1)
        reset_map = {
            "教育经历": "education", "工作经历": "work_experience",
            "项目经历": "project_experience",
            "其他信息": "others", "自我评价": "self_evaluation",
        }
        candidate = reset_layout_section(candidate, reset_map.get(name, "all"))

    if match_layout(r"(?:整体|全局|整份简历).{0,6}(?:更紧凑|紧凑一些|紧凑版)"):
        candidate = apply_density(candidate, "compact")
    if match_layout(r"(?:整体|全局|整份简历)?.{0,6}(?:更舒展|宽松一些|舒展版)"):
        candidate = apply_density(candidate, "comfortable")
    if match_layout(r"(?:标准密度|恢复标准间距)"):
        candidate = apply_density(candidate, "standard")
    if match_layout(r"(?:模块|章节)?标题.{0,8}(?:不要下划线|去掉下划线|纯文字)"):
        candidate["global"]["titleStyle"] = "plain"
    if match_layout(r"(?:模块|章节)?标题.{0,8}(?:加下划线|使用下划线)"):
        candidate["global"]["titleStyle"] = "underline"

    if match_layout(r"(?:学校|院校|211|985).{0,10}(?:不要黑底|普通文字|纯文字)"):
        candidate["education"]["schoolTagStyle"] = "text"
    if match_layout(r"(?:学校|院校|211|985).{0,10}(?:描边|边框)"):
        candidate["education"]["schoolTagStyle"] = "outline"
    if match_layout(r"(?:学校|院校|211|985).{0,10}(?:使用黑底|改成黑底|设为黑底|实心)"):
        candidate["education"]["schoolTagStyle"] = "filled"
    if match_layout(r"(?:隐藏|不要|去掉).{0,5}(?:学校标签|211|985)"):
        candidate["education"]["schoolTagStyle"] = "hidden"
    for label, field_name in (("GPA", "gpa"), ("绩点", "gpa"), ("排名", "ranking")):
        if match_layout(rf"(?:隐藏|不要|去掉).{{0,5}}{label}|{label}.{{0,5}}(?:隐藏|不要|去掉)", re.I):
            if field_name not in candidate["education"]["hiddenMetrics"]:
                candidate["education"]["hiddenMetrics"].append(field_name)
    if match_layout(r"(?:工作|实习)经历.{0,10}(?:不要圆点|改成段落|段落形式)"):
        candidate["work_experience"]["detailsStyle"] = "paragraph"
    if match_layout(r"项目经历.{0,10}(?:不要圆点|改成段落|段落形式)"):
        candidate["project_experience"]["detailsStyle"] = "paragraph"
    if match_layout(r"(?:工作|实习)经历.{0,10}(?:圆点|列表)"):
        candidate["work_experience"]["detailsStyle"] = "bullets"
    if match_layout(r"(?:隐藏|不要|去掉).{0,5}(?:工作类型|实习类型|全职兼职)"):
        candidate["work_experience"]["showJobType"] = False
    if match_layout(r"项目经历.{0,10}(?:圆点|列表)"):
        candidate["project_experience"]["detailsStyle"] = "bullets"
    if match_layout(r"项目经历.{0,10}(?:隐藏|不要|去掉).{0,4}(?:角色|职责)"):
        candidate["project_experience"]["showRole"] = False
    if match_layout(r"项目经历.{0,10}(?:隐藏|不要|去掉).{0,4}(?:日期|时间)"):
        candidate["project_experience"]["showDate"] = False
    for label, section_id in _LAYOUT_SECTION_NAMES.items():
        if match_layout(rf"(?:隐藏|不要|去掉).{{0,5}}{re.escape(label)}|{re.escape(label)}.{{0,5}}(?:隐藏|不要|去掉)"):
            if section_id not in candidate["global"]["hiddenSections"]:
                candidate["global"]["hiddenSections"].append(section_id)
        if match_layout(rf"(?:显示|恢复显示).{{0,5}}{re.escape(label)}|{re.escape(label)}.{{0,5}}(?:显示|恢复显示)"):
            candidate["global"]["hiddenSections"] = [value for value in candidate["global"]["hiddenSections"] if value != section_id]

    section_pattern = r"教育经历|专业技能|技能|研究方向|主要荣誉|荣誉|工作经历|项目经历|其他信息|自我评价"
    order_match = match_layout(rf"({section_pattern}).{{0,8}}(?:放到|移到)({section_pattern})(前面|后面)")
    if order_match:
        source = _LAYOUT_SECTION_NAMES[order_match.group(1)]
        target = _LAYOUT_SECTION_NAMES[order_match.group(2)]
        order = [value for value in candidate["global"]["sectionOrder"] if value != source]
        target_index = order.index(target) if target in order else len(order)
        order.insert(target_index + (1 if order_match.group(3) == "后面" else 0), source)
        candidate["global"]["sectionOrder"] = order

    title_match = match_layout(r"(教育经历|工作经历|项目经历|其他信息|自我评价)(?:的)?标题(?:改为|改成|叫做)\s*([^，。；;\n]+)")
    if title_match:
        section_id = _LAYOUT_SECTION_NAMES[title_match.group(1)]
        title = _parse_local_value(title_match.group(2))
        if not title:
            return None
        candidate["global"].setdefault("titleOverrides", {}).setdefault(section_id, {})["zh"] = title

    candidate = normalize_layout_config(candidate)
    return candidate if recognized else None


def _plain_response_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if value:
                    parts.append(str(value))
            elif item:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content or "")


_UNVERIFIED_EXECUTION_CLAIM_RE = re.compile(
    r"(?:右侧已显示(?:临时)?预览|"
    r"(?:已|已经|现已)[^。！？\n]{0,80}(?:生成|显示|准备(?:好)?|应用|保存|完成)[^。！？\n]{0,30}(?:修改(?:排版)?预览|预览|候选|简历)|"
    r"我先[^。！？\n]{0,80}(?:生成|显示|应用|保存|完成)[^。！？\n]{0,30}(?:修改(?:排版)?预览|预览|候选|简历))"
)
_NON_EXECUTION_CONTEXT_RE = re.compile(r"(?:建议|可以|是否|如果|无法|不能|未能|尚未|没有)")


def _contains_unverified_execution_claim(content: object) -> bool:
    """Detect positive execution claims when no tool actually ran.

    The check is deliberately limited to completion-style wording.  Advice
    such as "可以生成预览" or an error such as "尚未生成预览" must remain
    ordinary assistant text.
    """
    text = _plain_response_text(content).strip()
    if not text:
        return False
    for match in _UNVERIFIED_EXECUTION_CLAIM_RE.finditer(text):
        sentence_start = max(
            text.rfind("\n", 0, match.start()),
            text.rfind("。", 0, match.start()),
            text.rfind("！", 0, match.start()),
            text.rfind("？", 0, match.start()),
        ) + 1
        sentence_end_candidates = [
            position for position in (
                text.find("\n", match.end()),
                text.find("。", match.end()),
                text.find("！", match.end()),
                text.find("？", match.end()),
            )
            if position >= 0
        ]
        sentence_end = min(sentence_end_candidates, default=len(text))
        sentence = text[sentence_start:sentence_end]
        if not _NON_EXECUTION_CONTEXT_RE.search(sentence):
            return True
    return False


def _sanitize_unverified_execution_reply(content: object) -> str:
    """Replace a model-only success claim with a truthful safe status."""
    text = _plain_response_text(content).strip()
    if not _contains_unverified_execution_claim(text):
        return text
    return (
        "当前尚未生成修改候选。若需要执行修改，请明确修改目标；"
        "系统会在真实生成候选后再提供确认。"
    )


def _edit_intent_metadata_for_response(state: AgentState, response: object) -> dict:
    """Project the current edit-decision lifecycle without storing user text.

    This metadata is only a compact cross-turn hint for the harness.  It does
    not choose a Skill or alter canonical resume data; the model still makes
    the tool decision from the full request and the injected contract.
    """
    request = latest_human_text(state)
    status = "none"
    if _all_non_question_clauses_are_explicitly_authorized(request):
        status = "awaiting_tool"
    elif has_explicit_change_authorization(request):
        status = "needs_clarification"

    for call in list(getattr(response, "tool_calls", None) or []):
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
        if name == "resume_edit":
            status = "tool_called"
            break
    return {"status": status}


_LOCAL_CONTEXTUAL_SECTION_ALIASES = {
    "基本信息": "basics",
    "基本资料": "basics",
    "联系方式": "basics",
    "教育经历": "education",
    "教育背景": "education",
    "教育经历补充": "education_supplement",
    "工作经历": "work_experience",
    "工作职责": "work_experience",
    "项目经历": "project_experience",
    "项目经验": "project_experience",
    "项目职责": "project_experience",
    "其他信息": "others",
    "专业技能": "others.skills",
    "技能": "others.skills",
    "证书": "others.certificates",
    "语言": "others.languages",
    "证书与语言": "others",
    "研究方向": "research_interests",
    "研究兴趣": "research_interests",
    "主要荣誉": "honors",
    "荣誉": "honors",
    "奖项": "honors",
    "论文": "publications",
    "自定义栏目": "custom_sections",
    "自定义项目": "custom_sections",
    "自我评价": "self_evaluation",
    "个人总结": "self_evaluation",
}
_LOCAL_CONTEXTUAL_SECTION_PATTERN = "|".join(
    re.escape(value)
    for value in sorted(_LOCAL_CONTEXTUAL_SECTION_ALIASES, key=len, reverse=True)
)
_LOCAL_CONTEXTUAL_REPLACE_RE = re.compile(
    rf"^\s*(?:请|帮我|麻烦)?\s*(?:将|把)\s*(?P<section>{_LOCAL_CONTEXTUAL_SECTION_PATTERN})\s*"
    r"(?:中的|里面的|里的|内的)\s*"
    r"(?P<old>[^，,。；;\n]+?)\s*"
    r"(?:修改为|更改为|改为|改成|设置为|调整为|替换为)\s*"
    r"(?P<new>[^，,。；;\n]+?)\s*[。.!！]?\s*$"
)
_LOCAL_CONTEXTUAL_REPLACE_SUFFIX_RE = re.compile(
    r"[，,]\s*(?:其余|其他|其余的|其他的)[^。；;\n]{0,40}?"
    r"(?:保持(?:原样|不变)|不变|不要改动|不修改)\s*[。.!！]?\s*$"
)
_LOCAL_CONTEXTUAL_IGNORED_KEYS = {
    "photo",
    "type",
    "semantic_role",
    "label_bold",
    "source_layout_group",
    "source_indent_level",
    "source_marker_type",
}
_LOCAL_BASIC_PATTERNS = {
    "name": re.compile(r"(?:将|把)?\s*姓名\s*(?:修改为|更改为|改为|改成|设置为|调整为)\s*([^，,。；;\n]+)"),
    "target_position": re.compile(r"(?:将|把)?\s*(?:目标岗位|求职岗位|期望岗位)\s*(?:修改为|更改为|改为|改成|设置为|调整为)\s*([^，,。；;\n]+)"),
    "phone": re.compile(r"(?:将|把)?\s*(?:电话|手机号|手机)\s*(?:修改为|更改为|改为|改成|设置为|调整为)\s*([^，,。；;\n]+)"),
    "email": re.compile(r"(?:将|把)?\s*邮箱\s*(?:修改为|更改为|改为|改成|设置为|调整为)\s*([^，,。；;\n]+)"),
    "gender": re.compile(r"(?:将|把)?\s*性别\s*(?:修改为|更改为|改为|改成|设置为|调整为)\s*([^，,。；;\n]+)"),
}
_LOCAL_BASIC_MENTIONS = {
    "name": re.compile(r"姓名"),
    "target_position": re.compile(r"(?:目标岗位|求职岗位|期望岗位)"),
    "phone": re.compile(r"(?:电话|手机号|手机)"),
    "email": re.compile(r"邮箱"),
    "gender": re.compile(r"性别"),
}
_GPA_MENTION_RE = re.compile(r"(?:GPA|绩点)", re.IGNORECASE)
_GPA_ASSIGN_RE = re.compile(
    r"(?:(本科|学士|硕士|研究生|博士|专科|大专)[^，,。；;\n]{0,12})?"
    r"(?:GPA|绩点)\s*(?:修改为|更改为|改为|改成|设置为|调整为)\s*"
    r"(\d+(?:\.\d+)?)\s*(?:/|／)\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_EDUCATION_MENTION_RE = re.compile(r"(?:教育经历|教育背景)")
_LOCAL_EDUCATION_SCHOOL_RE = re.compile(
    r"(?:教育经历|教育背景)[^。；;\n]{0,24}?(?:将|把)\s*"
    r"([^，,。；;：:\n]{2,40}?(?:大学|学院))\s*"
    r"(?:修改为|更改为|改为|改成|设置为|调整为|替换为)\s*"
    r"([^，,。；;\n]{2,40}?(?:大学|学院))"
)


_LOCAL_OUTER_QUOTE_PAIRS = {
    '"': '"', "'": "'", "“": "”", "‘": "’", "「": "」", "『": "』",
}


def _plain_local_value(value: str) -> str:
    return plain_inline_text(str(value or "")).strip()


def _parse_local_value(value: str) -> str | None:
    text = _plain_local_value(value)
    if not text:
        return None
    quote_characters = set(_LOCAL_OUTER_QUOTE_PAIRS) | set(_LOCAL_OUTER_QUOTE_PAIRS.values())
    if text[0] in quote_characters or text[-1] in quote_characters:
        if len(text) < 2 or _LOCAL_OUTER_QUOTE_PAIRS.get(text[0]) != text[-1]:
            return None
        text = text[1:-1].strip()
    return text or None


def _iter_local_text_paths(value: object, path: tuple[str | int, ...] = ()):
    """Yield user-visible text leaves under a known resume module."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _LOCAL_CONTEXTUAL_IGNORED_KEYS:
                continue
            yield from _iter_local_text_paths(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_local_text_paths(child, (*path, index))
    elif isinstance(value, str) and path:
        yield path, value


def _strip_local_replace_suffix(text: str) -> str:
    return _LOCAL_CONTEXTUAL_REPLACE_SUFFIX_RE.sub("", text).strip()


def _parse_local_contextual_replacement(text: str) -> tuple[str, str, str] | None:
    match = _LOCAL_CONTEXTUAL_REPLACE_RE.fullmatch(_strip_local_replace_suffix(text))
    if not match:
        return None
    section = _LOCAL_CONTEXTUAL_SECTION_ALIASES[match.group("section")]
    old_value = _parse_local_value(match.group("old"))
    new_value = _parse_local_value(match.group("new"))
    if not old_value or not new_value:
        return None
    return section, old_value, new_value


def _set_local_text_path(candidate: dict, path: tuple[str | int, ...], value: str) -> bool:
    if not path:
        return False
    parent: object = candidate
    try:
        for token in path[:-1]:
            parent = parent[token]  # type: ignore[index]
        leaf = path[-1]
        current = parent[leaf]  # type: ignore[index]
        parent[leaf] = _inherit_whole_field_format(current, value)  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return False
    return True


def build_local_contextual_replace_candidate(current: dict, text: str) -> dict | None:
    """Resolve one or more exact module-scoped literal replacements locally."""
    clauses = _split_local_edit_clauses(text)
    if not clauses:
        return None

    candidate = deepcopy(current)
    for clause in clauses:
        parsed = _parse_local_contextual_replacement(clause)
        if parsed is None:
            return None
        section, old_value, new_value = parsed
        section_path = tuple(section.split("."))
        root: object = candidate
        for token in section_path:
            if not isinstance(root, dict):
                root = None
                break
            root = root.get(token)
        matches = [
            (path, value)
            for path, value in _iter_local_text_paths(root, section_path)
            if _plain_local_value(value) == old_value
        ]
        if len(matches) != 1:
            return None
        if not _set_local_text_path(candidate, matches[0][0], new_value):
            return None

    return normalize_and_validate_resume(candidate)


def _inherit_whole_field_format(current_value: object, new_value: str) -> str:
    """Keep whole-field bold when a deterministic edit replaces only its text."""
    current_text = str(current_value or "").strip()
    clean_new_value = plain_inline_text(str(new_value or "")).strip()
    if re.fullmatch(r"\*\*.+?\*\*", current_text, flags=re.DOTALL):
        return f"**{clean_new_value}**"
    return clean_new_value


def _education_index_for_gpa(current: dict, qualifier: str | None, new_gpa: str) -> int | None:
    education = current.get("education") or []
    if not education:
        return None
    if qualifier:
        groups = {
            "本科": ("本科", "学士"), "学士": ("本科", "学士"),
            "硕士": ("硕士", "研究生"), "研究生": ("硕士", "研究生"),
            "博士": ("博士",), "专科": ("专科", "大专"), "大专": ("专科", "大专"),
        }
        needles = groups.get(qualifier, (qualifier,))
        matches = [
            index for index, item in enumerate(education)
            if any(needle in str(item.get("degree", "")) for needle in needles)
        ]
        return matches[0] if len(matches) == 1 else None
    if len(education) == 1:
        return 0
    same_value = [
        index for index, item in enumerate(education)
        if str(item.get("gpa", "")).strip() == new_gpa
    ]
    if len(same_value) == 1:
        return same_value[0]
    populated = [index for index, item in enumerate(education) if item.get("gpa")]
    return populated[0] if len(populated) == 1 else None


def _build_local_edit_candidate_for_text(state: AgentState, text: str) -> dict | None:
    """Return a candidate only when every requested edit is locally unambiguous."""
    if (
        not text
        or "引号" in text
        or "[CONFIRM_REPLY:" in text
        or _QUESTION_INTENT_RE.search(text)
        or is_resume_analysis_request(text)
    ):
        return None

    current = normalize_resume_data(state.resume_data or {})
    contextual_candidate = build_local_contextual_replace_candidate(current, text)
    if contextual_candidate is not None:
        return contextual_candidate

    candidate = deepcopy(current)
    parsed_fields: set[str] = set()
    mentioned_fields = {
        field_name for field_name, pattern in _LOCAL_BASIC_MENTIONS.items()
        if pattern.search(text)
    }

    if _EDUCATION_MENTION_RE.search(text):
        mentioned_fields.add("education_school")
        school_match = _LOCAL_EDUCATION_SCHOOL_RE.search(text)
        if not school_match:
            return None
        source_school = _parse_local_value(school_match.group(1))
        target_school = _parse_local_value(school_match.group(2))
        if not source_school or not target_school:
            return None
        education = candidate.get("education") or []
        source_matches = [
            index for index, item in enumerate(education)
            if _plain_local_value(item.get("school_name", "")) == source_school
        ]
        target_matches = [
            index for index, item in enumerate(education)
            if _plain_local_value(item.get("school_name", "")) == target_school
        ]
        if len(source_matches) == 1:
            index = source_matches[0]
            education[index]["school_name"] = _inherit_whole_field_format(
                education[index].get("school_name", ""), target_school
            )
        elif not source_matches and len(target_matches) == 1:
            # 重复提交同一修改时走本地无变更结果，不再等待结构化模型。
            pass
        else:
            return None
        parsed_fields.add("education_school")

    for field_name, pattern in _LOCAL_BASIC_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        value = _parse_local_value(match.group(1))
        if not value or (field_name == "gender" and value not in {"男", "女", "其他"}):
            return None
        basics = candidate.setdefault("basics", {})
        basics[field_name] = _inherit_whole_field_format(
            basics.get(field_name, ""), value
        )
        parsed_fields.add(field_name)

    if _GPA_MENTION_RE.search(text):
        mentioned_fields.add("gpa")
        gpa_match = _GPA_ASSIGN_RE.search(text)
        if not gpa_match:
            return None
        qualifier, gpa, scale = gpa_match.groups()
        education_index = _education_index_for_gpa(current, qualifier, gpa)
        if education_index is None:
            return None
        candidate["education"][education_index]["gpa"] = gpa
        candidate["education"][education_index]["gpa_scale"] = scale
        parsed_fields.add("gpa")

    if not mentioned_fields or parsed_fields != mentioned_fields:
        return None
    return normalize_and_validate_resume(candidate)


_EDIT_CLAUSE_SPLIT_RE = re.compile(
    r"[。；;\n]+|(?:然后|随后|接着|再|回答后|并且|同时|另外|并)(?=(?:请|把|将|再|隐藏|显示|恢复|重置|调整|修改|更改|改写|重写|润色|优化|补全|完善|让|移到|放到))"
)


def _split_local_edit_clauses(text: str) -> list[str]:
    """Split independent edit clauses without assigning meaning to them."""
    return [
        value.strip().strip(" \t，,")
        for value in _EDIT_CLAUSE_SPLIT_RE.split(text)
        if value.strip().strip(" \t，,")
    ]


def build_local_edit_candidate(state: AgentState) -> dict | None:
    """Build one resume candidate using the shared local parser vocabulary."""
    return _build_local_edit_candidate_for_text(state, latest_human_text(state))


def _resolve_local_edit_candidates(
    state: AgentState,
) -> tuple[dict | None, dict | None, bool]:
    """Resolve every independent clause into one combined resume/layout candidate."""
    text = latest_human_text(state)
    if (
        not text
        or _QUESTION_INTENT_RE.search(text)
        or is_resume_analysis_request(text)
    ):
        return None, None, False
    clauses = _split_local_edit_clauses(text)
    if not clauses:
        return None, None, False

    resume_candidate = normalize_resume_data(state.resume_data or {})
    layout_candidate = normalize_layout_config(state.layout_data)
    for clause in clauses:
        clause_state = replace(
            state,
            messages=[HumanMessage(content=clause)],
            resume_data=resume_candidate,
            layout_data=layout_candidate,
        )
        local_resume = _build_local_edit_candidate_for_text(clause_state, clause)
        local_layout = build_local_layout_candidate(clause_state)
        if local_resume is None and local_layout is None:
            return None, None, False
        if local_resume is not None:
            resume_candidate = local_resume
        if local_layout is not None:
            layout_candidate = local_layout

    return resume_candidate, layout_candidate, True


def classify_local_edit_request(state: AgentState) -> str:
    """Classify a local edit attempt without interpreting unresolved language.

    ``resolved`` and ``resolved_noop`` are the only states eligible for the
    deterministic route.  Anything that cannot be resolved completely stays
    in the conversation node, where the model can clarify it.
    """
    current_resume = normalize_resume_data(state.resume_data or {})
    current_layout = normalize_layout_config(state.layout_data)
    resume_candidate, layout_candidate, resolved = _resolve_local_edit_candidates(state)
    if not resolved:
        return "unresolved"
    changed = resume_candidate != current_resume or layout_candidate != current_layout
    return "resolved" if changed else "resolved_noop"


def is_fully_resolved_local_edit_request(state: AgentState) -> bool:
    """Return True only when every independent edit clause is deterministic."""
    return classify_local_edit_request(state) in {"resolved", "resolved_noop"}


def _preview_summary(changes: list[dict]) -> str:
    has_layout_change = any(change.get("kind") == "layout" for change in changes)
    lines = [
        "已根据你的要求生成排版修改预览："
        if has_layout_change else "已根据你的要求生成修改预览：",
        "",
    ]
    lines.extend(
        (
            f"- {change['label']}："
            + (
                "；".join(
                    f"{detail.get('field_label', detail['field'])}：{detail['before_display']} → {detail['after_display']}"
                    for detail in change.get("details", [])
                )
                if change.get("kind") == "layout"
                else f"{change['before_display']} → {change['after_display']}"
            )
        )
        for change in changes
    )
    action_hint = (
        "请在下方选择全部接受、仅应用选中项或全部拒绝。"
        if len(changes) > 1
        else "请在下方选择接受或拒绝。"
    )
    lines.extend(["", f"右侧已显示临时预览；接受前不会保存。{action_hint}"])
    return "\n".join(lines)


def make_pending_confirmation(
    state: AgentState,
    candidate: dict | None = None,
    layout_candidate: dict | None = None,
) -> dict:
    """Build the same pending-confirmation contract for tool and fallback paths."""
    current = normalize_resume_data(state.resume_data or {})
    current_layout = normalize_layout_config(state.layout_data)
    candidate = normalize_resume_data(candidate if candidate is not None else current)
    layout_candidate = normalize_layout_config(
        layout_candidate if layout_candidate is not None else current_layout
    )
    resume_changes = build_resume_changes(current, candidate)
    layout_changes = build_layout_changes(current_layout, layout_candidate)
    changes = resume_changes + layout_changes
    if not changes:
        raise ValueError("没有检测到可应用的简历修改")
    confirm_id = str(uuid.uuid4())[:8]
    tool_args = {
        "content": json.dumps(candidate, ensure_ascii=False),
        "layout_content": json.dumps(layout_candidate, ensure_ascii=False),
        "user_id": state.user_id,
        "task_id": state.task_id,
    }
    return {
        "confirm_id": confirm_id,
        "content": "是否确认修改简历？",
        "options": [
            {"label": "全部接受", "value": "confirm", "style": "primary"},
            {"label": "全部拒绝", "value": "cancel", "style": "default"},
        ],
        "tool_name": "save_resume_tool",
        "tool_args": tool_args,
        "base_hash": resume_digest(current),
        "base_layout": current_layout,
        "resume_candidate": candidate,
        "layout_candidate": layout_candidate,
        "changes": changes,
        "status": "pending",
    }


async def direct_edit_node(state: AgentState) -> dict:
    """Build a preview for unambiguous field assignments without calling an LLM."""
    current = normalize_resume_data(state.resume_data or {})
    current_layout = normalize_layout_config(state.layout_data)
    metadata_updates = dict(getattr(state, "context_metadata_updates", None) or {})
    if is_font_size_chat_change_request(latest_human_text(state)):
        metadata_updates["edit_intent_state"] = {"status": "none"}
        return {
            "messages": list(state.messages) + [AIMessage(content=(
                "字号不会通过对话命令直接修改。请打开简历预览上方的“排版”，进入“设置各部分字号”，"
                "按半磅选择姓名、用户信息、模块标题、条目标题、字段标签和正文字号；弹窗会先实时预览，点击“应用”后才保存。"
            ))],
            "resume_data": current,
            "jd_data": state.jd_data or {},
            "layout_data": current_layout,
            "pending_confirmation": None,
            "proposal_error": None,
            "just_saved": False,
            "user_id": state.user_id,
            "task_id": state.task_id,
            "context_metadata_updates": metadata_updates,
        }
    await acquire_current_edit_lock()
    inline_request = is_inline_format_request(latest_human_text(state))
    inline_quote = ""
    inline_bold = True
    local_layout_candidate = None
    if inline_request:
        try:
            resume_candidate, inline_quote, inline_bold = build_inline_format_candidate(state)
        except InlineFormatError as exc:
            metadata_updates["edit_intent_state"] = {"status": "none"}
            return {
                "messages": list(state.messages) + [AIMessage(content=str(exc))],
                "resume_data": current,
                "jd_data": state.jd_data or {},
                "layout_data": current_layout,
                "pending_confirmation": None,
                "proposal_error": None,
                "just_saved": False,
                "user_id": state.user_id,
                "task_id": state.task_id,
                "context_metadata_updates": metadata_updates,
            }
    else:
        resume_candidate, local_layout_candidate, resolved = _resolve_local_edit_candidates(state)
        if not resolved:
            raise ValueError("本地修改路由收到无法确定解析的请求")
    if inline_request:
        local_layout_candidate = build_local_layout_candidate(state)
    candidate = resume_candidate if resume_candidate is not None else current
    layout_candidate = local_layout_candidate if local_layout_candidate is not None else current_layout
    if resume_candidate is None and local_layout_candidate is None:
        raise ValueError("本地修改路由收到无法确定解析的请求")
    changes = build_resume_changes(current, candidate) + build_layout_changes(current_layout, layout_candidate)
    if not changes:
        assistant_message = AIMessage(content="当前简历已经符合这项要求，没有需要应用的修改。")
        pending = None
    else:
        pending = make_pending_confirmation(state, candidate, layout_candidate)
        if inline_request:
            action_label = "加粗" if inline_bold else "取消加粗"
            assistant_message = AIMessage(content=(
                f"已生成格式预览：将“{inline_quote}”{action_label}。\n\n"
                "右侧已显示临时预览；接受前不会保存。"
            ))
        else:
            assistant_message = AIMessage(content=_preview_summary(changes))
    LOGGER.debug("本地修改候选生成完成，变更数=%s", len(changes))
    metadata_updates["edit_intent_state"] = {
        "status": "awaiting_confirmation" if pending else "none",
    }
    return {
        "messages": list(state.messages) + [assistant_message],
        "resume_data": current,
        "jd_data": state.jd_data or {},
        "layout_data": current_layout,
        "pending_confirmation": pending,
        "proposal_error": None,
        "just_saved": False,
        "user_id": state.user_id,
        "task_id": state.task_id,
        "context_metadata_updates": metadata_updates,
    }


async def proposal_generator_node(state: AgentState) -> dict:
    """Legacy graph entry kept for compatibility; normal routing uses the tool path."""
    start_time = time.time()
    current = normalize_resume_data(state.resume_data or {})
    current_layout = normalize_layout_config(state.layout_data)
    metadata_updates = dict(getattr(state, "context_metadata_updates", None) or {})

    try:
        metadata = state.context_metadata or {}
        preview = await _generate_resume_edit_preview(
            state,
            metadata.get("resume_operations", ()),
            metadata.get("layout_operations", ()),
        )
        LOGGER.debug(
            "修改候选生成完成，耗时=%.2fs，存在待确认=%s",
            time.time() - start_time,
            bool(preview.get("pending_confirmation")),
        )
        metadata_updates["edit_intent_state"] = {
            "status": "awaiting_confirmation" if preview.get("pending_confirmation") else "none",
        }
        return {
            "messages": list(state.messages) + [AIMessage(content=preview.get("message", ""))],
            "resume_data": current,
            "jd_data": state.jd_data or {},
            "layout_data": current_layout,
            "pending_confirmation": preview.get("pending_confirmation"),
            "proposal_error": None,
            "just_saved": False,
            "user_id": state.user_id,
            "task_id": state.task_id,
            "context_metadata_updates": metadata_updates,
        }
    except Exception as exc:
        LOGGER.warning("修改候选生成失败: %s", exc)
        metadata_updates["edit_intent_state"] = {"status": "none"}
        return {
            "messages": list(state.messages),
            "resume_data": current,
            "jd_data": state.jd_data or {},
            "layout_data": current_layout,
            "pending_confirmation": None,
            "proposal_error": "本次修改无法安全生成确认预览，系统未对简历做任何更改。",
            "just_saved": False,
            "user_id": state.user_id,
            "task_id": state.task_id,
            "context_metadata_updates": metadata_updates,
        }


def _coerce_resume_edit_operations(value, *, field_name: str) -> tuple[dict, ...]:
    """Accept only JSON-shaped operation lists from the tool call."""
    if value in (None, "", []):
        return ()
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ResumeEditOperationError(f"{field_name} 必须是结构化操作列表") from exc
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, dict) for item in value):
        raise ResumeEditOperationError(f"{field_name} 必须是结构化操作列表")
    return tuple(deepcopy(item) for item in value)


async def _generate_resume_edit_preview(
    state: AgentState,
    resume_operations=(),
    layout_operations=(),
) -> dict:
    """Run the generic edit skill with model-resolved operations only."""
    await acquire_current_edit_lock()
    current = normalize_resume_data(state.resume_data or {})
    current_layout = normalize_layout_config(state.layout_data)
    edit_result = await skill_runtime.invoke(
        EDIT_SKILL_NAME,
        {
            "answer_text": "",
            "resume_operations": list(resume_operations or ()),
            "layout_operations": list(layout_operations or ()),
        },
        {
            "resume_data": current,
            "layout_config": current_layout,
            "jd_data": state.jd_data or {},
            "context_type": getattr(state, "context_type", "main") or "main",
            "base_revision": resume_digest(current),
            "conversation_context": "",
        },
    )
    candidate = edit_result.resume_data
    layout_candidate = edit_result.layout_config
    changes = build_resume_changes(current, candidate) + build_layout_changes(current_layout, layout_candidate)
    if not changes:
        return {
            "pending_confirmation": None,
            "already_satisfied": True,
            "message": "当前简历已经符合这项要求，没有需要应用的修改。",
            "resume_data": current,
            "layout_data": current_layout,
        }
    pending = make_pending_confirmation(state, candidate, layout_candidate)
    return {
        "pending_confirmation": pending,
        "message": _preview_summary(changes),
        "resume_data": current,
        "layout_data": current_layout,
    }


# =============================================================================
# Nodes
# =============================================================================

async def conversation_node(state: AgentState) -> dict:
    """
    Conversation LLM 节点

    处理用户对话，根据情况决定是否需要读取文件或转向 formatter
    """
    debug_print_state(state, "conversation_node_ENTER")
    
    start_time = time.time()
    
    # 只记录规模信息，不记录简历或对话正文。
    total_tokens = 0
    for msg in state.messages:
        content = getattr(msg, 'content', '')
        total_tokens += estimate_tokens(content)
    
    LOGGER.debug(
        "对话节点开始，消息数=%s，估算 token=%s",
        len(state.messages),
        total_tokens,
    )

    latest_request = latest_human_text(state)
    coach_state = deepcopy(getattr(state, "coach_state", None) or {})
    coach_active = bool(coach_state.get("active"))
    context_type = getattr(state, "context_type", "main") or "main"
    mission_initial_turn = is_initial_mission_turn(state)
    visual_parts = list(getattr(state, "visual_snapshot_parts", None) or [])
    visual_calls = int(getattr(state, "visual_snapshot_calls", 0) or 0)
    visual_revision = str(getattr(state, "visual_snapshot_revision", "") or "")
    visual_error = str(getattr(state, "visual_snapshot_error", "") or "")
    metadata_updates = dict(getattr(state, "context_metadata_updates", None) or {})
    active_skill_names = list(getattr(state, "active_skill_names", None) or [])

    # A layout-advice mission has one explicit first-turn guarantee.  Every
    # later visual read is a model tool decision rather than a keyword gate.
    if should_force_initial_visual_snapshot(state):
        try:
            snapshot = await _render_current_visual_snapshot(state)
        except Exception as exc:
            visual_error = str(exc)
            harness_metrics.increment("resume_visual_render_failures_total")
            LOGGER.warning("首次排版快照生成失败: %s", exc)
            return {
                "messages": list(state.messages) + [AIMessage(content=(
                    "当前简历快照生成失败，本轮没有进行排版分析，也没有修改简历。请稍后重试。"
                ))],
                "resume_data": state.resume_data or {},
                "jd_data": state.jd_data or {},
                "layout_data": normalize_layout_config(state.layout_data),
                "pending_confirmation": None,
                "proposal_error": None,
                "just_saved": False,
                "user_id": state.user_id,
                "task_id": state.task_id,
                "visual_snapshot_parts": [],
                "visual_snapshot_calls": 1,
                "visual_snapshot_revision": "",
                "visual_snapshot_error": visual_error,
                "context_metadata_updates": {
                    **metadata_updates,
                    "last_visual_error": type(exc).__name__,
                },
            }
        visual_parts = snapshot.parts
        visual_calls = 1
        visual_revision = snapshot.revision
        visual_error = ""
        metadata_updates.update(_visual_metadata(snapshot))

    visual_attached = bool(visual_parts)
    layout_context_mode = (
        "full"
        if mission_initial_turn
        or visual_attached
        or is_explicit_layout_change_request(latest_request)
        else "capability"
    )
    messages = build_conversation_context(
        base_prompt=CONVERSATION_PROMPT,
        resume_data=state.resume_data,
        jd_data=state.jd_data,
        layout_data=state.layout_data,
        state_messages=state.messages,
        just_saved=getattr(state, "just_saved", False),
        memory_summary=getattr(state, "memory_summary", "") or "",
        context_type=context_type,
        context_metadata=getattr(state, "context_metadata", None) or {},
        layout_context_mode=layout_context_mode,
        mission_initial_turn=mission_initial_turn,
    )
    if messages and isinstance(messages[0], SystemMessage):
        messages[0] = SystemMessage(content=(
            str(messages[0].content)
            + skill_runtime.catalog_context()
            + skill_runtime.active_instructions_context(active_skill_names)
        ))
        if COACH_SKILL_NAME in active_skill_names:
            messages[0] = SystemMessage(content=(
                str(messages[0].content)
                + "\n\n【resume-coach 私有状态】\n"
                + "以下状态仅供当前已激活 Skill 使用。每轮必须以完整证据为依据，"
                  "不得把结论摘要当作用户事实。\n"
                + json.dumps(coach_state, ensure_ascii=False, indent=2)
            ))
    if visual_attached:
        messages = _attach_visual_resume_parts(messages, visual_parts)
        LOGGER.debug("已附加 %s 页临时视觉上下文", len(visual_parts))
    
    # 计算实际发送给 LLM 的 tokens 总数
    llm_input_tokens = 0
    for msg in messages:
        msg_content = getattr(msg, 'content', '')
        llm_input_tokens += estimate_tokens(msg_content)
    
    if getattr(state, 'just_saved', False):
        LOGGER.debug("已向 LLM 添加本轮刚保存提示")

    # 调用 LLM
    LOGGER.debug("开始调用 LLM，消息数=%s，估算 token=%s", len(messages), llm_input_tokens)
    try:
        # Skill selection belongs to the model. The execution layer remains
        # responsible for schema validation, preview-only edits, confirmation,
        # and the one-snapshot-per-turn guard.
        forced_coach_turn = bool(
            getattr(state, "coach_required", False)
            and not getattr(state, "coach_turn_processed", False)
        )
        model = conversation_llm.bind_tools(
            _conversation_tools_for_state(state),
            tool_choice=COACH_TOOL_NAME if forced_coach_turn else "auto"
        )
        # 不要添加 stop 序列，否则可能导致工具名称被截断
        # 增加超时时间到120秒，因为上下文可能较大
        async with asyncio.timeout(120.0):
            response = await model.ainvoke(messages)
    except asyncio.TimeoutError:
        LOGGER.warning("LLM 调用超时，消息数=%s", len(messages))
        if visual_attached:
            raise TimeoutError("视觉快照分析超时，请稍后重试")
        raise TimeoutError("LLM 调用超时，请稍后重试")
    except Exception as e:
        LOGGER.warning("LLM 调用失败: %s", e)
        if visual_attached:
            raise RuntimeError(f"视觉快照分析失败：{str(e)}")
        raise RuntimeError(f"LLM 调用失败: {str(e)}")

    response_updates = {}
    if isinstance(getattr(response, "content", None), str):
        response_content = response.content
        if not (getattr(response, "tool_calls", None) or []):
            response_content = _sanitize_unverified_execution_reply(response_content)
        response_updates["content"] = localize_user_visible_layout_text(response_content)
    tool_calls = deepcopy(getattr(response, "tool_calls", None) or [])
    for call in tool_calls:
        args = call.get("args") if isinstance(call, dict) else None
        if isinstance(args, dict) and isinstance(args.get("answer_text"), str):
            args["answer_text"] = localize_user_visible_layout_text(args["answer_text"])
    metadata_updates["edit_intent_state"] = _edit_intent_metadata_for_response(state, response)
    if tool_calls:
        response_updates["tool_calls"] = tool_calls
    if response_updates:
        response = response.model_copy(update=response_updates)

    elapsed_time = time.time() - start_time
    LOGGER.debug(
        "LLM 调用完成，耗时=%.2fs，工具调用数=%s，无效工具调用数=%s",
        elapsed_time,
        len(getattr(response, "tool_calls", None) or []),
        len(getattr(response, "invalid_tool_calls", None) or []),
    )

    if context_type == "layout" and mission_initial_turn:
        metadata_updates["initial_analysis_completed"] = True

    # 如果原始消息中有带 tool_calls 的 AIMessage，清除它们
    cleaned_messages = []
    seen_contents = set()  # 用于去重
    for msg in state.messages:
        content = getattr(msg, 'content', None)
        # 跳过 list 类型的内容（不可哈希）
        if isinstance(content, list):
            content = str(content)
        msg_key = (content, type(msg).__name__)
        if msg_key[0] and msg_key[0] not in seen_contents:
            seen_contents.add(msg_key[0])
            if isinstance(msg, AIMessage) and msg.tool_calls:
                cleaned_messages.append(AIMessage(content=msg.content, tool_calls=[]))
            else:
                cleaned_messages.append(msg)

    # 返回所有消息：原始消息 + 新响应（这样上下文才能累积）
    all_messages = list(state.messages) + [response]
    
    # 如果有 pending_confirmation 且状态为有效字典，保留
    # 如果是 False 或 None，清除
    pending_conf = state.pending_confirmation if isinstance(state.pending_confirmation, dict) else None
    
    # 规范化 pending_confirmation：确保是字典或 None
    if pending_conf is None or not isinstance(pending_conf, dict):
        pending_conf = None
    
    # 检查用户是否发送了新消息（不是确认回复）
    # 如果是，标记为需要清除 pending_confirmation
    user_is_confirming = '[CONFIRM_REPLY:' in latest_human_message_text(state)
    
    # 如果用户发送了新消息但不是确认回复，清除 pending_confirmation
    if not user_is_confirming and state.pending_confirmation is not None:
        LOGGER.debug("用户发送新消息，清除原待确认状态")
        pending_conf = None
    
    output_state = {
        "messages": all_messages,
        "resume_data": state.resume_data or {},
        "jd_data": state.jd_data or {},
        "layout_data": normalize_layout_config(state.layout_data),
        "pending_confirmation": pending_conf,
        "just_saved": False,  # 清除 just_saved 标记
        "user_id": state.user_id,  # 保留用户ID
        "task_id": state.task_id,
        "memory_summary": getattr(state, "memory_summary", "") or "",
        "memory_version": getattr(state, "memory_version", 0) or 0,
        # Image bytes are consumed by this invocation and deliberately cleared
        # before persistence or any later turn.
        "visual_snapshot_parts": [],
        "visual_snapshot_calls": visual_calls,
        "visual_snapshot_revision": visual_revision,
        "visual_snapshot_error": visual_error,
        "context_metadata_updates": metadata_updates,
        "active_skill_names": active_skill_names,
        "coach_state": coach_state,
        "coach_state_version": getattr(state, "coach_state_version", 0) or 0,
        "coach_state_changed": getattr(state, "coach_state_changed", False),
        "coach_turn_processed": getattr(state, "coach_turn_processed", False),
        "coach_required": coach_active or getattr(state, "coach_required", False),
        "coach_edit_handoff": getattr(state, "coach_edit_handoff", None),
        "assistant_command": getattr(state, "assistant_command", "") or "",
    }
    
    # 创建临时状态对象用于调试
    class DebugState:
        def __init__(self, d):
            self.messages = d.get("messages", [])
            self.resume_data = d.get("resume_data")
            self.jd_data = d.get("jd_data")
            self.pending_confirmation = d.get("pending_confirmation")
    
    debug_print_state(DebugState(output_state), "conversation_node_EXIT")
    
    return output_state


async def tool_node(state: AgentState) -> dict:
    """
    工具执行节点

    执行 LLM 调用的工具并生成预览
    支持延迟确认流程：修改工具不会立即保存，而是触发前端确认
    """
    debug_print_state(state, "tool_node_ENTER")
    
    start_time = time.time()
    LOGGER.debug("工具节点开始")
    last_message = state.messages[-1]
    user_content = getattr(last_message, 'content', '') or ''
    metadata_updates = dict(getattr(state, "context_metadata_updates", None) or {})
    active_skill_names = list(getattr(state, "active_skill_names", None) or [])
    coach_state = deepcopy(getattr(state, "coach_state", None) or {})
    coach_state_changed = bool(getattr(state, "coach_state_changed", False))
    coach_turn_processed = bool(getattr(state, "coach_turn_processed", False))
    coach_edit_handoff = deepcopy(getattr(state, "coach_edit_handoff", None))
    
    # 处理确认回复
    if '[CONFIRM_REPLY:' in user_content:
        LOGGER.debug("检测到确认回复")
        updated_resume_data = None
        updated_layout_data = None
        import re
        match = re.search(r'\[CONFIRM_REPLY:([^:]+):([^:\]]+)(?::([^\]]*))?\]', user_content)
        
        if match:
            user_confirm_id = match.group(1)
            value = match.group(2)
            selected_change_ids = [item for item in (match.group(3) or "").split(",") if item]

            # 检查是否有待确认的请求
            pending_conf = state.pending_confirmation
            if pending_conf and pending_conf.get('confirm_id') == user_confirm_id:
                tool_name = state.pending_confirmation.get('tool_name')
                tool_args = state.pending_confirmation.get('tool_args', {})
                confirm_content = state.pending_confirmation.get('content', '确认此修改')

                pending_task_id = tool_args.get("task_id")
                if pending_task_id and pending_task_id != state.task_id:
                    result = "无效的确认请求：待确认修改不属于当前简历任务"
                    saved_resume = False
                elif value in {'confirm', 'confirm_all', 'confirm_selected'}:
                    # 执行保存
                    LOGGER.debug("确认请求匹配，执行保存")
                    try:
                        # 直接从 pending_confirmation 获取修改后的数据并保存
                        tool_args = state.pending_confirmation.get("tool_args", {})
                        content = tool_args.get("content", "")

                        if not content:
                            result = "保存失败：没有找到修改后的简历数据"
                            saved_resume = False
                        else:
                            # 解析候选完整简历；这与原版流程一致。选择性接受只在解析后
                            # 通过服务端生成的差异清单确定性应用，不再调用模型。
                            try:
                                candidate_resume_data = json.loads(content)
                            except json.JSONDecodeError as e:
                                LOGGER.debug("确认候选 JSON 首次解析失败，尝试兼容修复")
                                fixed_content = fix_unquoted_json_strings(content)
                                candidate_resume_data = json.loads(fixed_content)

                            candidate_resume_data = normalize_and_validate_resume(candidate_resume_data)
                            candidate_layout_data = normalize_layout_config(
                                json.loads(tool_args.get("layout_content", "{}"))
                                if tool_args.get("layout_content") else state.layout_data
                            )
                            changes = state.pending_confirmation.get("changes") or []
                            base_hash = state.pending_confirmation.get("base_hash")
                            before_layout_data = normalize_layout_config(state.layout_data)
                            base_layout = normalize_layout_config(
                                state.pending_confirmation.get("base_layout")
                            )
                            # Pending confirmations created before a schema
                            # migration may contain a digest of the raw resume,
                            # while newer confirmations use normalized data.
                            # Accept either representation; any other digest
                            # still indicates a real concurrent edit.
                            raw_resume_data = state.resume_data or {}
                            live_digests = {
                                resume_digest(raw_resume_data),
                                resume_digest(normalize_resume_data(raw_resume_data)),
                            }
                            if base_hash and base_hash not in live_digests:
                                result = "保存失败：简历已发生其他修改，请重新生成修改建议"
                                saved_resume = False
                            elif (
                                any(item.get("kind") == "layout" for item in changes)
                                and state.pending_confirmation.get("base_layout") is not None
                                and before_layout_data != base_layout
                            ):
                                result = "保存失败：简历布局已发生其他修改，请重新生成修改建议"
                                saved_resume = False
                            else:
                                all_change_ids = [item.get("id") for item in changes if item.get("id")]
                                if changes and not validate_resume_change_set(
                                    normalize_resume_data(state.resume_data or {}),
                                    candidate_resume_data,
                                    changes,
                                ):
                                    result = "保存失败：修改预览已失效，请重新生成修改建议"
                                    saved_resume = False
                                elif changes:
                                    ids_to_apply = (
                                        all_change_ids
                                        if value in {'confirm', 'confirm_all'}
                                        else [item for item in selected_change_ids if item in all_change_ids]
                                    )
                                    if not ids_to_apply:
                                        result = "保存失败：请至少选择一项修改"
                                        saved_resume = False
                                    else:
                                        resume_changes = [item for item in changes if item.get("kind") != "layout"]
                                        updated_resume_data = apply_resume_changes(
                                            state.resume_data or {}, resume_changes, ids_to_apply
                                        )
                                        updated_layout_data = apply_layout_change_groups(
                                            before_layout_data, candidate_layout_data, ids_to_apply
                                        )
                                else:
                                    # 兼容升级前已生成的待确认记录。
                                    ids_to_apply = []
                                    updated_resume_data = candidate_resume_data
                                    updated_layout_data = before_layout_data

                                if updated_resume_data is not None:
                                    from .tools import update_resume
                                    updated_resume_data = normalize_and_validate_resume(updated_resume_data)
                                    before_resume_data = normalize_and_validate_resume(state.resume_data or {})
                                    result = update_resume(
                                        updated_resume_data,
                                        user_id=state.user_id,
                                        task_id=state.task_id,
                                    )
                                    saved_resume = not (
                                        result.startswith("保存失败") or result.startswith("错误")
                                    )
                                    if saved_resume:
                                        try:
                                            if any(str(change_id).startswith("layout-") for change_id in ids_to_apply):
                                                from .database import SessionLocal, get_resume_task, save_task_layout_config
                                                layout_db = SessionLocal()
                                                try:
                                                    saved_layout = save_task_layout_config(
                                                        layout_db, state.user_id, state.task_id,
                                                        updated_layout_data or before_layout_data,
                                                    )
                                                finally:
                                                    layout_db.close()
                                                if saved_layout is None:
                                                    raise ValueError("当前简历任务不存在")
                                                updated_layout_data = saved_layout
                                            record_assistant_revision(
                                                state.user_id,
                                                state.task_id,
                                                before_resume_data,
                                                updated_resume_data,
                                                ids_to_apply,
                                                before_layout_data,
                                                updated_layout_data,
                                            )
                                        except Exception as revision_error:
                                            LOGGER.warning("修改已保存，但布局或撤回版本记录失败: %s", revision_error)
                                        if changes:
                                            selected_changes = [
                                                item for item in changes
                                                if item.get("id") in ids_to_apply
                                            ]
                                            summaries = []
                                            for item in selected_changes:
                                                if item.get("kind") == "layout":
                                                    detail = "；".join(
                                                        f"{row.get('before_display', '')} → {row.get('after_display', '')}"
                                                        for row in item.get("details", [])
                                                    )
                                                    summaries.append(f"{item.get('label', '布局')}：{detail}")
                                                else:
                                                    summaries.append(
                                                        f"{item.get('label', '简历字段')}："
                                                        f"{item.get('before_display', '')} → "
                                                        f"{item.get('after_display', '')}"
                                                    )
                                            result = f"已应用 {len(selected_changes)} 项修改"
                                            if summaries:
                                                result += "：\n- " + "\n- ".join(summaries)
                    except json.JSONDecodeError as e:
                        result = f"保存失败：JSON 解析错误 - {str(e)}"
                        saved_resume = False
                    except Exception as e:
                        result = f"保存失败：{str(e)}"
                        saved_resume = False
                elif value == 'cancel':
                    # 取消
                    LOGGER.debug("用户取消待确认修改")
                    result = "已取消保存"
                    saved_resume = False
                else:
                    result = "确认回复格式错误"
                    saved_resume = False
                
                # 清除 pending_confirmation
                pending_confirmation = None
                LOGGER.debug("确认请求已处理")
            else:
                if pending_conf:
                    # 清除不匹配的 pending_confirmation
                    pending_confirmation = None
                else:
                    pending_confirmation = None
                result = "无效的确认请求或确认已过期，请重新发送修改请求"
                saved_resume = False
        else:
            LOGGER.warning("确认回复格式错误")
            result = "确认回复格式错误"
            saved_resume = False
            pending_confirmation = None

        metadata_updates["edit_intent_state"] = {"status": "none"}
        
        # 创建 ToolMessage
        new_messages = [ToolMessage(content=result, tool_call_id="confirm", name="confirmation_handler")]

        elapsed_time = time.time() - start_time
        LOGGER.debug("确认工具节点结束，耗时=%.2fs", elapsed_time)

        # 保存成功时使用 updated_resume_data，否则使用原来的 state.resume_data
        final_resume_data = updated_resume_data if (saved_resume and updated_resume_data) else (state.resume_data or {})
        final_layout_data = updated_layout_data if (saved_resume and updated_layout_data) else normalize_layout_config(state.layout_data)

        return {
            "messages": list(state.messages) + new_messages,
            "resume_data": final_resume_data,
            "jd_data": state.jd_data or {},
            "layout_data": final_layout_data,
            "pending_confirmation": pending_confirmation,
            "just_saved": saved_resume,
            "user_id": state.user_id,
            "task_id": state.task_id,
            "context_metadata_updates": metadata_updates,
        }
    
    # 普通工具调用处理
    # 检查是否有工具调用
    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        LOGGER.debug("工具节点没有工具调用")
        # 没有工具调用时，返回原始消息（保持上下文）
        return {
            "messages": list(state.messages),
            "resume_data": state.resume_data or {},
            "jd_data": state.jd_data or {},
            "layout_data": normalize_layout_config(state.layout_data),
            "user_id": state.user_id,
            "task_id": state.task_id,
            "context_metadata_updates": metadata_updates,
        }

    # 执行工具调用
    new_messages = []
    assistant_reply = ""
    edit_preview_reply = ""
    updated_resume_data = None  # 用于保存从工具参数中提取的简历数据
    pending_confirmation = None  # 用于触发确认按钮
    proposal_error = None
    edit_tool_called = False
    edit_noop = False
    seen_tool_call_fingerprints: set[str] = set()
    visual_parts = list(getattr(state, "visual_snapshot_parts", None) or [])
    visual_calls = int(getattr(state, "visual_snapshot_calls", 0) or 0)
    visual_revision = str(getattr(state, "visual_snapshot_revision", "") or "")
    visual_error = str(getattr(state, "visual_snapshot_error", "") or "")
    requested_tool_names = {
        tool_call.name if hasattr(tool_call, "name") else tool_call.get("name")
        for tool_call in last_message.tool_calls
        if hasattr(tool_call, "name") or isinstance(tool_call, dict)
    }
    defer_edit_for_visual = (
        "resume_snapshot" in requested_tool_names
        and "resume_edit" in requested_tool_names
        and visual_calls == 0
    )

    for tool_call in last_message.tool_calls:
        # 兼容不同版本的 tool_call 格式
        if hasattr(tool_call, 'name'):
            tool_name = tool_call.name
        elif isinstance(tool_call, dict) and 'name' in tool_call:
            tool_name = tool_call['name']
        else:
            continue  # 无效的工具调用，跳过

        if hasattr(tool_call, 'args'):
            tool_args = tool_call.args
        elif isinstance(tool_call, dict) and 'args' in tool_call:
            tool_args = tool_call['args']
        else:
            tool_args = {}
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except (TypeError, json.JSONDecodeError):
                tool_args = {}
        if not isinstance(tool_args, dict):
            tool_args = {}

        try:
            call_fingerprint = json.dumps(
                {"name": tool_name, "args": tool_args},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            call_fingerprint = f"{tool_name}:{repr(tool_args)}"
        if call_fingerprint in seen_tool_call_fingerprints:
            LOGGER.debug("忽略本轮重复工具调用: %s", tool_name)
            result = "本轮已处理相同工具调用，已忽略重复请求。"
            tool_call_id = (
                tool_call.id
                if hasattr(tool_call, "id")
                else tool_call.get("id", f"call_{uuid.uuid4().hex[:8]}")
                if isinstance(tool_call, dict)
                else f"call_{uuid.uuid4().hex[:8]}"
            )
            new_messages.append(ToolMessage(
                content=result,
                tool_call_id=tool_call_id,
                name=tool_name,
            ))
            continue
        seen_tool_call_fingerprints.add(call_fingerprint)

        # Tool 的发现、schema 与执行入口均由 Skill Runtime 统一解析。
        tool_func = activate_agent_skill if tool_name == activate_agent_skill.name else None
        if tool_func is None:
            try:
                tool_func = skill_runtime.get_by_tool_name(tool_name).model_tool()
            except Exception:
                tool_func = None

        if not tool_func:
            result = f"错误: 工具 {tool_name} 不存在"
            LOGGER.warning("模型请求了不存在的工具: %s", tool_name)
        else:
            try:
                # 如果是保存简历工具
                if tool_name == activate_agent_skill.name:
                    requested_skill_name = str(tool_args.get("name") or "").strip()
                    package = skill_runtime.get(requested_skill_name)
                    if package.name not in active_skill_names:
                        active_skill_names.append(package.name)
                    result = activate_agent_skill.invoke({"name": package.name})
                elif tool_name == COACH_TOOL_NAME:
                    coach_result = await skill_runtime.invoke(
                        COACH_SKILL_NAME,
                        tool_args,
                        {
                            "resume_data": normalize_resume_data(state.resume_data or {}),
                            "base_revision": resume_digest(normalize_resume_data(state.resume_data or {})),
                            "latest_user_message": latest_human_text(state),
                            "request_id": state.request_id or str(uuid.uuid4()),
                            "context_type": getattr(state, "context_type", "main") or "main",
                            "explicit_command": getattr(state, "assistant_command", "") == "coaching",
                            "coach_state": coach_state,
                        },
                    )
                    harness_metrics.increment("resume_coach_turns_total")
                    coach_state = coach_result.coach_state.model_dump()
                    coach_state_changed = True
                    coach_turn_processed = True
                    coach_edit_handoff = (
                        coach_result.edit_handoff.model_dump()
                        if coach_result.edit_handoff else None
                    )
                    if coach_result.active:
                        if COACH_SKILL_NAME not in active_skill_names:
                            active_skill_names.append(COACH_SKILL_NAME)
                    else:
                        active_skill_names = [
                            name for name in active_skill_names if name != COACH_SKILL_NAME
                        ]
                    if coach_edit_handoff and EDIT_SKILL_NAME not in active_skill_names:
                        active_skill_names.append(EDIT_SKILL_NAME)
                    result = coach_result.model_dump_json()
                # 如果是 Skill 激活请求
                elif tool_name == 'save_resume_tool':
                    content = tool_args.get('content', '')
                    try:
                        updated_resume_data = json.loads(content)
                        updated_resume_data = normalize_and_validate_resume(updated_resume_data)
                        tool_args['content'] = json.dumps(updated_resume_data, ensure_ascii=False)
                    except Exception as exc:
                        updated_resume_data = None
                        result = f"保存失败：简历数据结构不合法 - {str(exc)}"
                    else:
                        pending_confirmation = make_pending_confirmation(state, updated_resume_data)
                        confirm_id = pending_confirmation["confirm_id"]
                        tool_args = pending_confirmation["tool_args"]

                        # 返回确认标记
                        marker = {
                            "type": "save_resume",
                            "confirm_id": confirm_id,
                            "content": "是否确认修改简历？",
                            "options": pending_confirmation["options"]
                        }
                        result = f"[CONFIRM_MARKER:{json.dumps(marker)}]"
                        LOGGER.debug("修改工具已生成确认标记")
                elif tool_name == "resume_snapshot":
                    if visual_calls >= 1 or visual_parts:
                        result = "本轮已经提供过当前简历快照，请直接使用现有视觉证据继续判断。"
                    else:
                        visual_calls = 1
                        try:
                            snapshot = await _render_current_visual_snapshot(state)
                        except Exception as exc:
                            visual_error = str(exc)
                            metadata_updates["last_visual_error"] = type(exc).__name__
                            harness_metrics.increment("resume_visual_render_failures_total")
                            result = (
                                "当前简历快照生成失败，不能基于页面视觉作出判断："
                                f"{type(exc).__name__}。请仅回答不依赖视觉证据的部分。"
                            )
                        else:
                            visual_parts = snapshot.parts
                            visual_revision = snapshot.revision
                            visual_error = ""
                            metadata_updates.update(_visual_metadata(snapshot))
                            page_summary = "、".join(
                                f"第{index}页 {size[0]}×{size[1]}"
                                for index, size in enumerate(snapshot.page_sizes, start=1)
                            )
                            result = (
                                "已生成并附加当前简历 PDF 页面快照："
                                f"{page_summary}；版本 {snapshot.revision[:12]}。"
                            )
                elif tool_name == 'resume_edit':
                    edit_tool_called = True
                    if coach_state.get("active") and not coach_edit_handoff:
                        raise ValueError(
                            "深度打磨仍处于分析阶段；必须先由用户明确同意生成预览，"
                            "再通过 resume_coach 取得编辑授权"
                        )
                    if coach_edit_handoff:
                        tool_args = {
                            **tool_args,
                            "resume_operations": deepcopy(
                                coach_edit_handoff.get("resume_operations") or []
                            ),
                            "layout_operations": [],
                        }
                    if defer_edit_for_visual:
                        result = (
                            "本轮同时请求了视觉检查和修改。系统已先获取视觉证据，"
                            "尚未生成修改预览；请查看快照后重新调用 resume_edit，"
                            "并只提交最终确认的结构化操作。"
                        )
                        continue_edit = False
                    else:
                        continue_edit = True
                    if not continue_edit:
                        pass
                    else:
                        try:
                            resume_operations = _coerce_resume_edit_operations(
                                tool_args.get("resume_operations"),
                                field_name="resume_operations",
                            )
                            layout_operations = _coerce_resume_edit_operations(
                                tool_args.get("layout_operations"),
                                field_name="layout_operations",
                            )
                            preview = await _generate_resume_edit_preview(
                                state,
                                resume_operations,
                                layout_operations,
                            )
                        except Exception as exc:
                            LOGGER.warning("简历修改预览生成失败: %s", exc)
                            proposal_error = "本次修改无法安全生成确认预览，系统未对简历做任何更改。"
                            result = proposal_error
                        else:
                            pending_confirmation = preview.get("pending_confirmation")
                            if pending_confirmation and coach_edit_handoff:
                                pending_confirmation["coach_offer_id"] = coach_edit_handoff.get("offer_id")
                            edit_noop = bool(preview.get("already_satisfied"))
                            assistant_reply = str(tool_args.get("answer_text", "") or "").strip()
                            edit_preview_reply = str(
                                preview.get("message", "已生成修改预览。") or ""
                            ).strip()
                            result = edit_preview_reply
                else:
                    # 其他工具直接执行
                    result = tool_func.invoke(tool_args)

            except Exception as e:
                if tool_name == COACH_TOOL_NAME:
                    harness_metrics.increment("resume_coach_errors_total")
                result = f"错误: {str(e)}"

        # 创建 ToolMessage
        if hasattr(tool_call, 'id'):
            tool_call_id = tool_call.id
        elif isinstance(tool_call, dict) and 'id' in tool_call:
            tool_call_id = tool_call['id']
        else:
            tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
        tool_message = ToolMessage(
            content=result,
            tool_call_id=tool_call_id,
            name=tool_name
        )
        new_messages.append(tool_message)

    # Tool-only model responses commonly have empty assistant content.  After
    # the candidate really exists, expose any pre-preview answer followed by
    # the system-generated execution status before the confirmation card.
    if (pending_confirmation or edit_noop) and edit_preview_reply:
        reply_parts = [value for value in (assistant_reply, edit_preview_reply) if value]
        new_messages.append(AIMessage(content="\n\n".join(reply_parts)))

    elapsed_time = time.time() - start_time
    LOGGER.debug("工具节点结束，耗时=%.2fs，结果数=%s", elapsed_time, len(new_messages))

    # 返回所有消息
    all_messages = list(state.messages) + new_messages
    
    # 检查是否执行了 save_resume_tool（实际保存）
    saved_resume = any(
        (isinstance(m, ToolMessage) and '简历已成功保存' in m.content)
        for m in new_messages
    )
    if pending_confirmation:
        metadata_updates["edit_intent_state"] = {"status": "awaiting_confirmation"}
    elif edit_tool_called:
        metadata_updates["edit_intent_state"] = {"status": "none"}
    
    return {
        "messages": all_messages,
        "resume_data": updated_resume_data if updated_resume_data else (state.resume_data or {}),
        "jd_data": state.jd_data or {},
        "layout_data": normalize_layout_config(state.layout_data),
        "pending_confirmation": pending_confirmation,
        "proposal_error": proposal_error,
        "edit_noop": edit_noop,
        "just_saved": saved_resume,
        "user_id": state.user_id,
        "task_id": state.task_id,
        "memory_summary": getattr(state, "memory_summary", "") or "",
        "memory_version": getattr(state, "memory_version", 0) or 0,
        "visual_snapshot_parts": visual_parts,
        "visual_snapshot_calls": visual_calls,
        "visual_snapshot_revision": visual_revision,
        "visual_snapshot_error": visual_error,
        "context_metadata_updates": metadata_updates,
        "active_skill_names": active_skill_names,
        "coach_state": coach_state,
        "coach_state_version": getattr(state, "coach_state_version", 0) or 0,
        "coach_state_changed": coach_state_changed,
        "coach_turn_processed": coach_turn_processed,
        "coach_required": bool(coach_state.get("active")),
        "coach_edit_handoff": coach_edit_handoff,
        "assistant_command": getattr(state, "assistant_command", "") or "",
    }



# =============================================================================
# Routing Functions
# =============================================================================

def route_after_conversation(state: AgentState) -> str:
    """
    conversation_llm 后的路由决策

    Returns:
        'tool_node': 需要执行工具
        END: 对话结束
    """
    if not state.messages:
        LOGGER.debug("对话节点无消息，路由结束")
        return END

    last_message = state.messages[-1]
    has_tool_calls = hasattr(last_message, 'tool_calls') and last_message.tool_calls
    # 检查是否有工具调用
    if has_tool_calls:
        LOGGER.debug("对话节点路由到工具节点")
        return "tool_node"

    LOGGER.debug("对话节点路由结束")
    return END  # 无工具调用，结束对话


# =============================================================================
# Graph Construction
# =============================================================================

graph_builder = StateGraph(AgentState)

# 添加节点
graph_builder.add_node("conversation_llm", conversation_node)
graph_builder.add_node("tool_node", tool_node)
graph_builder.add_node("direct_edit", direct_edit_node)
graph_builder.add_node("proposal_generator", proposal_generator_node)

# conversation_llm → tool_node / END
graph_builder.add_conditional_edges(
    "conversation_llm",
    route_after_conversation,
    {
        "tool_node": "tool_node",
        END: END
    }
)

graph_builder.add_edge("direct_edit", END)
graph_builder.add_edge("proposal_generator", END)


# =============================================================================
# 入口路由函数
# =============================================================================

def entry_router(state: AgentState) -> str:
    """
    START 节点的路由决策

    Returns:
        'conversation_llm': 普通对话或由主模型解析后调用修改技能
        'tool_node': 确认按钮点击
        'direct_edit': 可确定解析的字段赋值
    """
    if not state.messages:
        return "conversation_llm"

    # 检查最后一条消息是否是确认按钮点击
    last_message = state.messages[-1]
    user_content = getattr(last_message, 'content', '') or ''

    if '[CONFIRM_REPLY:' in user_content:
        return "tool_node"

    # An explicit deep-polish Command and every active coach session stay on
    # the model/Skill path. Direct-edit heuristics cannot bypass evidence
    # collection or its preview-authorization boundary.
    if getattr(state, "coach_required", False) or bool(
        (getattr(state, "coach_state", None) or {}).get("active")
    ):
        return "conversation_llm"

    user_request = latest_human_text(state)
    if is_mission_resume_edit_request(
        user_request,
        getattr(state, "context_type", "main") or "main",
    ):
        return "conversation_llm"
    if is_font_size_chat_change_request(user_request):
        return "direct_edit"
    if is_inline_format_request(user_request):
        return "direct_edit"
    try:
        if classify_local_edit_request(state) in {"resolved", "resolved_noop"}:
            return "direct_edit"
    except Exception as exc:
        LOGGER.debug("本地解析不可用，转入结构化生成: %s", exc)

    return "conversation_llm"


# 设置入口点的条件路由
graph_builder.set_conditional_entry_point(entry_router)

# tool_node → conversation_llm / END
# 根据状态决定下一个节点
def tool_node_router(state: AgentState) -> str:
    # 如果有待确认状态，返回 END（等待前端确认）
    if getattr(state, 'pending_confirmation', None):
        return END

    if getattr(state, "proposal_error", None):
        return END

    if getattr(state, "edit_noop", False):
        return END

    # 所有确认结果都是确定性操作，不再调用 LLM。否则模型可能错误总结
    # 选择性接受的结果，或再次把历史修改请求路由到修改生成节点。
    if state.messages:
        last_message = state.messages[-1]
        if (
            isinstance(last_message, ToolMessage)
            and getattr(last_message, "name", "") == "confirmation_handler"
        ):
            return END

    # 默认返回 conversation_llm 生成结束语
    return "conversation_llm"

graph_builder.add_conditional_edges(
    "tool_node",
    tool_node_router,
    {
        "conversation_llm": "conversation_llm",
        END: END
    }
)

# 编译图（不使用 checkpointer，状态由数据库管理）
graph = graph_builder.compile()
LOGGER.debug("Agent 图编译完成")
# =============================================================================
# 测试函数
# =============================================================================

async def run_agent():
    """命令行测试入口"""
    print("简历助手已启动，输入'退出'结束对话")
    print("=" * 50)

    thread_id = "cli_test"

    while True:
        user_input = input("\n你：")
        if user_input.lower() in ["退出", "quit", "exit"]:
            print("再见！")
            break

        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "resume_data": None
        }

        outputs = []
        error_message = None
        try:
            async for chunk in graph.astream(initial_state, config={"configurable": {"thread_id": thread_id}}):
                outputs.append(chunk)
        except TimeoutError as e:
            error_message = f"抱歉，处理时间过长，请稍后重试。"
        except RuntimeError as e:
            error_message = f"抱歉，我遇到了问题，请稍后重试。"

        # 如果有错误，直接显示错误消息
        if error_message:
            print("\n[助手回复]")
            print("-" * 40)
            print(error_message)
            print("-" * 40)
            continue

        # 提取最后一条 AIMessage
        final_response = None
        for output in outputs:
            for node_name, node_output in output.items():
                if isinstance(node_output, dict) and "messages" in node_output:
                    messages = node_output["messages"]
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage) and msg.content:
                            final_response = msg.content
                            break

        print("\n[助手回复]")
        print("-" * 40)
        print(final_response or "未找到回复")
        print("-" * 40)


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_agent())
