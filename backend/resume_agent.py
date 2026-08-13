"""
简历助手 AI 代理模块
使用 LangGraph 构建的智能对话系统，帮助用户完善简历。

核心设计原则：
1. 状态驱动：单次执行状态通过 AgentState 传递，跨请求状态由应用数据库持久化
2. 工具调用：只在必要时调用工具（save_resume_tool）
3. 消息过滤：只传递 HumanMessage/AIMessage/SystemMessage 给 LLM，跳过 ToolMessage
4. 无硬编码回复：所有 AI 回复由 LLM 生成，不使用硬编码内容
5. 单LLM节点架构：conversation_llm 负责对话和工具调用决策
"""

import os
import json
import re
import uuid
import asyncio
import httpx
import time
from copy import deepcopy
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from dataclasses import field
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from dataclasses import dataclass
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

from .resume_data import normalize_resume_data
from .inline_formatting import InlineFormatError, format_resume_text, plain_inline_text
from .resume_changes import apply_resume_changes, build_resume_changes, resume_digest
from .layout_config import (
    apply_density,
    apply_layout_template,
    apply_layout_change_groups,
    build_layout_changes,
    default_layout_config,
    normalize_layout_config,
    reset_layout_section,
)
from .llm_providers import active_profile, role_temperature
from .harness.context import build_conversation_context
from .harness.interview import (
    INTERVIEW_MODES,
    apply_suggestion_candidate,
    normalize_interview_memory,
    run_interview_turn,
)
from .harness.observability import harness_metrics


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


def sanitize_for_log(content):
    """清理内容中的 base64 图片数据，避免日志污染"""
    if isinstance(content, str):
        if len(content) > 200:
            return content[:200] + "..."
        return content
    elif isinstance(content, list):
        sanitized_items = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "image_url":
                    sanitized_items.append("[图片已过滤]")
                elif item.get("type") == "text":
                    text = item.get("text", "")
                    sanitized_items.append(text[:100] + "..." if len(text) > 100 else text)
                else:
                    sanitized_items.append(str(item)[:50])
            else:
                sanitized_items.append(str(item)[:50])
        return "\n".join(sanitized_items)
    return str(content)[:200]


def estimate_tokens(text):
    """粗略估算 tokens 数量（中英文混合场景）"""
    if not text:
        return 0
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
    title: str = Field(..., description="论文标题")
    details: List[str] = Field(default_factory=list, description="论文详细内容")


class Education(BaseModel):
    """教育背景"""
    school_name: str = Field(..., description="学校名称")
    major: str = Field(..., description="专业")
    degree: str = Field(..., description="学历")
    date_range: List[str] = Field(..., description="就读时间")
    school_tags: List[str] = Field(default_factory=list, description="学校性质标签")
    gpa: str = Field(default="", description="平均绩点，例如 3.72")
    gpa_scale: str = Field(default="", description="绩点满分，例如 4.0")
    ranking: str = Field(default="", description="专业或年级排名，例如 前10%")
    average_score: str = Field(default="", description="加权平均分，例如 88/100")
    theses: List[Thesis] = Field(default_factory=list, description="论文列表")


class ProjectContentBlock(BaseModel):
    """经历正文的语义块，避免标题、正文和编号被统一渲染成圆点列表。"""
    type: Literal["paragraph", "numbered_list", "bullet_list"] = Field(
        default="paragraph", description="段落、编号列表或普通分点列表"
    )
    semantic_role: Optional[Literal["introduction", "responsibilities", "generic"]] = Field(
        default=None, description="稳定语义角色；旧数据缺省时由类型和标签兼容推断"
    )
    label: str = Field(default="", description="例如项目简介、项目职责")
    label_bold: bool = Field(default=True, description="语义标签是否加粗")
    text: str = Field(default="", description="paragraph 类型的正文")
    items: List[str] = Field(default_factory=list, description="列表类型的逐条内容，不包含序号")


class WorkExperience(BaseModel):
    """工作经历"""
    company_name: str = Field(..., description="公司名称")
    job_title: str = Field(..., description="职位名称")
    date_range: List[str] = Field(..., description="就职时间")
    job_type: str = Field(..., description="工作类型（实习/全职）")
    content_blocks: List[ProjectContentBlock] = Field(default_factory=list, description="项目简介、职责等语义内容块")
    details: List[str] = Field(default_factory=list, description="工作详细内容")


class ProjectExperience(BaseModel):
    """项目经历"""
    project_name: str = Field(..., description="项目名称")
    role: str = Field(default="", description="项目角色；原文未提供时必须留空")
    date_range: List[str] = Field(default_factory=list, description="项目时间")
    content_blocks: List[ProjectContentBlock] = Field(
        default_factory=list, description="优先使用的项目简介、项目职责等语义内容块"
    )
    details: List[str] = Field(default_factory=list, description="旧数据兼容字段；新解析优先写入 content_blocks")


class Others(BaseModel):
    """其他信息"""
    skills: List[str] = Field(default_factory=list, description="原简历专业技能/技能特长/技术栈栏目中的全部条目，包括该栏目内出现的语言和证书")
    certificates: List[str] = Field(default_factory=list, description="仅提取原简历独立证书/资格栏目中的条目")
    languages: List[str] = Field(default_factory=list, description="仅提取原简历独立语言/外语能力栏目中的条目")


class CustomSection(BaseModel):
    """无法安全映射到固定栏目、但必须保留的原简历栏目。"""
    title: str = Field(default="", description="原栏目标题")
    items: List[str] = Field(default_factory=list, description="按原阅读顺序保留的内容")


class Resume(BaseModel):
    """完整简历数据结构"""
    basics: BasicInfo = Field(..., description="基本信息")
    education: List[Education] = Field(default_factory=list, description="教育背景")
    research_interests: List[str] = Field(default_factory=list, description="研究方向或研究兴趣")
    honors: List[str] = Field(default_factory=list, description="荣誉、奖项、奖学金")
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

httpx_client = httpx.Client(
    timeout=httpx.Timeout(90.0),
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
你是拥有十年经验的顶级大厂资深的、极度严格苛刻的面试官。你的唯一目标是确保用户递交的简历能从数万份申请中脱颖而出。 * **核心思维**：怀疑论者。默认用户提供的描述是“平庸的琐事”，除非其符合 STAR 原则并具备量化价值。 * **沟通风格**：专业、简洁、极度高效。不废话，不吹捧，不提供廉价的心理按摩。你通过精准的提问，把用户从“执行者”思维拽向“价值创造者”思维。

# 核心原则
- **深挖而非代笔**：不直接给模棱两可的建议，而是通过追问挖掘用户没写出来的细节。
- **结果导向**：坚信任何经历都必须有量化指标或具体成果。
- **学长风范**：专业、敏锐、直接，用自然流畅的对话消除用户的焦虑。
- **绝对真实**：绝对禁止为用户虚构没有的经历、技能等，一个词都不允许，为了提高质量而虚构最终会害了用户。（例如用户本来没有提到photoshop，就算JD里要求了，也不能帮用户编一个技能出来，应该引导用户去学习这个技能，而不是通过虚构来达到JD要求，这样对用户才是真正的负责）

# 简历全维度评判（需要以怀疑论者的角度去审视，分数不用输出给用户）

## 标准优化顺序，你必须严格按照以下顺序逐步优化简历，**每次只聚焦一个模块**，不要跳跃：
1. **目标岗位**：如果你没有任何关于用户目标岗位或意愿的信息，不要进行假设，优先引导用户**点击页面右上角的“目标岗位”按钮上传目标岗位JD（文本或图片）**，或者如果没有明确的目标岗位，至少引导用户输入一个明确的期望岗位名称（如"我想申请字节跳动的产品经理岗位"），以便后续优化有明确的方向。
2. **基础信息**：姓名、手机、邮箱、期望岗位 （重要，绝对不能缺漏！）
3. **教育经历**：学校、专业、学位、时间、亮点标签、GPA/绩点、排名、平均分
4. **工作经历**：公司、职位、时间、STAR 描述、量化结果
5. **项目经历**：项目名、角色、技术栈、STAR 描述、量化成果
6. **其他**：技能、证书、语言
7. **自我评价**：总结性描述

## 规则
- **禁止跳跃**：不能跳过当前模块去优化下一个模块
- **精准打击**：每次只问/优化一个点，不要长篇大论
- **当前模块不完善时**：不能进入下一模块

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

## 完善度状态处理
- 如果简历不完善（低于60分），优先引导用户补充缺失模块、改进负面特征，**不要结束对话**
- 每次对话后，判断当前分数，决定是否进入下一模块或继续当前模块
- 只有当简历达到"完善"标准后，才能引导用户聊面试话题或结束对话

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
5. **负面惩罚意识**：如果用户提供的内容存在"过程劳务化"、"话术空心化"、"缺乏决策痕迹"，应指出并引导改进，而非直接采用。

# 用户的简历数据：{{resume_data}}

# 目标岗位JD数据：{{jd_data}}

# 对话逻辑规则与输出风格
1. **单点质询原则**：每次对话只输出一个核心问题的提问或一个具体的修改点，严禁一次性抛出多个问题分散用户注意力。
2. **引导式提问**：若描述简略，严禁说“很棒”，应通过提问启发细节。例：“这个项目方向很有意思。你能细说下当时遇到最难的技术点是什么吗？或者你用什么指标衡量它的成功？”
3. **确认修改**：当你给出了完整的优化建议、可以达到修改标准时，调用 `save_resume_tool`。此时，你的回复内容应包含完整的修改建议（用自然语言描述），然后调用工具。

# 工具调用规则
- **save_resume_tool**：当你给出了完整的优化建议、可以达到修改标准时，需要输出完整的修改建议（不要只输出部分的改动点，而是要输出要修改的部分的前后对比），且调用此工具。你需要将完整的简历JSON作为参数传入。调用后，系统会自动在前端显示确认框，**用户点击确认后才会实际保存到简历库**。
- **输出措辞注意**：当你调用 `save_resume_tool` 时，你的回复内容应该说"上述修改方案已准备好，请在下方确认框中确认是否应用（确认框可能稍有延迟，请耐心等待，确认框出现前不要离开或刷新当前页面以免丢失聊天记录）"或"以上是我对你的简历的修改建议，请在下方确认框中确认是否修改到简历库？（确认框显示可能稍有延迟，请耐心等待）"之类的话术，**绝对不能说"已保存"、"已同步"、"已修改"、"已经更新到简历库"等**，因为此时还需要用户确认，简历还没有实际被修改。
- **内容一致性约束**：你调用 `save_resume_tool` 时传入的JSON参数内容，必须与你的文字回复中描述的修改内容保持一致。文字描述是修改建议的展示形式，JSON是修改建议的数据形式，两者描述的是同一份修改。如果发现不一致，以JSON中的内容为准修正你的文字回复。
- **教育成绩字段约束**：用户提到“GPA”“绩点”“平均绩点”时写入 `gpa`，满分写入 `gpa_scale`；“专业排名/年级排名”写入 `ranking`；“平均分/加权平均分”写入 `average_score`。这些内容绝对不能写入 `theses`。
- 当调用工具时，传入的JSON格式如下：
```json
{
  "basics": {
    "name": "姓名",
    "gender": "性别",
    "phone": "手机号",
    "email": "邮箱",
    "target_position": "期望岗位"
  },
  "education": [{
    "school_name": "学校",
    "major": "专业",
    "degree": "学位",
    "date_range": ["开始时间", "结束时间"],
    "school_tags": ["标签1", "标签2"],
    "gpa": "3.72",
    "gpa_scale": "4.0",
    "ranking": "前10%",
    "average_score": "88/100",
    "theses": []
  }],
  "work_experience": [{
    "company_name": "公司",
    "job_title": "职位",
    "date_range": ["开始时间", "结束时间"],
    "job_type": "实习/全职",
    "details": ["具体工作内容1", "具体工作内容2"]
  }],
  "project_experience": [{
    "project_name": "项目名称",
    "role": "角色",
    "date_range": ["开始时间", "结束时间"],
    "details": ["具体内容1", "具体内容2"]
  }],
  "others": {
    "skills": ["技能1", "技能2"],
    "certificates": ["证书1", "证书2"],
    "languages": ["语言"]
  },
  "self_evaluation": ["自我评价1", "自我评价2"]
}
```

# 重要规则
- **重要** 当 just_saved=True（简历刚保存）时，说明简历已经修改完成了，不要调用任何工具。
- **重要** 绝对禁止在聊天内容中输出 JSON 代码块。
- **重要** 严禁在聊天内容中输出JSON格式内容。
- **重要** 禁止构造虚假的修改建议，必须基于用户实际提供的内容，为了提高质量而虚构任何东西（哪怕是一个词）最终会害了用户。
- 绝对禁止说："已保存"、"已修改"、"正在为你更新"。
- 当输出文本时，绝对禁止提及 JSON、Key、Value 等技术术语。
- 年份信息： 当前现实世界的年份是 2026 年，需要谨记。

# 面试引导逻辑
当简历达到"完善"标准后，你可以：
1. 主动引导用户例如："简历已经比较完善了，要开始准备面试了吗？我们来聊聊常见的面试问题或模拟面试吧。"
2. 提供面试高频问题
3. 进行模拟面试

但注意：不要强制引导，如果用户还想继续优化简历，尊重用户意愿。
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


# Resume Full Extract Prompt - 用于完整提取简历图片为JSON（首次上传流程）
RESUME_FULL_EXTRACT_PROMPT = '''# Role
你是简历OCR提取专家，负责从图片中完整提取所有简历信息。

# 核心要求
**逐字提取，不要省略任何内容**。图片中的每一个字、每一行都要完整提取。

# 严格的输出格式
你必须严格按照以下JSON Schema输出（其中的数组代表可以有多个），直接输出JSON对象：

```json规范参考
{
  "photo": "",（留空）
  "basics": {
    "name": "姓名",
    "gender": "性别",
    "phone": "手机号",
    "email": "邮箱",
    "target_position": "期望岗位"
  },
  "education": [{
    "school_name": "学校",
    "major": "专业",
    "degree": "学位",
    "date_range": ["开始时间", "结束时间"],
    "school_tags": ["标签1", "标签2"],
    "gpa": "3.72",
    "gpa_scale": "4.0",
    "ranking": "前10%",
    "average_score": "88/100",
    "theses": []
  }],
  "work_experience": [{
    "company_name": "公司",
    "job_title": "职位",
    "date_range": ["开始时间", "结束时间"],
    "job_type": "实习/全职",
    "details": ["具体工作内容1", "具体工作内容2"]
  }],
  "project_experience": [{
    "project_name": "项目名称",
    "role": "角色",
    "date_range": ["开始时间", "结束时间"],
    "details": ["具体内容1", "具体内容2"]
  }],
  "others": {
    "skills": ["技能1", "技能2"],
    "certificates": ["证书1", "证书2"],
    "languages": ["语言"]
  },
  "self_evaluation": ["自我评价1", "自我评价2"]
}
```

# 严格规则
1. **只输出JSON**，不要有任何解释、前缀、后缀、markdown代码块标记
2. **必须包含所有字段**，即使值为空字符串、空数组或空对象
3. **content 必须是数组**，每一条内容都要独立成数组元素
4. 时间格式统一为 "YYYY.MM - YYYY.MM" 或 "至今"
5. 如果图片中没有某字段，设置为 "" 或 []，不要省略
6. 绝对不要输出 ```json 或 ``` 标记
7. 绝对不要输出其他任何文字
8. “GPA/绩点/平均绩点”写入 gpa，绩点满分写入 gpa_scale；排名写入 ranking；平均分或加权平均分写入 average_score，绝对不要把这些信息写入 theses

# 示例
输入：一张简历图片，包含姓名"张三"，手机"13800138000"，工作经历"2020.01 - 2022.12 在字节跳动担任产品经理"
输出：{"basics":{"name":"张三","gender":"","phone":"13800138000","email":"","target_position":""},"education":[],"work_experience":[{"company":"字节跳动","position":"产品经理","time":"2020.01 - 2022.12","type":"","content":[]}],"project_experience":[],"others":{"skills":[],"certificates":[],"languages":[]},"self_evaluation":[]}
'''


RESUME_IMAGE_TRANSCRIPTION_PROMPT = '''你是只负责忠实转写的简历 OCR 引擎。

请按图片的阅读顺序逐行转写全部可见文字，不要总结、改写、补全或猜测。
无法确认的字符用“〔无法辨认〕”标记；图片中不存在的信息绝对不要生成。
保留各段标题、项目符号、日期、数字、邮箱和电话号码。只输出转写文本。'''


def build_resume_extract_prompt() -> str:
    """Return the single canonical prompt used for PDF and image imports."""
    return (
        "你是忠实、无损的简历文档解析器。完整读取所有页面；双栏或多栏页面必须先判断栏目边界，"
        "再按人类自然阅读顺序读取，不能把左右栏交叉拼接。\n"
        "【忠实性】逐字保留姓名、联系方式、学校、公司、职位、项目名、日期、数字、技术名词和每条可见描述；"
        "禁止总结、润色、改写、补全、合并不同经历或猜测不可见内容。\n"
        "【字段映射】出生年月进入 basics.birth_date；其他未预设的个人字段进入 basics.additional_fields；"
        "研究方向进入 research_interests；奖学金、竞赛奖项和主要荣誉进入 honors；"
        "字段映射必须先遵循原简历的可见栏目边界，而不是仅凭内容语义重新分类：专业技能、技能特长、技术栈栏目下的全部内容"
        "都进入 others.skills，即使其中包含 CET-4/CET-6、英语、证书或认证；只有原文存在独立的证书/资格栏目时才写入"
        "others.certificates，只有原文存在独立的语言/外语能力栏目时才写入 others.languages。禁止把原简历一个栏目拆成多个新栏目，"
        "也不要跨数组重复同一内容。不能把专业技能放入 custom_sections，也不能把荣誉混入 certificates。\n"
        "【经历语义】工作和项目内容优先写入各自的 content_blocks：项目简介/项目背景使用 paragraph 且 semantic_role=introduction；"
        "项目职责/主要职责使用 numbered_list 且 semantic_role=responsibilities；普通无标签内容使用 bullet_list 且 semantic_role=generic。"
        "label 保留原文标题且 label_bold=true；语义标签为空表示保留内容但不显示，不能擅自补回默认标签；"
        "原文中的（1）（2）或 (1)(2) 等编号只作为 items 的边界，items 内不要重复序号。"
        "原文没有项目角色时 role 必须为空，禁止输出‘角色’、‘项目成员’等占位词。\n"
        "【经历粒度】没有语义标题的普通工作描述才逐条进入 details，禁止合成一个长字符串；"
        "论文标题与说明写入 theses；GPA、满分、排名和平均分分别进入对应字段。\n"
        "【兜底保留】任何不能可靠映射到固定字段的原栏目，都必须按原栏目标题和阅读顺序写入 custom_sections，"
        "绝对不能因为 Schema 没有同名字段而省略。不要重复写入已经映射的内容。\n"
        "【输出】文件中不存在的字段使用空字符串或空数组；basics.photo 留空。"
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
    将格式化后的简历数据保存到数据库

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
        print(f"[save_resume_tool] 首次JSON解析失败，尝试修复: {e}")
        fixed_content = fix_unquoted_json_strings(content)
        try:
            resume_data = json.loads(fixed_content)
            print(f"[save_resume_tool] 修复后解析成功")
        except json.JSONDecodeError as e2:
            print(f"[save_resume_tool] 修复后仍然失败: {e2}")
            return f"保存失败：JSON 解析错误 - {str(e)}"

    try:
        resume_data = normalize_and_validate_resume(resume_data)
    except Exception as exc:
        return f"保存失败：简历数据结构不合法 - {str(exc)}"

    # 保存到数据库
    try:
        print(f"[save_resume_tool] 开始保存简历，用户ID={user_id}")
        print(f"[save_resume_tool] resume_data keys: {list(resume_data.keys()) if isinstance(resume_data, dict) else 'not a dict'}")
        result = update_resume(resume_data, user_id=user_id, task_id=task_id)
        print(f"[save_resume_tool] 保存结果: {result}")
        return result
    except Exception as e:
        print(f"[save_resume_tool] 保存错误: {e}")
        return f"保存失败：{str(e)}"


# 工具列表 - conversation_llm 只能调用 save_resume_tool
conversation_tools = [save_resume_tool]


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
    memory_summary: str = ""  # 分层记忆摘要，仅作为不可执行的上下文数据
    memory_version: int = 0  # 乐观并发版本，由持久化层管理
    interview_memory: dict = None  # 带来源的已核实事实与最近建议
    workflow_state: dict = None  # Checkpointer 中的轻量控制状态
    workflow_updates: dict = None  # 本节点产生的控制状态投影
    interaction_mode: str = ""  # diagnosis/coaching/jd_review；空值沿用旧链路
    interaction_action: str = ""  # start/answer/pause/resume/end/apply
    request_id: str = ""


# =============================================================================
# DEBUG: 添加诊断日志
# =============================================================================

def debug_print_state(state: AgentState, location: str = ""):
    """打印当前状态用于调试"""
    import sys
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[DEBUG@{location}]", file=sys.stderr)
    print(f"  messages count: {len(state.messages)}", file=sys.stderr)
    print(f"  resume_data keys: {list((state.resume_data or {}).keys()) if state.resume_data else None}", file=sys.stderr)
    print(f"  jd_data loaded: {bool(state.jd_data)}", file=sys.stderr)
    print(f"  pending_confirmation: {bool(state.pending_confirmation)}", file=sys.stderr)
    
    # 打印最后几条消息
    if state.messages:
        print(f"  last 3 messages:", file=sys.stderr)
        for i, msg in enumerate(state.messages[-3:]):
            msg_type = type(msg).__name__
            content = getattr(msg, 'content', '') or ''
            content_str = sanitize_for_log(content)[:80]
            print(f"    [{len(state.messages)-3+i}] {msg_type}: {content_str}...", file=sys.stderr)
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                print(f"       tool_calls: {[tc.name if hasattr(tc, 'name') else tc.get('name') for tc in msg.tool_calls]}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

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
    r"(?:修改|更改|改为|改成|替换|更新|填写|写入|新增|添加|删除|移除|补充|优化|调整|设置|设为|变更)"
)
_COACHING_INTENT_RE = re.compile(
    r"(?:诊断|点评|评估|审阅|审查|分析|拷打|追问|模拟面试官|修改建议|优化建议|"
    r"不足之处|不足|短板|问题在哪里|匹配度|怎么改|如何改|怎样改|如何修改|"
    r"怎么优化|如何优化|怎样优化|怎么完善|如何完善|怎样完善)"
)
_DIRECT_APPLY_RE = re.compile(
    r"(?:直接|立即|马上)(?:帮我|替我|给我)?(?:修改|优化|改写|重写|应用)|"
    r"(?:修改|优化|改写|重写)后(?:直接)?(?:应用|保存|写入)|(?:应用|保存|写入)(?:这些|上述|该)"
)
_RESUME_DATA_FIELD_RE = re.compile(
    r"(?:姓名|性别|年龄|出生年月|生日|电话|手机|邮箱|所在地|目标岗位|求职岗位|GPA|绩点|满绩|"
    r"排名|平均分|学校|专业|学历|学位|教育经历|工作经历|实习经历|项目经历|项目|"
    r"公司|职位|研究方向|研究兴趣|荣誉|奖项|技能|证书|语言|自定义栏目|自我评价|简历内容)"
)
_STYLE_ONLY_RE = re.compile(
    r"(?:字体|字号|颜色|填充|背景|边距|行距|间距|模板|排版|页眉|页脚|标签样式)"
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


def is_resume_coaching_request(message: str) -> bool:
    """Return True for read-only review, coaching, and interview-style requests."""
    text = str(message or "").strip()
    if not text or "[CONFIRM_REPLY:" in text:
        return False
    return bool(_COACHING_INTENT_RE.search(text) and not _DIRECT_APPLY_RE.search(text))


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
    if is_resume_coaching_request(text):
        return False
    if not (_CHANGE_ACTION_RE.search(text) and _RESUME_DATA_FIELD_RE.search(text)):
        return False
    # A request that only concerns presentation must stay in the normal dialog
    # path. Mixed data + presentation requests may still produce a data preview.
    data_without_style = _STYLE_ONLY_RE.sub("", text)
    return bool(_RESUME_DATA_FIELD_RE.search(data_without_style))


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
    r"标签|黑底|描边|普通文字|隐藏|显示|顺序|放到|移到|标题|圆点|段落|模板|恢复默认|重置)"
)
_LAYOUT_SECTION_NAMES = {
    "教育经历": "education", "教育背景": "education",
    "专业技能": "skills", "技能": "skills",
    "研究方向": "research_interests", "主要荣誉": "honors", "荣誉": "honors",
    "工作经历": "work_experience", "实习经历": "internship_experience",
    "项目经历": "project_experience", "其他信息": "others",
    "技能证书": "others", "自我评价": "self_evaluation", "个人总结": "self_evaluation",
}


def is_explicit_layout_change_request(message: str) -> bool:
    text = str(message or "").strip()
    if not text or "[CONFIRM_REPLY:" in text:
        return False
    if is_resume_coaching_request(text):
        return False
    return bool(_LAYOUT_ACTION_RE.search(text))


def build_local_layout_candidate(state: AgentState) -> dict | None:
    """Map common natural-language layout requests to the bounded preset contract."""
    text = latest_human_text(state)
    if not is_explicit_layout_change_request(text):
        return None
    current = normalize_layout_config(state.layout_data)
    candidate = deepcopy(current)

    for template_label, template_id in (
        ("经典专业", "classic-professional"),
        ("简洁现代", "modern-clean"),
        ("紧凑技术", "compact-tech"),
    ):
        if re.search(rf"(?:使用|应用|切换到|改成|换成)?.{{0,4}}{template_label}(?:模板|排版|风格)?", text):
            candidate = apply_layout_template(candidate, template_id)
            break

    reset_match = re.search(r"(?:恢复|重置)(?:(教育经历|工作经历|实习经历|项目经历|其他信息|自我评价|基本信息))?(?:布局|排版|样式)?(?:为)?默认", text)
    if reset_match:
        name = reset_match.group(1)
        reset_map = {
            "基本信息": "basics", "教育经历": "education", "工作经历": "work_experience",
            "实习经历": "work_experience", "项目经历": "project_experience",
            "其他信息": "others", "自我评价": "self_evaluation",
        }
        candidate = reset_layout_section(candidate, reset_map.get(name, "all"))

    if re.search(r"(?:整体|全局|整份简历)?.{0,6}(?:更紧凑|紧凑一些|紧凑版)", text):
        candidate = apply_density(candidate, "compact")
    if re.search(r"(?:整体|全局|整份简历)?.{0,6}(?:更舒展|宽松一些|舒展版)", text):
        candidate = apply_density(candidate, "comfortable")
    if re.search(r"(?:标准密度|恢复标准间距)", text):
        candidate = apply_density(candidate, "standard")
    if re.search(r"(?:模块|章节)?标题.{0,8}(?:不要下划线|去掉下划线|纯文字)", text):
        candidate["global"]["titleStyle"] = "plain"
    if re.search(r"(?:模块|章节)?标题.{0,8}(?:加下划线|使用下划线)", text):
        candidate["global"]["titleStyle"] = "underline"

    if re.search(r"(?:姓名|基本信息|页眉).{0,8}左对齐|左对齐.{0,8}(?:姓名|基本信息|页眉)", text):
        candidate["basics"]["preset"] = "left-aligned"
    if re.search(r"(?:姓名|基本信息|页眉).{0,8}居中|居中.{0,8}(?:姓名|基本信息|页眉)", text):
        candidate["basics"]["preset"] = "centered"
    if re.search(r"(?:联系方式).{0,8}(?:分行|竖排|纵向)", text):
        candidate["basics"]["contactLayout"] = "stacked"
    if re.search(r"(?:联系方式).{0,8}(?:同一行|横排|行内)", text):
        candidate["basics"]["contactLayout"] = "inline"
    if re.search(r"(?:隐藏|不要|去掉).{0,5}(?:照片|头像)|(?:照片|头像).{0,5}(?:隐藏|不要|去掉)", text):
        candidate["basics"]["photoPosition"] = "hidden"
        if "photo" not in candidate["basics"]["hiddenFields"]:
            candidate["basics"]["hiddenFields"].append("photo")
    for label, field_name in (("性别", "gender"), ("电话", "phone"), ("手机号", "phone"), ("邮箱", "email"), ("目标岗位", "target_position")):
        if re.search(rf"(?:隐藏|不要|去掉).{{0,5}}{label}|{label}.{{0,5}}(?:隐藏|不要|去掉)", text):
            if field_name not in candidate["basics"]["hiddenFields"]:
                candidate["basics"]["hiddenFields"].append(field_name)

    if re.search(r"(?:学校|院校|211|985).{0,10}(?:不要黑底|普通文字|纯文字)", text):
        candidate["education"]["schoolTagStyle"] = "text"
    if re.search(r"(?:学校|院校|211|985).{0,10}(?:描边|边框)", text):
        candidate["education"]["schoolTagStyle"] = "outline"
    if re.search(r"(?:学校|院校|211|985).{0,10}(?:使用黑底|改成黑底|设为黑底|实心)", text):
        candidate["education"]["schoolTagStyle"] = "filled"
    if re.search(r"(?:隐藏|不要|去掉).{0,5}(?:学校标签|211|985)", text):
        candidate["education"]["schoolTagStyle"] = "hidden"
    for label, field_name in (("GPA", "gpa"), ("绩点", "gpa"), ("排名", "ranking"), ("平均分", "average_score")):
        if re.search(rf"(?:隐藏|不要|去掉).{{0,5}}{label}|{label}.{{0,5}}(?:隐藏|不要|去掉)", text, re.I):
            if field_name not in candidate["education"]["hiddenMetrics"]:
                candidate["education"]["hiddenMetrics"].append(field_name)
    if re.search(r"(?:GPA|绩点|专业|学历).{0,15}(?:学校|院校).{0,6}(?:右边|右侧)|(?:学校|院校).{0,15}(?:GPA|绩点|专业|学历).{0,6}(?:右边|右侧)", text, re.I):
        candidate["education"]["preset"] = "three-column"
        candidate["education"]["metricsPlacement"] = "info-column"
    elif re.search(r"教育经历.{0,8}紧凑|紧凑.{0,8}教育经历", text):
        candidate["education"]["preset"] = "compact"
    elif re.search(r"教育经历.{0,8}(?:经典|默认)", text):
        candidate["education"]["preset"] = "classic"

    if re.search(r"(?:工作|实习)经历.{0,8}紧凑|紧凑.{0,8}(?:工作|实习)经历", text):
        candidate["work_experience"]["preset"] = "compact"
    if re.search(r"项目经历.{0,8}紧凑|紧凑.{0,8}项目经历", text):
        candidate["project_experience"]["preset"] = "compact"
    if re.search(r"(?:工作|实习)经历.{0,10}(?:不要圆点|改成段落|段落形式)", text):
        candidate["work_experience"]["detailsStyle"] = "paragraph"
    if re.search(r"项目经历.{0,10}(?:不要圆点|改成段落|段落形式)", text):
        candidate["project_experience"]["detailsStyle"] = "paragraph"
    if re.search(r"(?:工作|实习)经历.{0,10}(?:圆点|列表)", text):
        candidate["work_experience"]["detailsStyle"] = "bullets"
    if re.search(r"(?:隐藏|不要|去掉).{0,5}(?:工作类型|实习类型|全职兼职)", text):
        candidate["work_experience"]["showJobType"] = False
    if re.search(r"项目经历.{0,10}(?:圆点|列表)", text):
        candidate["project_experience"]["detailsStyle"] = "bullets"
    if re.search(r"项目经历.{0,10}(?:隐藏|不要|去掉).{0,4}(?:角色|职责)", text):
        candidate["project_experience"]["showRole"] = False
    if re.search(r"项目经历.{0,10}(?:隐藏|不要|去掉).{0,4}(?:日期|时间)", text):
        candidate["project_experience"]["showDate"] = False
    if re.search(r"(?:工作|实习).{0,5}(?:拆开|分开|分别显示)", text):
        candidate["global"]["splitWorkExperience"] = True
    if re.search(r"(?:工作|实习).{0,5}(?:合并|放在一起)", text):
        candidate["global"]["splitWorkExperience"] = False

    if re.search(r"(?:技能|证书|语言|其他信息).{0,8}标签", text):
        candidate["others"]["preset"] = "tags"
    if re.search(r"(?:技能|证书|语言|其他信息).{0,8}(?:分行|纵向)", text):
        candidate["others"]["preset"] = "stacked"
    if re.search(r"(?:技能|证书|语言|其他信息).{0,8}(?:同一行|行内)", text):
        candidate["others"]["preset"] = "inline"
    if re.search(r"自我评价.{0,8}(?:圆点|列表)", text):
        candidate["self_evaluation"]["preset"] = "bullets"
    if re.search(r"自我评价.{0,8}(?:紧凑|一段)", text):
        candidate["self_evaluation"]["preset"] = "compact"
    if re.search(r"自我评价.{0,8}(?:分段|段落)", text):
        candidate["self_evaluation"]["preset"] = "paragraphs"

    for label, section_id in _LAYOUT_SECTION_NAMES.items():
        if re.search(rf"(?:隐藏|不要|去掉).{{0,5}}{re.escape(label)}|{re.escape(label)}.{{0,5}}(?:隐藏|不要|去掉)", text):
            if section_id not in candidate["global"]["hiddenSections"]:
                candidate["global"]["hiddenSections"].append(section_id)
        if re.search(rf"(?:显示|恢复显示).{{0,5}}{re.escape(label)}|{re.escape(label)}.{{0,5}}(?:显示|恢复显示)", text):
            candidate["global"]["hiddenSections"] = [value for value in candidate["global"]["hiddenSections"] if value != section_id]

    section_pattern = r"教育经历|专业技能|技能|研究方向|主要荣誉|荣誉|工作经历|实习经历|项目经历|其他信息|自我评价"
    order_match = re.search(rf"({section_pattern}).{{0,8}}(?:放到|移到)({section_pattern})(前面|后面)", text)
    if order_match:
        source = _LAYOUT_SECTION_NAMES[order_match.group(1)]
        target = _LAYOUT_SECTION_NAMES[order_match.group(2)]
        order = [value for value in candidate["global"]["sectionOrder"] if value != source]
        target_index = order.index(target) if target in order else len(order)
        order.insert(target_index + (1 if order_match.group(3) == "后面" else 0), source)
        candidate["global"]["sectionOrder"] = order

    title_match = re.search(r"(教育经历|工作经历|实习经历|项目经历|其他信息|自我评价)(?:的)?标题(?:改为|改成|叫做)\s*([^，。；;\n]+)", text)
    if title_match:
        section_id = _LAYOUT_SECTION_NAMES[title_match.group(1)]
        candidate["global"].setdefault("titleOverrides", {}).setdefault(section_id, {})["zh"] = title_match.group(2).strip()

    candidate = normalize_layout_config(candidate)
    return candidate if candidate != current else None


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


def parse_resume_candidate(content) -> dict:
    """Extract and validate a full resume JSON object from a plain LLM reply."""
    text = _plain_response_text(content).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型没有返回完整的简历 JSON")
    raw_json = text[start:end + 1]
    try:
        candidate = json.loads(raw_json)
    except json.JSONDecodeError:
        candidate = json.loads(fix_unquoted_json_strings(raw_json))
    return normalize_and_validate_resume(candidate)


def parse_edit_candidate(content, current_resume: dict, current_layout: dict) -> tuple[dict, dict]:
    """Parse a combined resume/layout proposal while preserving omitted domains."""
    text = _plain_response_text(content).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型没有返回完整的修改 JSON")
    raw = text[start:end + 1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = json.loads(fix_unquoted_json_strings(raw))
    if "resume_data" not in payload and "layout_config" not in payload:
        return normalize_and_validate_resume(payload), normalize_layout_config(current_layout)
    return (
        normalize_and_validate_resume(payload.get("resume_data", current_resume)),
        normalize_layout_config(payload.get("layout_config", current_layout)),
    )


_COMPLEX_EDIT_FIELD_RE = re.compile(
    r"(?:工作经历|实习经历|项目经历|项目|研究方向|研究兴趣|荣誉|技能|证书|语言|自定义栏目|自我评价|论文|课程|奖项)"
)
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


def _clean_local_value(value: str) -> str:
    return str(value or "").strip().strip('"\'“”‘’ ')


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


def build_local_edit_candidate(state: AgentState) -> dict | None:
    """Return a candidate only when every requested edit is locally unambiguous."""
    text = latest_human_text(state)
    if not is_explicit_resume_change_request(text) or _COMPLEX_EDIT_FIELD_RE.search(text):
        return None

    current = normalize_resume_data(state.resume_data or {})
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
        source_school = _clean_local_value(school_match.group(1))
        target_school = _clean_local_value(school_match.group(2))
        education = candidate.get("education") or []
        source_matches = [
            index for index, item in enumerate(education)
            if _clean_local_value(item.get("school_name", "")) == source_school
        ]
        target_matches = [
            index for index, item in enumerate(education)
            if _clean_local_value(item.get("school_name", "")) == target_school
        ]
        if len(source_matches) == 1:
            education[source_matches[0]]["school_name"] = target_school
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
        value = _clean_local_value(match.group(1))
        if not value or (field_name == "gender" and value not in {"男", "女", "其他"}):
            return None
        candidate.setdefault("basics", {})[field_name] = value
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


def _preview_summary(changes: list[dict]) -> str:
    has_layout_change = any(change.get("kind") == "layout" for change in changes)
    lines = [
        "已根据你的要求匹配排版预设并生成临时预览："
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
    lines.extend(["", "右侧已显示临时预览；接受前不会保存。请在下方选择全部接受、仅应用选中项或全部拒绝。"])
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
    if is_font_size_chat_change_request(latest_human_text(state)):
        return {
            "messages": list(state.messages) + [AIMessage(content=(
                "字号不会通过对话命令直接修改。请打开简历预览上方的“排版”，进入“设置各部分字号”，"
                "按半磅选择姓名、模块标题、条目标题、元信息、正文和标签字号；弹窗会先实时预览，点击“应用”后才保存。"
            ))],
            "resume_data": current,
            "jd_data": state.jd_data or {},
            "layout_data": current_layout,
            "pending_confirmation": None,
            "proposal_error": None,
            "just_saved": False,
            "user_id": state.user_id,
            "task_id": state.task_id,
        }
    inline_request = is_inline_format_request(latest_human_text(state))
    inline_quote = ""
    inline_bold = True
    if inline_request:
        try:
            resume_candidate, inline_quote, inline_bold = build_inline_format_candidate(state)
        except InlineFormatError as exc:
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
            }
    else:
        resume_candidate = build_local_edit_candidate(state)
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
    print(f"[direct_edit] 本地生成完成, changes={len(changes)}")
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
    }


async def proposal_generator_node(state: AgentState) -> dict:
    """Generate one structured candidate for a complex explicit edit request."""
    start_time = time.time()
    request_text = latest_human_text(state)
    current = normalize_resume_data(state.resume_data or {})
    current_layout = normalize_layout_config(state.layout_data)
    prompt = f"""你是简历内容与排版配置生成器。请根据用户的明确要求输出一个 JSON 对象，包含 resume_data 和 layout_config。

严格规则：
1. 只输出一个完整 JSON 对象，不要输出解释、Markdown 或代码块；格式必须是 {{"resume_data": 完整简历, "layout_config": 完整布局配置}}。
2. 未被用户要求修改的内容必须原样保留，不得编造经历或事实。
3. GPA 数值写入 gpa，满分写入 gpa_scale，排名写入 ranking，绝对不能写入 theses。
4. 如果用户同时提出多项修改，必须一次性体现在同一份完整简历中。
5. 排版只能修改给定 layout_config 已存在的键和值；禁止输出 CSS、HTML、坐标或新增字段。
6. 可选值：density=compact/standard/comfortable；titleStyle=underline/plain；basics.preset=centered/left-aligned；contactLayout=inline/stacked；education.preset=classic/compact/three-column；schoolTagStyle=filled/outline/text/hidden；metricsPlacement=below/with-degree/info-column；work/project preset=classic/compact；detailsStyle=bullets/paragraph；datePosition=right/inline；others.preset=inline/tags/stacked；self_evaluation.preset=paragraphs/bullets/compact。
7. 字号只能由用户在字号设置弹窗中选择；必须原样保留 global.fontSize 和 typography.fontSizes，不得根据对话修改字号。

当前简历：
{json.dumps(current, ensure_ascii=False, indent=2)}

当前布局配置：
{json.dumps(current_layout, ensure_ascii=False, indent=2)}

当前目标岗位 JD：
{json.dumps(state.jd_data or {}, ensure_ascii=False, indent=2)}

用户要求：
{request_text}
"""

    try:
        async with asyncio.timeout(90.0):
            response = await conversation_llm.ainvoke([
                SystemMessage(content="你只负责生成严格、完整、可校验的简历与受控布局 JSON。"),
                HumanMessage(content=prompt),
            ])
        candidate, layout_candidate = parse_edit_candidate(response.content, current, current_layout)
        # Font sizes are modal-only. Even a drifting proposal model cannot
        # smuggle size changes into an unrelated content/layout confirmation.
        layout_candidate["global"]["fontSize"] = current_layout["global"]["fontSize"]
        layout_candidate["typography"]["fontSizes"] = deepcopy(current_layout["typography"]["fontSizes"])
        layout_candidate = normalize_layout_config(layout_candidate)
        changes = build_resume_changes(current, candidate) + build_layout_changes(current_layout, layout_candidate)
        if not changes:
            pending = None
            assistant_message = AIMessage(content="当前简历已经符合这项要求，没有需要应用的修改。")
        else:
            pending = make_pending_confirmation(state, candidate, layout_candidate)
            assistant_message = AIMessage(content=_preview_summary(changes))
        print(
            f"[proposal_generator] 完成, 耗时={time.time() - start_time:.2f}s, "
            f"changes={len(changes)}"
        )
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
        }
    except Exception as exc:
        print(f"[proposal_generator] 失败: {exc}")
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
        }


async def interview_coach_node(state: AgentState) -> dict:
    """Run the source-traceable interview path without mutating resume data."""
    current = normalize_resume_data(state.resume_data or {})
    current_layout = normalize_layout_config(state.layout_data)
    memory = normalize_interview_memory(state.interview_memory or {}, state.interaction_mode)
    action = str(state.interaction_action or "answer")

    if action == "apply":
        suggestion = memory.get("latest_suggestion")
        try:
            if (state.workflow_state or {}).get("status") == "completed":
                raise ValueError("本轮深度打磨已结束，请重新开始后再应用建议")
            if (state.workflow_state or {}).get("phase") not in {"awaiting_apply", "questioning"}:
                raise ValueError("当前阶段没有可应用的改写建议")
            if not suggestion:
                raise ValueError("当前没有可应用的改写建议")
            candidate = apply_suggestion_candidate(current, suggestion)
            pending = make_pending_confirmation(state, candidate, current_layout)
            assistant_message = AIMessage(content=_preview_summary(pending.get("changes", [])))
            return {
                "messages": list(state.messages) + [assistant_message],
                "resume_data": state.resume_data or {},
                "jd_data": state.jd_data or {},
                "layout_data": current_layout,
                "pending_confirmation": pending,
                "proposal_error": None,
                "interview_memory": memory,
                "workflow_updates": {
                    "interaction_mode": state.interaction_mode,
                    "status": "awaiting_confirmation",
                    "phase": "awaiting_apply",
                    "focus_section": str((state.workflow_state or {}).get("focus_section", "")),
                    "current_question": str((state.workflow_state or {}).get("current_question", "")),
                    "last_node": "interview_coach",
                },
                "just_saved": False,
                "user_id": state.user_id,
                "task_id": state.task_id,
            }
        except Exception as exc:
            return {
                "messages": list(state.messages) + [AIMessage(content=str(exc))],
                "resume_data": state.resume_data or {},
                "jd_data": state.jd_data or {},
                "layout_data": current_layout,
                "pending_confirmation": None,
                "proposal_error": None,
                "interview_memory": memory,
                "workflow_updates": {
                    "interaction_mode": state.interaction_mode,
                    "status": "active",
                    "phase": "questioning",
                    "last_node": "interview_coach",
                },
                "just_saved": False,
                "user_id": state.user_id,
                "task_id": state.task_id,
            }

    try:
        result = await run_interview_turn(
            llm=conversation_llm,
            action=action,
            mode=state.interaction_mode,
            user_text=latest_human_text(state),
            resume_data=current,
            jd_data=state.jd_data or {},
            memory=memory,
            workflow=state.workflow_state or {},
            request_id=state.request_id,
        )
    except Exception as exc:
        print(f"[interview_coach] 结构化输出失败，安全回退: {exc}")
        harness_metrics.increment("interview_fallbacks_total")
        fallback_question = "这段经历中，最能证明你个人贡献的一个具体结果是什么？"
        result = {
            "content": f"本轮结构化分析暂时不可用，简历未被修改。\n\n{fallback_question}",
            "memory": memory,
            "workflow_updates": {
                "interaction_mode": state.interaction_mode,
                "status": "active",
                "phase": "questioning",
                "focus_section": str((state.workflow_state or {}).get("focus_section", "")),
                "current_question": fallback_question,
                "last_node": "interview_fallback",
            },
        }
    return {
        "messages": list(state.messages) + [AIMessage(content=result["content"])],
        "resume_data": state.resume_data or {},
        "jd_data": state.jd_data or {},
        "layout_data": current_layout,
        "pending_confirmation": None,
        "proposal_error": None,
        "interview_memory": result["memory"],
        "workflow_updates": result["workflow_updates"],
        "just_saved": False,
        "user_id": state.user_id,
        "task_id": state.task_id,
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
    
    # 计算总 tokens（用于日志显示）
    total_tokens = 0
    for msg in state.messages:
        content = getattr(msg, 'content', '')
        total_tokens += estimate_tokens(content)
    
    print(f"\n=== [Node] conversation_llm [开始] ===")
    print(f"Input: {len(state.messages)} messages")
    print(f"Total tokens (估算): {total_tokens}")
    for i, msg in enumerate(state.messages):
        content = getattr(msg, 'content', '')
        content_str = sanitize_for_log(content)
        msg_type = type(msg).__name__
        has_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls
        print(f"  [{i}] {msg_type}: {content_str[:80]}... (tool_calls: {bool(has_tool_calls)})")

    latest_request = latest_human_text(state)
    coaching_mode = is_resume_coaching_request(latest_request)
    messages = build_conversation_context(
        base_prompt=CONVERSATION_PROMPT,
        resume_data=state.resume_data,
        jd_data=state.jd_data,
        state_messages=state.messages,
        coaching_mode=coaching_mode,
        just_saved=getattr(state, "just_saved", False),
        memory_summary=getattr(state, "memory_summary", "") or "",
    )
    
    # 计算实际发送给 LLM 的 tokens 总数
    llm_input_tokens = 0
    for msg in messages:
        msg_content = getattr(msg, 'content', '')
        llm_input_tokens += estimate_tokens(msg_content)
    
    if getattr(state, 'just_saved', False):
        print("[Debug] 已添加 just_saved 提示给 LLM")

    # 调用 LLM
    print(f"[conversation_llm] [{time.strftime('%H:%M:%S')}] 开始调用 LLM, messages 数量: {len(messages)}")
    print(f"[conversation_llm] [{time.strftime('%H:%M:%S')}] total tokens (估算): {llm_input_tokens}")
    try:
        # Coaching/review turns are read-only by contract. Do not expose a
        # mutation tool at all, so model drift cannot create a save proposal.
        model = conversation_llm
        if not coaching_mode:
            model = conversation_llm.bind_tools(
                conversation_tools,
                tool_choice="auto"
            )
        # 不要添加 stop 序列，否则可能导致工具名称被截断
        # 增加超时时间到120秒，因为上下文可能较大
        async with asyncio.timeout(120.0):
            response = await model.ainvoke(messages)
    except asyncio.TimeoutError:
        print(f"[conversation_llm] LLM 调用超时! messages 数量: {len(messages)}")
        raise TimeoutError("LLM 调用超时，请稍后重试")
    except Exception as e:
        print(f"[conversation_llm] LLM 调用失败: {str(e)}")
        raise RuntimeError(f"LLM 调用失败: {str(e)}")

    elapsed_time = time.time() - start_time
    # 打印 LLM 输出（完整信息）
    print(f"[conversation_llm] [{time.strftime('%H:%M:%S')}] LLM 调用完成, 耗时: {elapsed_time:.2f}s")
    print("LLM Output:")
    print(f"  content: {repr(response.content)[:200]}")

    # 检查 tool_calls
    print(f"  === Tool Calls 检查 ===")
    print(f"  hasattr(response, 'tool_calls'): {hasattr(response, 'tool_calls')}")
    if hasattr(response, 'tool_calls'):
        print(f"  response.tool_calls: {response.tool_calls}")
        print(f"  bool(response.tool_calls): {bool(response.tool_calls)}")
        if response.tool_calls:
            print(f"  tool_calls 数量: {len(response.tool_calls)}")
            for i, tc in enumerate(response.tool_calls):
                print(f"    tool_call[{i}]: {tc}")
                print(f"    tool_call[{i}] type: {type(tc)}")

    # 检查 invalid_tool_calls
    print(f"  hasattr(response, 'invalid_tool_calls'): {hasattr(response, 'invalid_tool_calls')}")
    if hasattr(response, 'invalid_tool_calls'):
        print(f"  response.invalid_tool_calls: {response.invalid_tool_calls}")

    # 检查 additional_kwargs
    print(f"  hasattr(response, 'additional_kwargs'): {hasattr(response, 'additional_kwargs')}")
    if hasattr(response, 'additional_kwargs'):
        print(f"  response.additional_kwargs: {response.additional_kwargs}")
    print(f"=== [Node] conversation_llm [结束] 耗时: {elapsed_time:.2f}s ===\n")

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
        print(f"[conversation_node] 用户发送了新消息，清除 pending_confirmation")
        pending_conf = None
    
    output_state = {
        "messages": all_messages,
        "resume_data": state.resume_data or {},
        "jd_data": state.jd_data or {},
        "pending_confirmation": pending_conf,
        "just_saved": False,  # 清除 just_saved 标记
        "user_id": state.user_id,  # 保留用户ID
        "task_id": state.task_id,
        "memory_summary": getattr(state, "memory_summary", "") or "",
        "memory_version": getattr(state, "memory_version", 0) or 0,
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

    执行 LLM 调用的工具（如 save_resume_tool）
    支持延迟确认流程：当调用 save_resume_tool 时，不立即保存，而是触发前端确认
    """
    print(f"\n=== [Node] tool_node [被调用] ===")
    print(f"state.messages 数量: {len(state.messages)}")
    if state.messages:
        last_msg = state.messages[-1]
        print(f"最后一条消息类型: {type(last_msg).__name__}")
        if hasattr(last_msg, 'tool_calls'):
            print(f"最后一条消息 tool_calls: {last_msg.tool_calls}")
    debug_print_state(state, "tool_node_ENTER")
    
    start_time = time.time()
    print(f"\n=== [Node] tool_node [开始] ===")
    last_message = state.messages[-1]
    user_content = getattr(last_message, 'content', '') or ''
    
    # 处理确认回复
    if '[CONFIRM_REPLY:' in user_content:
        print("[Tool] 检测到确认回复")
        updated_resume_data = None
        updated_layout_data = None
        import re
        match = re.search(r'\[CONFIRM_REPLY:([^:]+):([^:\]]+)(?::([^\]]*))?\]', user_content)
        
        if match:
            user_confirm_id = match.group(1)
            value = match.group(2)
            selected_change_ids = [item for item in (match.group(3) or "").split(",") if item]
            print(f"[Tool] 用户发送的 confirm_id={user_confirm_id}, value={value}")
            print(f"[Tool] state.pending_confirmation confirm_id: {state.pending_confirmation.get('confirm_id') if state.pending_confirmation else None}")
            if state.pending_confirmation:
                db_confirm_id = state.pending_confirmation.get('confirm_id')
                print(f"[Tool] 数据库中的 confirm_id={db_confirm_id}")
                print(f"[Tool] ID匹配检查: {user_confirm_id == db_confirm_id}")
            
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
                    print("[Tool] 用户确认，执行保存")
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
                                print(f"[Tool] 首次JSON解析失败，尝试修复: {e}")
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
                            if base_hash and resume_digest(state.resume_data or {}) != base_hash:
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
                                if changes:
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
                                                from .database import SessionLocal, save_task_layout_config
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
                                            print(f"[Tool] 修改已保存，但布局或撤回版本记录失败: {revision_error}")
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
                                    print(f"[Tool] 保存结果: {result}")
                    except json.JSONDecodeError as e:
                        result = f"保存失败：JSON 解析错误 - {str(e)}"
                        saved_resume = False
                    except Exception as e:
                        result = f"保存失败：{str(e)}"
                        saved_resume = False
                elif value == 'cancel':
                    # 取消
                    print("[Tool] 用户取消")
                    result = "已取消保存"
                    saved_resume = False
                else:
                    result = "确认回复格式错误"
                    saved_resume = False
                
                # 清除 pending_confirmation
                pending_confirmation = None
                print("[Tool] 确认请求匹配成功，已执行保存/取消")
            else:
                print("[Tool] 无匹配的待确认请求")
                if pending_conf:
                    print(f"[Tool] 数据库中的 confirm_id={pending_conf.get('confirm_id')}，用户发送的 confirm_id={user_confirm_id}")
                    print(f"[Tool] 清除不匹配的 pending_confirmation")
                    # 清除不匹配的 pending_confirmation
                    pending_confirmation = None
                else:
                    print("[Tool] 无 pending_confirmation 数据")
                    pending_confirmation = None
                result = "无效的确认请求或确认已过期，请重新发送修改请求"
                saved_resume = False
        else:
            print("[Tool] 确认回复格式错误")
            result = "确认回复格式错误"
            saved_resume = False
            pending_confirmation = None
        
        # 创建 ToolMessage
        new_messages = [ToolMessage(content=result, tool_call_id="confirm", name="confirmation_handler")]

        elapsed_time = time.time() - start_time
        print(f"Tool results: {[m.content for m in new_messages]}")
        print(f"=== [Node] tool_node [结束] 耗时: {elapsed_time:.2f}s ===\n")

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
        }
    
    # 普通工具调用处理
    # 检查是否有工具调用
    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        print("=== [End] tool_node (no tool_calls) 耗时: 0.00s ===\n")
        # 没有工具调用时，返回原始消息（保持上下文）
        return {
            "messages": list(state.messages),
            "resume_data": state.resume_data or {},
            "jd_data": state.jd_data or {},
            "layout_data": normalize_layout_config(state.layout_data),
            "user_id": state.user_id,
            "task_id": state.task_id,
        }

    # 打印工具调用信息
    print(f"Tool calls: {[tc.name if hasattr(tc, 'name') else tc.get('name') for tc in last_message.tool_calls]}")

    # 执行工具调用
    new_messages = []
    updated_resume_data = None  # 用于保存从工具参数中提取的简历数据
    pending_confirmation = None  # 用于触发确认按钮

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

        # 查找工具函数
        tool_func = None
        for t in conversation_tools:
            if t.name == tool_name:
                tool_func = t
                break

        if not tool_func:
            result = f"错误: 工具 {tool_name} 不存在"
            print(f"[Tool] 工具 {tool_name} 调用失败: 工具不存在")
        else:
            try:
                # 如果是保存简历工具
                if tool_name == 'save_resume_tool':
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
                        print(f"[Tool] 生成确认标记，confirm_id={confirm_id}")
                else:
                    # 其他工具直接执行
                    result = tool_func.invoke(tool_args)

            except Exception as e:
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

    # 打印工具结果
    elapsed_time = time.time() - start_time
    print(f"Tool results: {[m.content for m in new_messages]}")
    print(f"=== [Node] tool_node [结束] 耗时: {elapsed_time:.2f}s ===\n")

    # 返回所有消息
    all_messages = list(state.messages) + new_messages
    
    # 检查是否执行了 save_resume_tool（实际保存）
    saved_resume = any(
        (isinstance(m, ToolMessage) and '简历已成功保存' in m.content)
        for m in new_messages
    )
    
    return {
        "messages": all_messages,
        "resume_data": updated_resume_data if updated_resume_data else (state.resume_data or {}),
        "jd_data": state.jd_data or {},
        "pending_confirmation": pending_confirmation,
        "just_saved": saved_resume,
        "user_id": state.user_id,
        "task_id": state.task_id,
        "memory_summary": getattr(state, "memory_summary", "") or "",
        "memory_version": getattr(state, "memory_version", 0) or 0,
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
    print(f"\n=== [Route] route_after_conversation [开始] ===")
    if not state.messages:
        print("[Route] 无消息，返回 END")
        return END

    last_message = state.messages[-1]
    has_tool_calls = hasattr(last_message, 'tool_calls') and last_message.tool_calls
    print(f"[Route] last_message type: {type(last_message).__name__}")
    print(f"[Route] has_tool_calls: {has_tool_calls}")
    if has_tool_calls:
        print(f"[Route] tool_calls: {[tc.name if hasattr(tc, 'name') else tc.get('name') for tc in last_message.tool_calls]}")

    # 检查是否有工具调用
    if has_tool_calls:
        print("[Route] 路由到 tool_node")
        return "tool_node"

    print("[Route] 路由到 END")
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
graph_builder.add_node("interview_coach", interview_coach_node)

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
graph_builder.add_edge("interview_coach", END)


# =============================================================================
# 入口路由函数
# =============================================================================

def entry_router(state: AgentState) -> str:
    """
    START 节点的路由决策

    Returns:
        'conversation_llm': 普通对话
        'tool_node': 确认按钮点击
        'direct_edit': 可确定解析的字段赋值
        'proposal_generator': 复杂的明确修改请求
    """
    if not state.messages:
        return "conversation_llm"

    if state.interaction_mode in INTERVIEW_MODES:
        return "interview_coach"

    # 检查最后一条消息是否是确认按钮点击
    last_message = state.messages[-1]
    user_content = getattr(last_message, 'content', '') or ''

    if '[CONFIRM_REPLY:' in user_content:
        return "tool_node"

    user_request = latest_human_text(state)
    if is_font_size_chat_change_request(user_request):
        return "direct_edit"
    if is_inline_format_request(user_request):
        return "direct_edit"
    resume_change = is_explicit_resume_change_request(user_request)
    layout_change = is_explicit_layout_change_request(user_request)
    if resume_change or layout_change:
        try:
            local_resume = build_local_edit_candidate(state) if resume_change else None
            local_layout = build_local_layout_candidate(state) if layout_change else None
            if (not resume_change or local_resume is not None) and (not layout_change or local_layout is not None):
                return "direct_edit"
        except Exception as exc:
            print(f"[Route] 本地解析不可用，转入结构化生成: {exc}")
        return "proposal_generator"

    return "conversation_llm"


# 设置入口点的条件路由
graph_builder.set_conditional_entry_point(entry_router)

# tool_node → conversation_llm / END
# 根据状态决定下一个节点
def tool_node_router(state: AgentState) -> str:
    # 如果有待确认状态，返回 END（等待前端确认）
    if getattr(state, 'pending_confirmation', None):
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
print("[Graph] 图编译完成（本地字段修改 + 单次复杂修改生成）")
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
