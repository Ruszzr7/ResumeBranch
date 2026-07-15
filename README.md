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
- **用户认证**：JWT 令牌认证，支持多用户隔离
- **数据持久化**：SQLite 数据库存储用户简历、JD 和对话历史
- **AI 驱动**：基于 LangGraph 构建的智能 Agent
- **PDF 导出**：服务端 WeasyPrint 生成高质量 PDF

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
| html2pdf.js | 0.12.1 | 客户端 PDF 导出（备用） |

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.104+ | HTTP API 框架 |
| Uvicorn | 0.24+ | ASGI 服务器 |
| Gunicorn | 21+ | WSGI 服务器（生产环境） |
| SQLAlchemy | 2.0+ | ORM |
| LangGraph | 1.0+ | AI Agent 工作流 |
| LangChain | 1.1+ | LLM 集成 |
| WeasyPrint | 60+ | 服务端 PDF 生成 |
| python-jose | 3.3+ | JWT 认证 |
| bcrypt | 4.0+ | 密码加密 |

> **注意**：默认使用 `gemini-3-flash-preview` 模型，需通过兼容的 LLM API（如 Google AI Studio 或自定义 BASE_URL）使用。

---

## ✨ 核心功能

### 用户系统
- ✅ 用户注册（邀请码机制）
- ✅ 用户登录/登出
- ✅ JWT Token 认证（24 小时有效期）
- ✅ 管理员后台（管理邀请码）
- ✅ 多用户数据隔离

### 简历编辑
- ✅ 对话式 AI 优化简历
- ✅ 表单式编辑（基本信息、教育、工作、项目）
- ✅ 富文本编辑（Ctrl+B 加粗）
- ✅ 日期选择器（支持"至今"）
- ✅ 照片上传（Base64）
- ✅ 实时预览（A4 分页）
- ✅ 样式调节（页边距、字体大小等）

### JD 匹配
- ✅ JD 文本粘贴
- ✅ JD 图片 OCR 识别
- ✅ 表单式 JD 编辑
- ✅ 智能解析和结构化

### 导出功能
- ✅ 服务端 WeasyPrint PDF 导出（推荐）
- ✅ 客户端 html2pdf.js 导出（备用）

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

> Windows 本机运行请优先参考 [LOCAL_DEPLOYMENT.md](LOCAL_DEPLOYMENT.md)。该方案使用
> 项目专用 Python 虚拟环境、本机 MySQL 8.4 和隔离的 WeasyPrint/Pango，不依赖 Docker。

### 环境要求

- Python 3.11+
- Node.js 20+
- macOS: brew install pango harfbuzz cairo fontconfig (WeasyPrint 依赖)

### 1. 克隆项目

```bash
git clone <repository-url>
cd DeepAgents
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# JWT 配置（必须修改）
JWT_SECRET_KEY=your-super-secret-jwt-key-here

# LLM API 配置
LLM_API_KEY=your-api-key
BASE_URL=https://api.bltcy.ai/v1

# Tavily 搜索 API（可选）
TAVILY_API_KEY=tvly-your-tavily-api-key

# 服务器配置
DOMAIN=your-domain.com

# 数据库（可选，默认使用 SQLite）
DATABASE_URL=sqlite:///./data/deepagents.db
```

### 3. 安装后端依赖

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 4. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 5. 初始化数据库

```bash
# 数据库会在首次运行时自动创建
# 如需创建管理员账号
python create_admin.py
```

### 6. 启动服务

**方式一：手动启动（开发环境）**

```bash
# 终端 1 - 启动后端
source .venv/bin/activate
python mcp_service_simple.py

# 终端 2 - 启动前端
cd frontend
npm run dev
```

**方式二：使用启动脚本**

```bash
# 后端
./start_backend.sh

# 前端（另一个终端）
cd frontend && npm run dev
```

**方式三：Docker 部署（推荐生产环境）**

```bash
docker-compose up -d --build
```

### 7. 访问应用

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- 健康检查：http://localhost:8000/health

---

## 📁 项目结构

```
DeepAgents/
├── frontend/                          # Vue3 前端项目
│   ├── src/
│   │   ├── components/               # 组件
│   │   │   ├── ChatMessage.vue      # 聊天消息
│   │   │   ├── ResumePreview.vue    # 简历预览
│   │   │   ├── RichTextEditor.vue   # 富文本编辑器
│   │   │   ├── BoldTextarea.vue     # 加粗文本域
│   │   │   └── MobileTabBar.vue     # 移动端导航
│   │   ├── views/                   # 页面
│   │   │   ├── Homepage.vue         # 首页
│   │   │   ├── Login.vue            # 登录
│   │   │   ├── Register.vue         # 注册
│   │   │   └── Admin.vue            # 管理员后台
│   │   ├── router/
│   │   └── index.js             # 路由配置
│   ├── App.vue                  # 主应用
│   ├── main.js                  # 入口
│   ├── api.js                   # API 请求封装
│   └── style.css                # 全局样式
│   ├── package.json
│   ├── vite.config.js
│   ├── Dockerfile
│   └── nginx.conf
│
├── data/                              # 数据目录
│   └── deepagents.db                 # SQLite 数据库
│
├── nginx/                             # Nginx 配置
│   ├── nginx.conf
│   └── conf.d/
│
├── mcp_service_simple.py              # FastAPI 服务入口
├── resume_agent.py                    # LangGraph AI Agent 核心
├── tools.py                           # 工具函数
├── pdf_generator.py                   # PDF 生成器
├── database.py                        # 数据库模型
├── auth.py                            # JWT 认证
├── create_admin.py                    # 管理员创建脚本
├── requirements.txt                   # Python 依赖
├── .env                               # 环境变量
├── .env.example                       # 环境变量模板
├── docker-compose.yml                 # Docker Compose 配置
├── Dockerfile                         # 后端 Dockerfile
├── start_backend.sh                   # 后端启动脚本
├── DEPLOYMENT.md                      # 部署指南
├── RESUME_AGENT_ARCHITECTURE.md      # Agent 架构文档
└── README.md                          # 本文件
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
| `/load_resume` | POST | 加载简历数据 |
| `/save_resume` | POST | 保存简历数据 |
| `/api/resume/parse_and_save` | POST | 上传并解析简历文件 |
| `/api/resume/parsing_status` | GET | 获取解析状态 |

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

详细部署文档请参考 [DEPLOYMENT.md](./DEPLOYMENT.md)。

### Docker Compose 快速部署

```bash
# 1. 配置 .env
cp .env.example .env
# 编辑 .env 文件

# 2. 构建并启动
docker-compose up -d --build

# 3. 查看日志
docker-compose logs -f

# 4. 停止服务
docker-compose down
```

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

完整的环境变量配置参考 `.env.example`。

### 创建管理员

```bash
python create_admin.py
```

默认管理员账号：
- 邮箱：admin@qq.com
- 密码：admin123

---

## 📚 相关文档

- [RESUME_AGENT_ARCHITECTURE.md](./RESUME_AGENT_ARCHITECTURE.md) - LangGraph Agent 详细架构文档
- [DEPLOYMENT.md](./DEPLOYMENT.md) - 完整部署指南

---

## 📄 License

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
