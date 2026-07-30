"""
简历助手 AI 代理模块
使用 LangGraph 构建的智能对话系统，帮助用户完善简历。

核心设计原则：
1. 状态驱动：所有状态通过 AgentState 传递，使用 LangGraph checkpointer 持久化
2. 工具调用：只在必要时调用工具（save_resume_tool）
3. 消息过滤：只传递 HumanMessage/AIMessage/SystemMessage 给 LLM，跳过 ToolMessage
4. 无硬编码回复：所有 AI 回复由 LLM 生成，不使用硬编码内容
5. 单LLM节点架构：conversation_llm 负责对话和工具调用决策
"""

import os
import json
import uuid
import asyncio
import httpx
import time
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from dataclasses import field
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from dataclasses import dataclass
from typing import List
from pydantic import BaseModel, Field


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

# 全局变量：当前用户ID（由 backend.main 设置）
current_user_id = None
current_task_id = None

# 加载环境变量
load_dotenv()
# Preserve Windows/system proxy auto-detection for future LLM calls without
# changing any machine-wide environment variable.
os.environ.setdefault("LANGCHAIN_OPENAI_TCP_KEEPALIVE", "0")


# =============================================================================
# Pydantic 数据模型定义
# =============================================================================

class BasicInfo(BaseModel):
    """基本信息"""
    name: str = Field(..., description="姓名")
    gender: str = Field(..., description="性别")
    phone: str = Field(..., description="手机号")
    email: str = Field(..., description="邮箱")
    target_position: str = Field(..., description="期望岗位")


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
    theses: List[Thesis] = Field(default_factory=list, description="论文列表")


class WorkExperience(BaseModel):
    """工作经历"""
    company_name: str = Field(..., description="公司名称")
    job_title: str = Field(..., description="职位名称")
    date_range: List[str] = Field(..., description="就职时间")
    job_type: str = Field(..., description="工作类型（实习/全职）")
    details: List[str] = Field(default_factory=list, description="工作详细内容")


class ProjectExperience(BaseModel):
    """项目经历"""
    project_name: str = Field(..., description="项目名称")
    role: str = Field(..., description="项目角色")
    date_range: List[str] = Field(..., description="项目时间")
    details: List[str] = Field(default_factory=list, description="项目详细内容")


class Others(BaseModel):
    """其他信息"""
    skills: List[str] = Field(default_factory=list, description="技能")
    certificates: List[str] = Field(default_factory=list, description="证书")
    languages: List[str] = Field(default_factory=list, description="语言")


class Resume(BaseModel):
    """完整简历数据结构"""
    basics: BasicInfo = Field(..., description="基本信息")
    education: List[Education] = Field(default_factory=list, description="教育背景")
    work_experience: List[WorkExperience] = Field(default_factory=list, description="工作经历")
    project_experience: List[ProjectExperience] = Field(default_factory=list, description="项目经历")
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

LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("BASE_URL", "").strip() or None
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3-flash-preview").strip() or "gemini-3-flash-preview"
LLM_ENABLED = bool(LLM_API_KEY)

# ChatOpenAI constructs clients during module import. A local sentinel keeps the
# non-AI parts of the application bootable until a real key is configured.
llm_client_api_key = LLM_API_KEY or "local-llm-disabled"

httpx_client = httpx.Client(
    timeout=httpx.Timeout(90.0),
    limits=httpx.Limits(max_connections=20),
)

KIMI_FIXED_TEMPERATURE_MODELS = {
    "k3",
    "k3-256k",
    "kimi-for-coding",
    "kimi-k3",
    "kimi-k2.7-code",
    "kimi-k2.7-code-highspeed",
    "kimi-k2.6",
}


def create_llm_for_config(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    temperature: float,
):
    """Create a chat model for a specific local configuration."""
    kwargs = {
        "api_key": api_key or "local-llm-disabled",
        "base_url": base_url,
        "model": model,
        "http_client": httpx_client,
        "max_retries": 3,
    }
    if model not in KIMI_FIXED_TEMPERATURE_MODELS:
        kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)


def create_llm(*, temperature: float):
    """Create a chat model while respecting provider-specific parameters."""
    return create_llm_for_config(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        temperature=temperature,
    )


# Conversation LLM - 负责对话和读取
conversation_llm = create_llm(temperature=0.1)

# JD Parser LLM - 负责解析JD文本/图片为JSON
jd_parser_llm = create_llm(temperature=0.0)


def reload_llm_config():
    """Reload local LLM settings without restarting the backend process."""
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_ENABLED
    global llm_client_api_key, conversation_llm, jd_parser_llm

    LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
    LLM_BASE_URL = os.getenv("BASE_URL", "").strip() or None
    LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3-flash-preview").strip() or "gemini-3-flash-preview"
    LLM_ENABLED = bool(LLM_API_KEY)
    llm_client_api_key = LLM_API_KEY or "local-llm-disabled"
    conversation_llm = create_llm(temperature=0.1)
    jd_parser_llm = create_llm(temperature=0.0)
    return {
        "configured": LLM_ENABLED,
        "model": LLM_MODEL,
        "base_url": LLM_BASE_URL or "",
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
3. **教育经历**：学校、专业、学位、时间、亮点标签
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

# 示例
输入：一张简历图片，包含姓名"张三"，手机"13800138000"，工作经历"2020.01 - 2022.12 在字节跳动担任产品经理"
输出：{"basics":{"name":"张三","gender":"","phone":"13800138000","email":"","target_position":""},"education":[],"work_experience":[{"company":"字节跳动","position":"产品经理","time":"2020.01 - 2022.12","type":"","content":[]}],"project_experience":[],"others":{"skills":[],"certificates":[],"languages":[]},"self_evaluation":[]}
'''



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
    pending_confirmation: dict = None  # 待确认状态
    just_saved: bool = False  # 刚保存简历后设置为 True
    user_id: int = None  # 当前用户ID
    task_id: str = None  # 当前任务ID


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

    # 构建系统消息，使用模板替换 resume_data
    if state.resume_data:
        resume_for_llm = {k: v for k, v in state.resume_data.items() if k != 'photo'}
        if 'basics' in resume_for_llm:
            resume_for_llm['basics'] = {k: v for k, v in resume_for_llm.get('basics', {}).items() if k != 'photo'}
        resume_json = json.dumps(resume_for_llm, ensure_ascii=False, indent=2)
        system_content = CONVERSATION_PROMPT.replace("{{resume_data}}", f"\n{resume_json}\n")
    else:
        system_content = CONVERSATION_PROMPT.replace("{{resume_data}}", "\n（简历数据尚未加载）")

    # 注入 jd_data
    if state.jd_data:
        jd_json = json.dumps(state.jd_data, ensure_ascii=False, indent=2)
        system_content = system_content.replace("{{jd_data}}", f"\n目标岗位 JD 数据：\n{jd_json}\n")
    else:
        system_content = system_content.replace("{{jd_data}}", "\n（目标岗位JD数据尚未加载）")

    # 过滤掉 ToolMessage，只保留 HumanMessage 和 AIMessage 传给 LLM
    # ToolMessage 是工具执行的结果，不应该传给 LLM
    # 注意：如果 AIMessage 带有 tool_calls（但工具还没执行），需要清空 tool_calls
    llm_messages = []
    for msg in state.messages:
        if isinstance(msg, ToolMessage):
            continue  # 跳过 ToolMessage
        elif isinstance(msg, HumanMessage):
            # 跳过确认消息（不作为 LLM 输入，但保留在数据库中）
            msg_content = getattr(msg, 'content', '') or ''
            if '[CONFIRM_REPLY:' in msg_content:
                continue
            llm_messages.append(msg)
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                # 如果 AIMessage 有 tool_calls，清空它们（工具会在 tool_node 中执行）
                llm_messages.append(AIMessage(content=msg.content, tool_calls=[]))
            elif getattr(state, 'just_saved', False) and msg.content and str(msg.content).strip().startswith("{"):
                # just_saved=True 且内容是 JSON，跳过 formatter_llm 的输出
                # conversation_llm 只需要知道 just_saved 状态，不需要完整 JSON
                continue
            else:
                llm_messages.append(msg)
        else:
            llm_messages.append(msg)

    # 消息已由 save_state_async 在超过 20 条时压缩，这里使用过滤后的消息
    messages = [SystemMessage(content=system_content)] + llm_messages
    
    # 计算实际发送给 LLM 的 tokens 总数
    llm_input_tokens = 0
    for msg in messages:
        msg_content = getattr(msg, 'content', '')
        llm_input_tokens += estimate_tokens(msg_content)
    
    # 如果刚保存了简历，添加一条 HumanMessage 提醒 LLM
    if getattr(state, 'just_saved', False):
        messages.append(HumanMessage(content="[系统提示：简历已成功保存到数据库，请不要调用任何工具，直接回复用户]"))
        llm_input_tokens += estimate_tokens("[系统提示：简历已成功保存...]")
        print("[Debug] 已添加 just_saved 提示给 LLM")

    # 调用 LLM
    print(f"[conversation_llm] [{time.strftime('%H:%M:%S')}] 开始调用 LLM, messages 数量: {len(messages)}")
    print(f"[conversation_llm] [{time.strftime('%H:%M:%S')}] total tokens (估算): {llm_input_tokens}")
    try:
        conversation_llm_with_tools = conversation_llm.bind_tools(
            conversation_tools,
            tool_choice="auto"
        )
        # 不要添加 stop 序列，否则可能导致工具名称被截断
        # 增加超时时间到120秒，因为上下文可能较大
        async with asyncio.timeout(120.0):
            response = await conversation_llm_with_tools.ainvoke(messages)
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
    user_is_confirming = any(
        '[CONFIRM_REPLY:' in (getattr(msg, 'content', '') or '')
        for msg in state.messages
        if isinstance(msg, HumanMessage)
    )
    
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
        "user_id": state.user_id  # 保留用户ID
    }
    
    # 创建临时状态对象用于调试
    class DebugState:
        def __init__(self, d):
            self.messages = d.get("messages", [])
            self.resume_data = d.get("resume_data")
            self.jd_data = d.get("jd_data")
            self.pending_confirmation = None
    
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
        import re
        match = re.search(r'\[CONFIRM_REPLY:([^:]+):([^:]+)\]', user_content)
        
        if match:
            user_confirm_id = match.group(1)
            value = match.group(2)
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
                
                if value == 'confirm':
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
                            # 解析 JSON 数据，失败时尝试修复
                            try:
                                updated_resume_data = json.loads(content)
                            except json.JSONDecodeError as e:
                                print(f"[Tool] 首次JSON解析失败，尝试修复: {e}")
                                fixed_content = fix_unquoted_json_strings(content)
                                try:
                                    updated_resume_data = json.loads(fixed_content)
                                    print(f"[Tool] 修复后解析成功")
                                except json.JSONDecodeError as e2:
                                    print(f"[Tool] 修复后仍然失败: {e2}")
                                    result = f"保存失败：JSON 解析错误 - {str(e)}"
                                    saved_resume = False
                                    # 仍然需要设置 result 变量并返回，但这里已经返回了
                                    # 直接跳到后面清除 pending_confirmation
                                    pending_confirmation = None
                                    return {
                                        "messages": state.messages + [ToolMessage(content=result)],
                                        "resume_data": state.resume_data,
                                        "jd_data": state.jd_data,
                                        "pending_confirmation": pending_confirmation,
                                        "just_saved": False,
                                        "user_id": state.user_id
                                    }

                            # 直接调用 update_resume 保存
                            from .tools import update_resume
                            result = update_resume(updated_resume_data, user_id=state.user_id)
                            saved_resume = True
                            print(f"[Tool] 保存结果: {result}")
                    except json.JSONDecodeError as e:
                        result = f"保存失败：JSON 解析错误 - {str(e)}"
                        saved_resume = False
                    except Exception as e:
                        result = f"保存失败：{str(e)}"
                        saved_resume = False
                else:
                    # 取消
                    print("[Tool] 用户取消")
                    result = "已取消保存"
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

        return {
            "messages": list(state.messages) + new_messages,
            "resume_data": final_resume_data,
            "jd_data": state.jd_data or {},
            "pending_confirmation": pending_confirmation,
            "just_saved": saved_resume,
            "user_id": state.user_id
        }
    
    # 普通工具调用处理
    # 检查是否有工具调用
    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        print("=== [End] tool_node (no tool_calls) 耗时: 0.00s ===\n")
        # 没有工具调用时，返回原始消息（保持上下文）
        return {"messages": list(state.messages), "resume_data": state.resume_data or {}, "jd_data": state.jd_data or {}}

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
                    except json.JSONDecodeError:
                        updated_resume_data = None
                    
                    # 传递 user_id
                    tool_args['user_id'] = state.user_id
                    tool_args['task_id'] = state.task_id
                    
                    # 生成确认标记，返回给前端
                    confirm_id = str(uuid.uuid4())[:8]
                    pending_confirmation = {
                        "confirm_id": confirm_id,
                        "content": "是否确认修改简历？",  # 固定提示文案
                        "options": [
                            {"label": "确认", "value": "confirm", "style": "primary"},
                            {"label": "取消", "value": "cancel", "style": "default"}
                        ],
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "status": "pending"
                    }
                    
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
        "user_id": state.user_id
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

# 添加节点（两个节点）
graph_builder.add_node("conversation_llm", conversation_node)
graph_builder.add_node("tool_node", tool_node)

# conversation_llm → tool_node / END
graph_builder.add_conditional_edges(
    "conversation_llm",
    route_after_conversation,
    {
        "tool_node": "tool_node",
        END: END
    }
)


# =============================================================================
# 入口路由函数
# =============================================================================

def entry_router(state: AgentState) -> str:
    """
    START 节点的路由决策

    Returns:
        'conversation_llm': 普通对话
        'tool_node': 确认按钮点击
    """
    if not state.messages:
        return "conversation_llm"

    # 检查最后一条消息是否是确认按钮点击
    last_message = state.messages[-1]
    user_content = getattr(last_message, 'content', '') or ''

    if '[CONFIRM_REPLY:' in user_content:
        return "tool_node"

    return "conversation_llm"


# 设置入口点的条件路由
graph_builder.set_conditional_entry_point(entry_router)

# tool_node → conversation_llm / END
# 根据状态决定下一个节点
def tool_node_router(state: AgentState) -> str:
    # 如果有待确认状态，返回 END（等待前端确认）
    if getattr(state, 'pending_confirmation', None):
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
print("[Graph] 图编译完成（单LLM节点架构）")
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
