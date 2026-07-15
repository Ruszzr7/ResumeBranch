# Resume Agent 架构详细文档

> 基于 LangGraph 构建的智能简历助手系统

## 目录

1. [系统概述](#系统概述)
2. [整体架构图](#整体架构图)
3. [核心数据模型](#核心数据模型)
4. [Agent State 详解](#agent-state-详解)
5. [节点详解](#节点详解)
6. [状态流转机制](#状态流转机制)
7. [持久化存储机制](#持久化存储机制)
8. [路由决策机制](#路由决策机制)
9. [工具系统](#工具系统)
10. [执行流程示例](#执行流程示例)

---

## 系统概述

### 核心设计原则

```
┌─────────────────────────────────────────────────────────────────┐
│                    Resume Agent 设计原则                         │
├─────────────────────────────────────────────────────────────────┤
│  1. 状态驱动：所有状态通过 AgentState 传递，使用 LangGraph        │
│     checkpointer 持久化                                          │
│  2. 工具调用：只在必要时调用工具（read_file, write_file）          │
│  3. 消息过滤：只传递 HumanMessage/AIMessage/SystemMessage         │
│     给 LLM，跳过 ToolMessage                                     │
│  4. 无硬编码回复：所有 AI 回复由 LLM 生成，不使用硬编码内容        │
└─────────────────────────────────────────────────────────────────┘
```

### 技术栈

| 组件 | 技术选型 | 用途 |
|------|----------|------|
| 图框架 | LangGraph | 工作流编排 |
| LLM | ChatOpenAI (Gemini-3-Flash) | 对话生成与格式化 |
| 状态持久化 | MemorySaver | 内存级状态存储 |
| 数据验证 | Pydantic | 数据模型定义 |
| HTTP客户端 | httpx | 异步HTTP请求 |

---

## 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Resume Agent 架构总览                               │
└─────────────────────────────────────────────────────────────────────────────────┘

                                    ┌─────────────┐
                                    │   User      │
                                    │  (CLI输入)  │
                                    └──────┬──────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           LangGraph StateGraph                                   │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                           入口点 (Entry Point)                            │   │
│  │                           conversation_llm                                │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│           │                                                                     │
│           │    ┌─────────────────────────────────────────────────────────────┐  │
│           │    │                   条件边 (Conditional Edges)                │  │
│           │    │              route_after_conversation()                     │  │
│           │    └─────────────────────────────────────────────────────────────┘  │
│           │              │                    │               │                  │
│           ▼              ▼                    ▼               ▼                  │
│  ┌─────────────┐ ┌─────────────┐    ┌─────────────┐ ┌─────────────┐            │
│  │ formatter   │ │   tool      │    │ conversation│ │    END      │            │
│  │ _llm        │ │   _node     │    │ _llm        │ │             │            │
│  │ (格式化节点) │ │  (工具节点) │    │ (对话节点)  │ │   (结束)    │            │
│  └──────┬──────┘ └──────┬──────┘    └──────┬──────┘ └─────────────┘            │
│         │               │                   │                                   │
│         │               │                   │                                   │
│         ▼               │                   │                                   │
│  ┌─────────────┐        │                   │                                   │
│  │  条件边     │        │                   │                                   │
│  │route_after_ │◄───────┘                   │                                   │
│  │ formatter() │        ┌───────────────────┘                                   │
│  └──────┬──────┘        │                                                       │
│         │               │                                                       │
│         ▼               │                                                       │
│  ┌─────────────┐        │                                                       │
│  │  tool_node  ├────────┘                                                       │
│  │  (工具节点) │                                                                │
│  └──────┬──────┘                                                                 │
│         │                                                                        │
│         │    ┌─────────────────────────────────────────────────────────────┐    │
│         │    │                      普通边 (Edge)                           │    │
│         │    │                 tool_node → conversation_llm                 │    │
│         │    └─────────────────────────────────────────────────────────────┘    │
│         │                                                                       │
│         ▼                                                                       │
│  ┌─────────────┐                                                               │
│  │conversation │                                                               │
│  │  _llm       │                                                               │
│  └─────────────┘                                                               │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   MemorySaver       │
                         │   (状态持久化)       │
                         └─────────────────────┘
```

---

## 核心数据模型

### Pydantic 数据模型层次结构

```
Resume (完整简历)
│
├── basics: BasicInfo (基本信息)
│   ├── name: str (姓名)
│   ├── gender: str (性别)
│   ├── phone: str (手机号)
│   ├── email: str (邮箱)
│   └── target_position: str (期望岗位)
│
├── education: List[Education] (教育背景列表)
│   └── Education
│       ├── school_name: str (学校名称)
│       ├── major: str (专业)
│       ├── degree: str (学历)
│       ├── date_range: List[str] (就读时间)
│       ├── school_tags: List[str] (学校标签)
│       └── theses: List[Thesis] (论文列表)
│
├── work_experience: List[WorkExperience] (工作经历列表)
│   └── WorkExperience
│       ├── company_name: str (公司名称)
│       ├── job_title: str (职位名称)
│       ├── date_range: List[str] (工作时间)
│       ├── job_type: str (实习/全职)
│       └── details: List[str] (工作内容)
│
├── project_experience: List[ProjectExperience] (项目经历列表)
│   └── ProjectExperience
│       ├── project_name: str (项目名称)
│       ├── role: str (项目角色)
│       ├── date_range: List[str] (项目时间)
│       └── details: List[str] (项目内容)
│
├── others: Others (其他信息)
│   └── Others
│       ├── skills: List[str] (技能)
│       ├── certificates: List[str] (证书)
│       └── languages: List[str] (语言)
│
└── self_evaluation: List[str] (自我评价列表)
```

### 代码定义

```python
class BasicInfo(BaseModel):
    """基本信息"""
    name: str = Field(..., description="姓名")
    gender: str = Field(..., description="性别")
    phone: str = Field(..., description="手机号")
    email: str = Field(..., description="邮箱")
    target_position: str = Field(..., description="期望岗位")

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
```

---

## Agent State 详解

### State 结构定义

```python
@dataclass
class AgentState:
    """
    代理状态

    Attributes:
        messages: 对话消息列表
        resume_data: 简历数据（从 resume.json 读取）
    """
    messages: list
    resume_data: dict = None  # None 表示尚未读取简历
```

### State 数据流向图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              State 数据流向                                      │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│ User Input   │────►│ conversation_node│────►│    State     │
│ HumanMessage │     │   (处理对话)      │     │ 更新messages │
└──────────────┘     └──────────────────┘     └──────┬───────┘
                                                     │
                                                     ▼
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│    State     │◄────│   tool_node      │◄────│ write_file   │
│ 读取resume   │     │   (执行工具)      │     │   工具       │
│ _data        │     └──────────────────┘     └──────────────┘
└──────┬───────┘            ▲
       │                    │
       │                    │ route_after_xxx()
       │                    │
       └────────────────────┘
              路由决策
```

### State 字段说明

| 字段 | 类型 | 初始值 | 说明 |
|------|------|--------|------|
| `messages` | `list` | 必填 | 存储所有对话消息，包括 HumanMessage、AIMessage、ToolMessage、SystemMessage |
| `resume_data` | `dict` | `None` | 存储从 resume.json 读取的简历数据，None 表示尚未加载 |

### State 更新时机

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            State 更新时机                                        │
└─────────────────────────────────────────────────────────────────────────────────┘

1. conversation_node 返回时:
   {
       "messages": state.messages + [AIMessage],  // 添加AI回复
       "resume_data": state.resume_data           // 保持不变
   }

2. tool_node 返回时:
   {
       "messages": state.messages + [ToolMessage], // 添加工具执行结果
       "resume_data": updated_resume_data          // 如果是read_file则更新
   }

3. formatter_node 返回时:
   {
       "messages": state.messages + [AIMessage],   // 添加格式化结果
       "resume_data": state.resume_data            // 保持不变
   }
```

### State 传入节点的方式

```python
# LangGraph 自动将 State 传入节点函数
async def conversation_node(state: AgentState) -> dict:
    # state 是当前图状态的快照
    # 包含: state.messages, state.resume_data
    pass

# 节点返回值会自动合并到 State
async def tool_node(state: AgentState) -> dict:
    # 返回的 dict 会与现有 State 合并
    return {
        "messages": state.messages + new_messages,
        "resume_data": updated_resume_data
    }
```

---

## 节点详解

### 1. conversation_node（对话节点）

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           conversation_node 流程图                               │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   节点进入       │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │ 检查消息是否为空  │
                              │ last_msg = ...  │
                              └────────┬────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                     │
                    ▼                                     ▼
           ┌─────────────────┐                   ┌─────────────────┐
           │ 消息为空        │                   │  简历数据存在？  │
           │ 返回原State     │                   └────────┬────────┘
           └─────────────────┘                            │
                                                           │
                    ┌──────────────────┬──────────────────┴──────────────────┐
                    │                 │                                     │
                    ▼                 ▼                                     ▼
           ┌─────────────────┐ ┌─────────────────┐               ┌─────────────────┐
           │ 构建系统消息    │ │ 使用空简历提示  │               │ 构建系统消息    │
           │ (无resume_data) │ │ CONVERSATION_   │               │ (有resume_data) │
           └────────┬────────┘ │ PROMPT          │               └────────┬────────┘
                    │          └─────────────────┘                            │
                    │                                                            │
                    └──────────────────────┬───────────────────────────────────┘
                                           │
                                           ▼
                              ┌─────────────────┐
                              │ 调用 LLM (带工具)│
                              │ conversation_   │
                              │ llm.bind_tools()│
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │  处理响应结果    │
                              │  清理标记字符    │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │   返回更新后的  │
                              │   State         │
                              └─────────────────┘
```

**核心逻辑说明：**

| 步骤 | 操作 | 代码位置 |
|------|------|----------|
| 1 | 进入节点，打印日志 | `resume_agent.py:398-402` |
| 2 | 检查最后一条消息 | `resume_agent.py:404-406` |
| 3 | 构建系统提示词 | `resume_agent.py:408-415` |
| 4 | 绑定工具并调用 LLM | `resume_agent.py:421-437` |
| 5 | 清理回复内容 | `resume_agent.py:446-453` |
| 6 | 返回新 State | `resume_agent.py:455-459` |

**LLM 配置：**

```python
conversation_llm = ChatOpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("BASE_URL"),
    model="gemini-3-flash-preview",
    http_client=httpx_client,
    max_retries=3,
    temperature=0.1  # 对话需要一定创造性
)
```

**可用工具：**
- `read_file_tool`：读取 resume.json 文件

---

### 2. tool_node（工具节点）

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            tool_node 流程图                                      │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   节点进入       │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │ 检查是否有工具调用│
                              │ last_message.   │
                              │ tool_calls      │
                              └────────┬────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                     │
                    ▼                                     ▼
           ┌─────────────────┐                   ┌─────────────────┐
           │ 无工具调用      │                   │  遍历工具调用    │
           │ 返回原State     │                   │  for tool_call  │
           └─────────────────┘                   └────────┬────────┘
                                                           │
                                                           ▼
                                          ┌────────────────┴────────────────┐
                                          │                                 │
                                          ▼                                 ▼
                                 ┌─────────────────┐              ┌─────────────────┐
                                 │ 查找工具函数     │              │ 执行工具函数     │
                                 │ tool_func       │              │ tool_func.      │
                                 └────────┬────────┘              │ invoke(args)    │
                                          │                       └────────┬────────┘
                                          │                                │
                                          │                                ▼
                                          │                    ┌─────────────────┐
                                          │                    │ 是 read_file？  │
                                          │                    │ 更新resume_data │
                                          │                    └────────┬────────┘
                                          │                             │
                                          └──────────────────┬──────────┘
                                                             │
                                                             ▼
                                            ┌────────────────┴────────────────┐
                                            │                                 │
                                            ▼                                 ▼
                                   ┌─────────────────┐              ┌─────────────────┐
                                   │  创建 ToolMessage│              │ 创建 ToolMessage│
                                   │  返回执行结果    │              │ 返回执行结果    │
                                   └─────────────────┘              └─────────────────┘
                                                             │
                                                             ▼
                                            ┌────────────────┴────────────────┐
                                            │                                 │
                                            ▼                                 ▼
                                   ┌─────────────────┐              ┌─────────────────┐
                                   │  所有工具执行完？│              │   返回更新后的  │
                                   │  (循环结束)      │              │   State         │
                                   └────────┬────────┘              └─────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐
                                   │  返回包含messages│
                                   │  和resume_data  │
                                   │  的新State      │
                                   └─────────────────┘
```

**核心逻辑说明：**

| 步骤 | 操作 | 代码位置 |
|------|------|----------|
| 1 | 检查工具调用 | `resume_agent.py:476-478` |
| 2 | 遍历工具调用 | `resume_agent.py:484-523` |
| 3 | 查找并执行工具 | `resume_agent.py:491-515` |
| 4 | 更新 resume_data | `resume_agent.py:507-511` |
| 5 | 创建 ToolMessage | `resume_agent.py:517-523` |
| 6 | 返回新 State | `resume_agent.py:525-529` |

---

### 3. formatter_node（格式化节点）

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          formatter_node 流程图                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   节点进入       │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │ 提取用户修改意图 │
                              │ extract_user_   │
                              │ intent(state)   │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │ 构建消息给LLM   │
                              │ SystemMessage   │
                              │ + HumanMessage  │
                              │ (含修改意图)     │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │ 调用 formatter_ │
                              │ llm (带write_   │
                              │ file工具)       │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │  清理响应内容    │
                              │  提取JSON       │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │  验证JSON格式    │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │   返回更新后的  │
                              │   State         │
                              └─────────────────┘
```

**核心逻辑说明：**

| 步骤 | 操作 | 代码位置 |
|------|------|----------|
| 1 | 进入节点 | `resume_agent.py:538-540` |
| 2 | 提取修改意图 | `resume_agent.py:542-543` |
| 3 | 构建消息 | `resume_agent.py:546-558` |
| 4 | 调用 LLM | `resume_agent.py:560-569` |
| 5 | 清理并提取 JSON | `resume_agent.py:574-587` |
| 6 | 验证 JSON | `resume_agent.py:589-595` |
| 7 | 返回 State | `resume_agent.py:597-603` |

**LLM 配置：**

```python
formatter_llm = ChatOpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("BASE_URL"),
    model="gemini-3-flash-preview",
    http_client=httpx_client,
    max_retries=3,
    temperature=0.0  # 格式化需要确定性输出
)
```

**可用工具：**
- `write_file_tool`：写入 JSON 到文件

---

## 状态流转机制

### 消息类型定义

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            消息类型说明                                          │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┬──────────────────────────────────────────────────────────────┐
│    消息类型       │                           说明                               │
├──────────────────┼──────────────────────────────────────────────────────────────┤
│ SystemMessage    │ 系统提示词，定义LLM角色和行为规则                             │
├──────────────────┼──────────────────────────────────────────────────────────────┤
│ HumanMessage     │ 用户输入，对话的开始                                         │
├──────────────────┼──────────────────────────────────────────────────────────────┤
│ AIMessage        │ LLM回复，可能包含 tool_calls                                 │
├──────────────────┼──────────────────────────────────────────────────────────────┤
│ ToolMessage      │ 工具执行结果，包含 read_file/write_file 的返回内容           │
└──────────────────┴──────────────────────────────────────────────────────────────┘
```

### 完整状态流转序列图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           状态流转序列图                                         │
└─────────────────────────────────────────────────────────────────────────────────┘

  用户      conversation_     tool_node      formatter_      Memory
  输入         llm                            llm             Saver
   │             │                             │               │
   │ HumanMessage│                             │               │
   │────────────►│                             │               │
   │             │                             │               │
   │             │ AIMessage                   │               │
   │             │(含tool_calls)               │               │
   │             │─────────────►               │               │
   │             │             │               │               │
   │             │             │ ToolMessage   │               │
   │             │             │(read_file结果)│               │
   │             │             │◄──────────────│               │
   │             │             │               │               │
   │             │ AIMessage   │               │               │
   │             │(常规回复)   │               │               │
   │◄────────────│─────────────►               │               │
   │             │                             │               │
   │ HumanMessage│                             │               │
   │(修改确认)   │                             │               │
   │────────────►│                             │               │
   │             │                             │               │
   │             │ AIMessage                   │               │
   │             │("[转向 formatter_llm]")      │               │
   │             │───────────────────────────────────────────►  │
   │             │                             │               │
   │             │                             │ AIMessage     │
   │             │                             │(含tool_calls) │
   │             │                             │───────►       │
   │             │                             │       │       │
   │             │                             │       │ ToolMessage
   │             │                             │       │(write_file)
   │             │                             │       │◄───────
   │             │                             │       │       │
   │             │                             │ AIMessage    │
   │             │                             │(格式化结果)  │
   │             │◄─────────────────────────────────────────────│
   │             │                             │               │
   │             │ HumanMessage (下一轮对话)    │               │
   │◄────────────│─────────────────────────────►│               │
   │             │                             │               │
   │             │ ... (循环)                   │               │
   │             │                             │               │
   │             │                             │               │ State持久化
   └─────────────┴─────────────────────────────┴───────────────┴────────────►
```

---

## 持久化存储机制

### MemorySaver 简介

```python
# 编译图时添加 checkpointer
memory = MemorySaver()
graph = graph_builder.compile(checkpointer=memory)
```

### 持久化特性

| 特性 | 说明 |
|------|------|
| 存储位置 | 内存（MemorySaver） |
| 持久化内容 | 完整的 AgentState（messages + resume_data） |
| 持久化时机 | 每个节点执行完成后自动保存 |
| 检索方式 | 通过 thread_id 恢复对话状态 |

### 使用方式

```python
# 创建配置，指定 thread_id
config = {"configurable": {"thread_id": thread_id}}

# 执行图
async for chunk in graph.astream(initial_state, config=config):
    # 每个 chunk 都是一个节点输出
    pass

# 后续调用时使用相同 thread_id，即可恢复状态
```

### 状态恢复流程

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           状态恢复流程                                           │
└─────────────────────────────────────────────────────────────────────────────────┘

  用户新输入
      │
      ▼
  ┌───────────────────┐
  │ 创建 config       │
  │ {thread_id: xxx}  │
  └─────────┬─────────┘
            │
            ▼
  ┌───────────────────┐
  │ MemorySaver 查询  │
  │ 相同 thread_id    │
  └─────────┬─────────┘
            │
            ▼
  ┌───────────────────┐     ┌───────────────────┐
  │ 找到历史状态      │     │ 未找到历史状态    │
  └─────────┬─────────┘     └─────────┬─────────┘
            │                        │
            ▼                        ▼
  ┌───────────────────┐     ┌───────────────────┐
  │ 恢复到历史State   │     │ 创建新的初始State │
  │ (messages +       │     │ (messages +       │
  │  resume_data)     │     │  resume_data=None)│
  └─────────┬─────────┘     └───────────────────┘
            │
            ▼
  ┌───────────────────┐
  │ 从恢复的State     │
  │ 继续执行          │
  └───────────────────┘
```

---

## 路由决策机制

### 路由函数概览

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            路由函数说明                                          │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┬────────────────────────┬───────────────────────────────────┐
│      路由函数        │       调用时机          │           返回值                  │
├─────────────────────┼────────────────────────┼───────────────────────────────────┤
│ route_after_        │ conversation_llm       │ 'formatter_llm' / 'tool_node' /   │
│ conversation()      │ 执行完成后             │ END                               │
├─────────────────────┼────────────────────────┼───────────────────────────────────┤
│ route_after_        │ formatter_llm          │ 'tool_node'                       │
│ formatter()         │ 执行完成后             │                                   │
└─────────────────────┴────────────────────────┴───────────────────────────────────┘
```

### route_after_conversation 决策逻辑

```python
def route_after_conversation(state: AgentState) -> str:
    """
    conversation_llm 后的路由决策

    优先级：
    1. 检查是否有工具调用
    2. 检查是否是 ToolMessage（工具刚执行完）
    3. 检查是否需要转向 formatter_llm
    4. 无工具调用 → 结束对话
    """
    last_message = state.messages[-1]
    content = str(getattr(last_message, 'content', ''))

    # 1. 有工具调用 → tool_node
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tool_node"

    # 2. 如果最后一条是 ToolMessage → 根据内容判断
    if isinstance(last_message, ToolMessage):
        # 防止重复调用
        if len(state.messages) >= 2:
            prev_message = state.messages[-2]
            if isinstance(prev_message, ToolMessage) and prev_message.name == last_message.name:
                return END
        # 根据工具返回内容判断下一步：
        # - "的内容：" -> read_file 结果，需要继续对话
        # - "已成功保存" -> write_file 结果，直接结束
        if '已成功保存' in content:
            return END
        return "conversation_llm"

    # 3. 检测 "[转向 formatter_llm]" 标记 → formatter_llm
    if "[转向 formatter_llm]" in content:
        return "formatter_llm"

    # 4. 无工具调用 → 结束
    return END
```

> **注意**：路由决策完全依赖 LLM 生成的 `"[转向 formatter_llm]"` 标记，通过检查 ToolMessage 的返回内容来区分 read_file 和 write_file 操作。

**路由决策流程图：**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     route_after_conversation 决策流程                           │
└─────────────────────────────────────────────────────────────────────────────────┘

                           ┌─────────────────┐
                           │ conversation_   │
                           │ llm 返回        │
                           └────────┬────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │ 包含"[转向       │
                           │ formatter_llm]"?│
                           └────────┬────────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                         ▼                     ▼
                ┌─────────────────┐   ┌─────────────────┐
                │     是          │   │      否         │
                │ formatter_llm   │   │ 有tool_calls?   │
                └─────────────────┘   └────────┬────────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │                     │
                                    ▼                     ▼
                           ┌─────────────────┐   ┌─────────────────┐
                           │      是         │   │      否         │
                           │   tool_node     │   │ 是ToolMessage?  │
                           └─────────────────┘   └────────┬────────┘
                                                          │
                                           ┌──────────────┴──────────────┐
                                           │                             │
                                           ▼                             ▼
                                  ┌─────────────────┐           ┌─────────────────┐
                                  │ 是 (需检查重复) │           │      否         │
                                  │ prev也是        │           │ 检测"[转向      │
                                  │ ToolMessage?    │           │ formatter_llm]"?│
                                  └────────┬────────┘           └────────┬────────┘
                                           │                              │
                                ┌──────────┴──────────┐          ┌──────────┴──────────┐
                                │                     │          │                     │
                                ▼                     ▼          ▼                     ▼
                       ┌─────────────────┐   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
                       │      是         │   │      否         │ │      是         │ │      否         │
                       │      END        │   │ "已成功保存"?   │ │ formatter_llm   │ │      END        │
                       └─────────────────┘   └────────┬────────┘ └─────────────────┘ └─────────────────┘
                                                      │
                                     ┌────────────────┴────────────────┐
                                     │                                 │
                                     ▼                                 ▼
                            ┌─────────────────┐              ┌─────────────────┐
                            │      是         │              │      否         │
                            │      END        │              │ conversation_   │
                            └─────────────────┘              │ llm (继续对话)  │
                                                              └─────────────────┘
```

### route_after_formatter 决策逻辑

```python
def route_after_formatter(state: AgentState) -> str:
    """
    formatter_llm 后的路由决策

    简单逻辑：
    - 有工具调用（write_file）→ tool_node
    - 无工具调用 → conversation_llm
    """
    last_message = state.messages[-1]

    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tool_node"

    return "conversation_llm"
```

---

## 工具系统

### 工具定义

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            工具系统架构                                          │
└─────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────┐
│                              conversation_tools                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │  read_file_tool                                                         │  │
│  │  - 用途：读取 resume.json 文件                                           │  │
│  │  - 参数：file_path (默认 "resume.json")                                  │  │
│  │  - 返回：文件内容的字符串描述                                             │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────┐
│                              formatter_tools                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │  write_file_tool                                                        │  │
│  │  - 用途：写入 JSON 内容到 resume.json                                    │  │
│  │  - 参数：file_path, content (JSON字符串)                                 │  │
│  │  - 行为：清理 markdown 代码块标记，提取 JSON 并保存                        │  │
│  │  - 返回：成功消息                                                        │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────┘
```

### read_file_tool 实现

```python
@tool
def read_file_tool(file_path: str = "resume.json") -> str:
    """读取简历文件内容"""
    return read_file(file_path=file_path)
```

### write_file_tool 实现

```python
@tool
def write_file_tool(file_path: str = "resume.json", content: str = "") -> str:
    """
    写入 JSON 内容到文件

    处理步骤：
    1. 清理 ```json 和 ``` 标记
    2. 提取 JSON 对象（如果包含其他文字）
    3. 保存到文件
    """
    import re

    # 清理 markdown 代码块标记
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    content = content.strip()

    # 提取 JSON 对象
    if not content.startswith('{'):
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            content = match.group()

    # 保存文件
    write_file(file_path=file_path, content=content)
    return "简历已成功保存到 resume.json"
```

### 工具调用流程

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           工具调用完整流程                                       │
└─────────────────────────────────────────────────────────────────────────────────┘

   LLM决定调用工具                    工具执行                    状态更新
       │                               │                          │
       ▼                               ▼                          ▼
┌───────────────┐            ┌──────────────────┐        ┌──────────────────┐
│ AIMessage     │            │ tool_node        │        │ AgentState       │
│ 包含          │───────────►│ 查找工具函数     │        │ messages:        │
│ tool_calls    │            │ tool_func.invoke │        │   [...,          │
└───────────────┘            │ (args)           │        │    ToolMessage]  │
                             └────────┬─────────┘        │ resume_data:     │
                                      │                  │   updated_data   │
                                      ▼                  └──────────────────┘
                             ┌──────────────────┐
                             │ 解析工具返回     │
                             │ 更新 resume_data │
                             │ (如果是read)     │
                             └────────┬─────────┘
                                      │
                                      ▼
                             ┌──────────────────┐
                             │ 创建 ToolMessage │
                             │ 返回给 LLM       │
                             └──────────────────┘
```

---

## 执行流程示例

### 场景：用户首次问候并询问简历信息

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       场景：用户首次问候并询问简历                                │
└─────────────────────────────────────────────────────────────────────────────────┘

用户输入: "你好，请帮我看看我的简历内容"

┌───────────────────────────────────────────────────────────────────────────────┐
│ Step 1: 初始状态创建                                                          │
└───────────────────────────────────────────────────────────────────────────────┘

initial_state = {
    "messages": [HumanMessage(content="你好，请帮我看看我的简历内容")],
    "resume_data": None
}

┌───────────────────────────────────────────────────────────────────────────────┐
│ Step 2: conversation_llm 执行                                                 │
└───────────────────────────────────────────────────────────────────────────────┘

输入: AgentState(messages=[HumanMessage(...)], resume_data=None)
处理:
  - 构建系统消息 (resume_data 为空)
  - 调用 conversation_llm
输出: AgentState(
    messages=[HumanMessage(...), AIMessage(content="您好！请稍等，我帮您查看简历...", tool_calls=[...])],
    resume_data=None
)
路由: "tool_node" (因为有 tool_calls)

┌───────────────────────────────────────────────────────────────────────────────┐
│ Step 3: tool_node 执行                                                        │
└───────────────────────────────────────────────────────────────────────────────┘

输入: AgentState(messages=[..., AIMessage(tool_calls=[...])], resume_data=None)
处理:
  - 识别到 read_file_tool 调用
  - 执行 read_file_tool
  - 解析返回内容，更新 resume_data
  - 创建 ToolMessage
输出: AgentState(
    messages=[..., AIMessage(...), ToolMessage(content="文件 resume.json 的内容：...")],
    resume_data={...}  # 简历数据
)
路由: "conversation_llm" (工具执行完成)

┌───────────────────────────────────────────────────────────────────────────────┐
│ Step 4: conversation_llm 执行 (第二轮)                                         │
└───────────────────────────────────────────────────────────────────────────────┘

输入: AgentState(messages=[..., ToolMessage(...)], resume_data={...})
处理:
  - 构建系统消息 (resume_data 有数据)
  - 调用 conversation_llm (可以看到 ToolMessage 的结果)
  - 生成最终回复
输出: AgentState(
    messages=[..., ToolMessage(...), AIMessage(content="我已经查看了您的简历，您目前的基本信息是...")],
    resume_data={...}
)
路由: END (无工具调用)
```

### 场景：用户修改简历

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       场景：用户修改简历                                         │
└─────────────────────────────────────────────────────────────────────────────────┘

用户输入: "把我的期望岗位改成算法工程师"

┌───────────────────────────────────────────────────────────────────────────────┐
│ Step 1-2: conversation_llm 执行 (识别修改意图)                                 │
└───────────────────────────────────────────────────────────────────────────────┘

输入: AgentState(messages=[HumanMessage("把我的期望岗位改成算法工程师")], resume_data={...})
处理:
  - LLM 理解用户意图
  - 生成回复并添加 "[转向 formatter_llm]" 标记
输出: AgentState(
    messages=[HumanMessage(...), AIMessage(content="好的，我来帮您修改。把期望岗位改为算法工程师对吧？[转向 formatter_llm]")],
    resume_data={...}
)
路由: "formatter_llm" (检测到标记)

┌───────────────────────────────────────────────────────────────────────────────┐
│ Step 3: formatter_llm 执行                                                    │
└───────────────────────────────────────────────────────────────────────────────┘

输入: AgentState(messages=[..., AIMessage("[转向 formatter_llm]")], resume_data={...})
处理:
  - extract_user_intent() 提取修改意图
  - 调用 formatter_llm (带 write_file_tool)
  - 生成格式化的 JSON
输出: AgentState(
    messages=[..., AIMessage(content="...", tool_calls=[write_file_tool])],
    resume_data={...}
)
路由: "tool_node" (有 tool_calls)

┌───────────────────────────────────────────────────────────────────────────────┐
│ Step 4: tool_node 执行                                                        │
└───────────────────────────────────────────────────────────────────────────────┘

输入: AgentState(messages=[..., AIMessage(tool_calls=[...])], resume_data={...})
处理:
  - 执行 write_file_tool
  - 保存 JSON 到文件
  - 创建 ToolMessage
输出: AgentState(
    messages=[..., ToolMessage(content="简历已成功保存到 resume.json")],
    resume_data={...}
)
路由: END (检测到"已成功保存" -> 结束对话)
```

---

## 总结

### 架构特点

1. **双 LLM 设计**：
   - `conversation_llm`：负责对话和意图理解，temperature=0.1
   - `formatter_llm`：负责格式化 JSON，temperature=0.0

2. **状态驱动**：
   - 所有数据通过 `AgentState` 传递
   - `messages` 存储对话历史
   - `resume_data` 存储简历数据

3. **工具调用**：
   - `read_file_tool`：读取简历
   - `write_file_tool`：保存简历
   - 工具调用由 LLM 决定

4. **持久化**：
   - 使用 `MemorySaver`
   - 通过 `thread_id` 区分不同对话
   - 自动保存每个节点的状态

5. **路由控制**：
   - `route_after_conversation`：对话后路由
   - `route_after_formatter`：格式化后路由
   - 消息驱动：通过检查 ToolMessage 返回内容区分 read/write 操作
   - 标记驱动：使用 `[转向 formatter_llm]` 标记触发修改流程

### 扩展建议

| 扩展方向 | 建议 |
|----------|------|
| 持久化存储 | 将 MemorySaver 替换为 PostgreSQL/SQLite checkpointer |
| 多文件支持 | 修改工具支持多个简历文件 |
| 模板功能 | 添加简历模板生成功能 |
| 对话历史 | 限制 messages 长度防止上下文过长 |
| 并发支持 | 使用 AsyncLangGraph 支持高并发 |

---

*文档生成时间: 2026-01-01*
*基于 resume_agent.py v1.0*
