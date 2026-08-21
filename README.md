# DeepAgents - AI 简历助手

基于 **LangGraph + Vue3** 的智能简历助手，通过对话帮助用户完善简历内容，支持岗位 JD 匹配分析和 PDF 导出。

---

## 📋 目录

- [项目概述](#项目概述)
- [技术栈](#技术栈)
- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [API 接口](#api-接口)
- [部署指南](#部署指南)
- [开发说明](#开发说明)

---

## 🚀 项目概述

DeepAgents 是一个全栈 AI 简历优化工具，具有以下特点：

- **对话式交互**：通过自然语言与 AI 对话，智能修改简历
- **双运行模式**：本地单用户免登录，或 JWT 多用户隔离；多用户版每个账号只保留一个活跃登录会话
- **数据持久化**：本地默认使用免服务的 SQLite，多人自托管推荐 MySQL 8.4
- **AI 驱动**：基于 LangGraph 构建的智能 Agent
- **PDF 导出**：服务端统一使用 Chromium 浏览器打印，保持与网页预览一致的排版引擎

### 两种部署入口

| 配置 | 本地单用户（默认） | 多人自托管（可选） |
|------|--------------------|--------------------|
| `APP_MODE` | `local` | `multi_user` |
| 推荐数据库 | SQLite 文件 | MySQL 8.4 |
| 账号功能 | 免登录，账号接口关闭 | JWT 登录、注册、邀请码、管理员 |
| 启动方式 | `scripts\start_local.cmd` | `scripts\start_multi_user.cmd` |
| 导出 | 保存到 `output/resumes/`，可一键打开目录 | 默认仅浏览器下载 |

两种入口复用同一套 Vue 界面、FastAPI 业务接口和 SQLAlchemy 模型。运行模式是部署配置，不是页面内开关；SQLite 与 MySQL 数据相互独立，不自动迁移或覆盖。

---

## 🛠️ 技术栈

### 前端
| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | 3.5.24 | 响应式 UI 框架 |
| Vite | 7.2.4 | 构建工具 |
| Element Plus | 2.13.0 | UI 组件库 |
| Vue Router | 4.6.4 | 路由管理 |
| marked | 17.0.1 | Markdown 渲染 |

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.104+ | HTTP API 框架 |
| Uvicorn | 0.24+ | ASGI 服务器 |
| Gunicorn | 21+ | WSGI 服务器（生产环境） |
| SQLAlchemy | 2.0+ | ORM |
| LangGraph | 1.0+ | AI Agent 工作流、状态与检查点 |
| LangChain Core / OpenAI | 1.1+ | 消息、Prompt、工具与模型适配 |
| Chromium（Chrome/Edge） | 112+ | 与浏览器预览一致的 PDF 生成 |
| Poppler | 系统包 | Docker 中把 PDF 转为 Agent 可分析的页面快照；Windows 可使用项目配置的转换工具 |
| python-jose | 3.3+ | JWT 认证 |
| bcrypt | 4.0+ | 密码加密 |

> **注意**：解析API默认使用 `gemini-3.6-flash` 模型，需使用支持原生pdf上传的 LLM API（如 Google AI Studio 或自定义 BASE_URL）。对话API支持任意的 LLM API。两种API均可于设置中更改，保存前先测试连通。

---

## ✨ 核心功能

### 用户系统
- ✅ `local` / `multi_user` 双模式切换
- ✅ 用户注册（邀请码机制）
- ✅ 用户登录/登出
- ✅ JWT Token 认证（24 小时有效期）
- ✅ 服务端会话撤销：新登录会使旧设备登录失效，同一浏览器多标签页复用当前会话
- ✅ 管理员后台（管理邀请码）
- ✅ 多用户数据隔离
- ✅ 同一简历任务的修改预览互斥，跨对话与多进程由数据库锁兜底

### 简历编辑
- ✅ 主简历—岗位版本工作区：一份基础简历对应一份主简历，每个 JD 对应独立岗位版本
- ✅ 新岗位版本自动继承基础简历，各版本的简历、JD 和对话互相隔离
- ✅ 主简历与岗位版本可删除，基础简历提供防误删保护
- ✅ 紧凑岗位版本栏与固定三栏布局，优先保证简历完整显示
- ✅ 🔧 二次确认后恢复默认页边距、模块间距、行距与字号
- ✅ 简历预览支持适宽、整页及 40%～100% 手动缩放
- ✅ 对话式 AI 优化简历
- ✅ 表单式编辑（基本信息、教育、工作、项目）
- ✅ 富文本编辑（多行与单行字段均支持 Ctrl+B 加粗）
- ✅ 对话式局部加粗/取消加粗：引用唯一原文生成确定性预览，确认后才保存；歧义时拒绝修改
- ✅ 日期选择器（支持"至今"）
- ✅ 照片上传（Base64）
- ✅ 实时预览（A4 分页）
- ✅ 中英文简历切换：结构化翻译并按字段复用未变化内容，避免重复调用模型
- ✅ 统一排版协议：预览、PDF、DOCX 共用微软雅黑/Arial、字号、行距、模块间距与页边距
  - 默认层级：姓名 14pt、模块标题 11pt、条目标题 10pt、元信息/正文/标签 9pt
  - 姓名、模块标题、条目标题、元信息、正文和标签字号可在排版弹窗中按 0.5pt 分别调整
  - 默认节奏：行距 1.25、模块间距 4.5pt、页边距上下 8.5mm / 左右 9mm
- ✅ 当前简历栏目设置：可修改栏目标题、选择无标记/分点/编号，并将研究方向、荣誉、论文、证书与语言并入教育经历
  - 论文使用独立的可编辑字符串列表；学校标签按 `学校 · 211 · 双一流` 显示
  - 标题与正文等自由文本统一支持 Ctrl+B；学校、公司、项目名称等默认粗体也可由用户取消
  - 页面预览、PDF、DOCX 共用 schema v9 `layout_config`、内容块契约、栏目规则与物理排版 token

### JD 匹配
- ✅ JD 文本粘贴
- ✅ JD 图片 OCR 识别
- ✅ 表单式 JD 编辑
- ✅ 智能解析和结构化

### 导出功能
- ✅ 服务端 Chromium PDF 导出，复用浏览器的中文换行与双端对齐规则
- ✅ Chromium 缺失或执行失败时给出明确错误，不使用不同排版引擎静默降级
- ✅ PDF / DOCX 使用 `简历组名_版本名_导出日期` 命名，本地重复导出自动增加序号并保留到项目输出目录

### AI 特性
- ✅ SSE 流式响应
- ✅ 上下文压缩（历史过长自动压缩）
- ✅ 对话历史持久化
- ✅ 模块高亮动画

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        DeepAgents 系统架构                       │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│   前端 (Vue3)    │
│  - App.vue       │
│  - Router        │
│  - Components    │
└────────┬─────────┘
         │ HTTP/WebSocket
         ▼
┌─────────────────────────────────────────────────────────┐
│                 后端 (FastAPI)                          │
│  ┌─────────────────────────────────────────────────┐  │
│  │  API 层                                        │  │
│  │  - /auth/* (登录/注册)                         │  │
│  │  - /chat (SSE 流式对话)                        │  │
│  │  - /resume/* (简历 CRUD)                       │  │
│  │  - /jd/* (JD CRUD)                             │  │
│  │  - /export_pdf (PDF 导出)                      │  │
│  │  - /tasks/{id}/layout (当前简历排版)            │  │
│  └─────────────────┬───────────────────────────────┘  │
│                    │                                   │
│  ┌─────────────────▼───────────────────────────────┐  │
│  │  业务逻辑层                                     │  │
│  │  - JWT 认证                                     │  │
│  │  - 上下文压缩                                   │  │
│  │  - 状态管理                                     │  │
│  └─────────────────┬───────────────────────────────┘  │
│                    │                                   │
│  ┌─────────────────▼───────────────────────────────┐  │
│  │  LangGraph Agent                                │  │
│  │  ┌──────────────────────────────────────────┐ │  │
│  │  │ conversation_llm (对话节点)               │ │  │
│  │  │ - 处理用户对话                             │ │  │
│  │  │ - 调用 save_resume_tool                   │ │  │
│  │  └──────────────┬───────────────────────────┘ │  │
│  │                 │                               │  │
│  │  ┌──────────────▼──────────────┐              │  │
│  │  │ tool_node (工具执行节点)      │              │  │
│  │  │ - 执行工具调用                 │              │  │
│  │  │ - 处理确认流程                 │              │  │
│  │  └───────────────────────────────┘              │  │
│  └─────────────────────────────────────────────────┘  │
│                    │                                   │
│  ┌─────────────────▼───────────────────────────────┐  │
│  │  数据层 (SQLAlchemy)                            │  │
│  │  - User (用户表)                                │  │
│  │  - ResumeProject (基础简历项目)                 │  │
│  │  - ProjectTask (JD 任务版本、对话与上下文)      │  │
│  │  - Resume (简历表)                              │  │
│  │  - JobDescription (JD表)                        │  │
│  │  - Conversation (对话历史表)                    │  │
│  │  - InviteCode (邀请码表)                        │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────┐
│  SQLite 数据库   │
│  deepagents.db   │
└──────────────────┘
```

### LangGraph 工作流

```
┌───────────────────────────────────────────────────────────────────────┐
│                        LangGraph StateGraph                            │
├───────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    START (入口条件路由)                        │  │
│  │              entry_router() - 检查是否是确认回复              │  │
│  └──────────────┬───────────────────────────────────────────┘  │
│                 │                                              │
│         ┌───────┴───────┐                                      │
│         │               │                                      │
│         ▼               ▼                                      │
│  ┌─────────────┐  ┌─────────────┐                              │
│  │conversation │  │  tool_node  │  用户点击确认按钮时走这里    │
│  │   _llm      │  │  (工具执行) │                              │
│  └──────┬──────┘  └──────┬──────┘                              │
│         │                  │                                      │
│         │ route_after_     │                                      │
│         │ conversation()   │                                      │
│         │                  │                                      │
│    ┌────┴────┐        ┌───┴────┐                                 │
│    │         │        │        │                                 │
│    ▼         ▼        ▼        │                                 │
│ ┌───────┐ ┌───────────┐   │                                 │
│ │ END   │ │ tool_node │   │                                 │
│ └───────┘ └─────┬─────┘   │                                 │
│                   │         │                                 │
│                   │ tool_   │                                 │
│                   │ node_   │                                 │
│                   │ router()│                                 │
│                   │         │                                 │
│          ┌────────┴────────┐                                 │
│          │                 │                                 │
│          ▼                 ▼                                 │
│     ┌─────────┐       ┌─────────┐                            │
│     │conversation│       │   END   │  有待确认时暂停等待用户 │
│     │   _llm    │       └─────────┘                            │
│     └─────────┘                                                 │
│                                                                 │
└───────────────────────────────────────────────────────────────────┘
```

### 工作流说明

#### 1. 入口路由 (entry_router)
- 检查最后一条消息是否是 `[CONFIRM_REPLY:]`（用户点击了确认/取消按钮）
- 如果是确认回复 → 直接进入 `tool_node`
- 否则 → 进入 `conversation_llm`

#### 2. conversation_llm 节点
- 处理用户对话，生成 AI 回复
- 可以调用工具 `save_resume_tool`（保存简历）
- 返回后通过 `route_after_conversation()` 路由

#### 3. route_after_conversation 路由
- 有 tool_calls → 进入 `tool_node`
- 无 tool_calls → END

#### 4. tool_node 节点
- 执行工具调用（如 `save_resume_tool`）
- 特殊逻辑：调用 `save_resume_tool` 时不立即保存，而是生成 `pending_confirmation` 触发前端确认框
- 处理用户确认回复（`[CONFIRM_REPLY:]`）
- 返回后通过 `tool_node_router()` 路由

#### 5. tool_node_router 路由
- 有 `pending_confirmation`（有待确认）→ END（暂停，等待用户在前端操作）
- 无 pending_confirmation → 进入 `conversation_llm` 生成结束语

---

## 🚀 快速开始

> Windows 本机运行请优先参考 [本地部署说明](docs/local-deployment.md)；需要测试注册、登录和用户隔离时，参考 [本机多用户部署](docs/multi-user-local.md)。默认本地版使用项目专用 Python 虚拟环境、SQLite 和 Chrome/Edge，不依赖 Docker 或数据库服务。

### 环境要求

- Python 3.11+
- Node.js 20+
- Chrome、Edge 或 Chromium（PDF 导出必需；可通过 `RESUME_PDF_BROWSER` 指定路径）

### 1. 克隆项目

```bash
git clone <repository-url>
cd DeepAgents
```

### 2. 配置环境变量

复制示例文件并编辑：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# 本地单用户模式（免登录）
APP_MODE=local
LOCAL_USER_EMAIL=local@localhost
DATABASE_URL=sqlite:///./data/deepagents.db
LOCAL_EXPORT_DIR=./output/resumes
HOST=127.0.0.1

# LLM API 配置
LLM_API_KEY=your-api-key
BASE_URL=https://api.bltcy.ai/v1

# Tavily 搜索 API（可选）

```

需要登录、注册、邀请码和多用户隔离时，不要修改本地 `.env` 或本地启动脚本；复制 `.env.multi_user.example`，配置本机 MySQL 后使用 `scripts\start_multi_user.cmd`。详见 [本机多用户部署](docs/multi-user-local.md)。

### 3. 安装依赖

安装后端和前端依赖：

```bash
# 创建虚拟环境
python -m venv .venv-win
# .venv-win\Scripts\activate  # Windows

# 安装后端依赖
.venv-win\Scripts\pip install -r backend/requirements.txt

# 安装前端依赖
cd frontend
npm install
cd ..
```

### 4. 初始化数据库

SQLite 文件和表会在本地后端首次运行时自动创建，无需初始化命令。本机多用户模式需要提前在 MySQL 中创建业务数据库和应用账号，具体 SQL 见 [本机多用户部署](docs/multi-user-local.md)。Docker Compose 模式会自动启动 MySQL 容器并创建业务表。

### 5. 启动服务

**方式一：Windows 本地一键启动（推荐）**

```cmd
# 启动本地 SQLite 后端 + 前端
scripts\start_local.cmd

# 默认无交互连续启动；仅需让最终结果停留时使用
scripts\start_local.cmd --pause

# 分别启动（运行日志写入 .local-run）
scripts\start_backend_local.cmd
scripts\start_frontend.cmd

# 后端脚本会自动判断：未运行则启动，已运行则重启
scripts\start_backend_local.cmd

# 一键脚本同样会重启已运行的后端并检查前后端
scripts\start_local.cmd

# 停止
scripts\stop_app.cmd
```

**方式二：Windows 本机多用户 MySQL**

```cmd
# 首次使用前：完成 MySQL 数据库/应用账号配置，并编辑 .env.multi_user

# 启动 MySQL、MySQL 后端和共用前端
scripts\start_multi_user.cmd

# 停止前端和后端，保留 MySQL 服务
scripts\stop_app.cmd

# 确认不再使用 MySQL 时再单独停止服务
scripts\stop_mysql.cmd
```

多用户启动器会先检查 MySQL 连接，检查通过后才重启后端；共用前端已经运行时会继续复用 Vite 进程。详细说明见 [本机多用户部署](docs/multi-user-local.md)。

**方式三：手动启动（跨平台开发环境）**

```bash
# 终端 1 - 启动后端
source .venv/bin/activate  # macOS/Linux
python -m backend.main

# 终端 2 - 启动前端
cd frontend
npm run dev
```

**方式四：Docker 多人自托管（可选服务器部署）**

```bash
cp .env.docker.example .env.docker
# 修改 JWT、管理员和 MySQL 密码后：
docker compose --env-file .env.docker -f docker-compose.multi-user.yml up -d --build
```

### 6. 访问应用

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- 健康检查：http://localhost:8000/health
- Docker 多用户版前端：http://localhost:8080

---

## 📁 项目结构

```
resume_assistant/
├── backend/                           # FastAPI / LangGraph Python 包
│   ├── main.py                        # FastAPI 入口
│   ├── resume_agent.py                # LangGraph Agent
│   ├── database.py                    # SQLAlchemy 模型与数据访问
│   ├── auth.py                        # JWT 认证
│   ├── tools.py                       # Agent 工具
│   ├── pdf_generator.py               # PDF 内容与排版生成入口
│   ├── pdf_renderer.py                # Chromium 浏览器发现与 PDF 打印
│   ├── create_admin.py                # 管理员初始化模块
│   ├── requirements.txt
│   ├── requirements.lock.txt
│   └── Dockerfile
├── frontend/                          # Vue 3 / Vite 前端
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── Dockerfile
│   └── nginx.conf
├── docs/                              # 部署、测试、架构和 Prompt 文档
│   ├── architecture/
│   ├── prompts/
│   ├── deployment.md
│   ├── local-deployment.md
│   └── testing.md
├── scripts/                           # Windows 本地启动、停止与冒烟测试
├── nginx/                             # Docker Nginx 配置
├── data/                              # 本地 SQLite、上传原件与工作流数据
├── output/resumes/                    # 本地导出目录（运行时生成）
├── docker-compose.yml                 # 旧部署入口（兼容保留）
├── docker-compose.multi-user.yml      # 多人 MySQL 自托管入口
├── .env.example                       # 本地配置模板
├── .env.multi_user.example            # 多人配置模板
├── .env.docker.example                 # Docker 多人配置模板
└── README.md
```

---

## 🔌 API 接口

### 认证接口

| 端点 | 方法 | 功能 |
|------|------|------|
| `/auth/register` | POST | 用户注册 |
| `/auth/login` | POST | 用户登录 |
| `/auth/me` | GET | 获取当前用户信息 |

### 聊天接口

| 端点 | 方法 | 功能 |
|------|------|------|
| `/chat` | POST | SSE 流式对话 |
| `/confirm` | POST | 处理确认操作 |

### 对话管理接口

| 端点 | 方法 | 功能 |
|------|------|------|
| `/save_conversation` | POST | 保存对话历史 |
| `/load_conversation` | POST | 加载对话历史 |

### 简历接口

| 端点 | 方法 | 功能 |
|------|------|------|
| `/projects` | GET / POST | 列出或创建简历项目 |
| `/projects/{project_id}` | GET | 获取项目及任务列表 |
| `/projects/{project_id}/tasks` | POST | 从基础简历创建 JD 任务 |
| `/tasks/{task_id}` | GET | 获取任务摘要 |
| `/load_resume` | POST | 加载简历数据 |
| `/save_resume` | POST | 保存简历数据 |
| `/translate_resume` | POST | 将当前中文简历结构化翻译为英文，并复用字段级翻译缓存 |
| `/restore_resume_translation` | POST | 恢复当前任务持久化的中文翻译基线 |
| `/api/resume/parse_and_save` | POST | 上传并解析简历文件 |
| `/api/resume/parsing_status` | GET | 获取解析状态 |

工作区接口通过 `X-Task-ID` 请求头确定当前任务。基础任务的修改会更新项目
基础简历；JD 任务的修改只保存在该任务版本中。

### JD 接口

| 端点 | 方法 | 功能 |
|------|------|------|
| `/load_jd` | POST | 加载 JD 数据 |
| `/save_jd` | POST | 保存 JD 数据 |
| `/parse_jd` | POST | 解析 JD（文本/图片） |

### 导出接口

| 端点 | 方法 | 功能 |
|------|------|------|
| `/export_pdf` | POST | 导出 PDF |
| `/export_docx` | POST | 导出可编辑 DOCX |
| `/local/exports/open` | POST | 打开本地导出目录（仅本地模式） |

### 管理接口

| 端点 | 方法 | 功能 |
|------|------|------|
| `/auth/invite-codes` | GET | 获取邀请码列表 |
| `/auth/invite-codes` | POST | 创建邀请码 |

### 健康检查

| 端点 | 方法 | 功能 |
|------|------|------|
| `/health` | POST | 健康检查 |

---

## 🚢 部署指南

详细部署文档请参考 [部署指南](docs/deployment.md)。

### Docker Compose 多人自托管

```bash
# 1. 配置多人环境
cp .env.docker.example .env.docker
# 编辑 .env.docker 中的 JWT、管理员和 MySQL 密码

# 2. 构建并启动
docker compose --env-file .env.docker -f docker-compose.multi-user.yml up -d --build

# 3. 查看日志
docker compose --env-file .env.docker -f docker-compose.multi-user.yml logs -f

# 4. 停止服务（保留数据卷）
docker compose --env-file .env.docker -f docker-compose.multi-user.yml down
```

该配置适用于受控自托管环境；开放公网前仍需补充 HTTPS、限流、审计和备份运维。不要使用 `down -v` 停止已有数据的环境。

### Nginx 配置

项目包含完整的 Nginx 配置，支持：
- 静态文件服务
- API 反向代理
- Gzip 压缩
- SSL/TLS 支持
- Vue Router History 模式

---

## 💻 开发说明

### 数据模型

#### 简历数据结构

```python
{
  "basics": {
    "name": "姓名",
    "gender": "男/女/保密",
    "phone": "手机号",
    "email": "邮箱",
    "target_position": "期望岗位",
    "photo": "base64图片"
  },
  "education": [{
    "school_name": "学校",
    "major": "专业",
    "degree": "学历",
    "date_range": ["2020.09", "2025.06"],
    "school_tags": ["标签1", "标签2"],
    "theses": []
  }],
  "work_experience": [{
    "company_name": "公司",
    "job_title": "职位",
    "date_range": ["2024.07", "至今"],
    "job_type": "全职/实习",
    "details": ["工作内容1", "工作内容2"]
  }],
  "project_experience": [{
    "project_name": "项目名称",
    "role": "角色",
    "date_range": ["开始时间", "结束时间"],
    "details": ["项目内容1", "项目内容2"]
  }],
  "others": {
    "skills": ["技能1", "技能2"],
    "certificates": ["证书"],
    "languages": ["语言"]
  },
  "self_evaluation": ["自我评价"]
}
```

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + B` | 加粗选中文本 |
| `Ctrl + Enter` | 发送消息（全屏输入框） |

### 环境变量

本地配置参考 `.env.example`；多人配置参考 `.env.multi_user.example`。

### 创建管理员

仅 `APP_MODE=multi_user` 时需要：

```bash
python -m backend.create_admin
```

管理员登录标识和密码必须通过对应环境文件中的 `ADMIN_EMAIL`、`ADMIN_PASSWORD` 设置。为兼容既有配置仍沿用变量名 `ADMIN_EMAIL`；管理员标识可以是邮箱或专用账号名，普通用户注册和登录必须使用邮箱。

本机多用户启动器读取 `.env.multi_user`。
Docker Compose 读取 `.env.docker`；两者都会创建或升级该账号为管理员。

---

## 📚 相关文档

- [本地部署说明](docs/local-deployment.md) - Windows 本地部署与启动说明
- [本机多用户部署](docs/multi-user-local.md) - Windows 原生 MySQL + JWT 多用户启动说明
- [Docker 多人自托管部署](docs/deployment.md) - Linux 服务器上的 JWT + MySQL + Docker Compose
- [测试清单](docs/testing.md) - 功能回归检查项

---

## 📄 License

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
