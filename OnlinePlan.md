# DeepAgents 多用户上线改造计划

## 一、改造目标

将目前本地单用户运行的简历助手，改造为支持多用户、有用户认证、数据持久化的生产级应用。

### 技术选型

| 组件 | 方案 | 原因 |
|------|------|------|
| 数据库 | SQLite | 轻量、单文件、零运维，100-1000用户完全够用 |
| 认证 | JWT Token | 无状态、可扩展，无需 session 服务 |
| 注册 | 邀请码 | 前期无需 Redis 和邮件服务器，控制用户增长 |
| 并发 | FastAPI 异步 + workers | I/O 并发能力强，无需 Celery |
| 数据存储 | 混合模式 | 用户数据存 SQLite，简历/JD/对话存 JSON 文件 |

---

## 二、架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                       阿里云 ECS                                 │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Docker 容器 (单容器)                         │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │               FastAPI (8000)                     │   │   │
│  │  │  ├── REST API (认证、简历、JD、对话)             │   │   │
│  │  │  └── SSE 流式响应 (聊天)                         │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  │                              │                            │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │         data/ (数据目录，挂载到主机)             │   │   │
│  │  │  ├── deepagents.db          (SQLite: 用户/邀请码)│   │   │
│  │  │  └── users/{user_id}/       (JSON: 简历/JD/对话) │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 为什么不需要 Celery？

| 场景 | FastAPI 异步 | Celery |
|------|-------------|--------|
| 聊天对话 | SSE 流式，用户实时看到输出 | 不适合（用户体验差）|
| 并发能力 | asyncio 事件循环，I/O 并发强 | 过度设计 |
| 复杂度 | 单服务简单 | 增加运维复杂度 |

**结论**：FastAPI 异步架构 + `--workers 4` 多进程已能支撑 100-1000 用户。

---

## 三、数据存储设计

### 3.1 SQLite 数据库（用户系统）

```
data/
  deepagents.db
    └── users 表
        - id
        - email (唯一)
        - hashed_password
        - invite_code
        - created_at
        - is_active

    └── invite_codes 表
        - code (主键)
        - is_used
        - created_at
```

### 3.2 JSON 文件（用户数据）

```
data/
  users/
    user_1/
      resume.json        # 用户简历
      jd.json            # 用户保存的JD列表
      conversations/
        session_abc/
          messages.json  # 对话历史
```

---

## 四、数据库设计 (SQLite)

### 4.1 数据模型

```python
# database.py

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/deepagents.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    """用户表"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    invite_code = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class InviteCode(Base):
    """邀请码表"""
    __tablename__ = "invite_codes"
    code = Column(String(50), primary_key=True)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Resume(Base):
    """简历数据表"""
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(100), default="默认简历")
    resume_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class JobDescription(Base):
    """JD数据表"""
    __tablename__ = "job_descriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    company = Column(String(100), default="")
    position = Column(String(100), default="")
    jd_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Conversation(Base):
    """对话历史表"""
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String(36), nullable=False)
    messages = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
```

### 4.2 数据存储目录

```
data/
  deepagents.db          # SQLite（User, InviteCode, Resume, JD, Conversation）
  users/                 # JSON 文件备份（可选）
    {user_id}/
      resume.json        # 简历备份
      jd.json            # JD备份
      conversations/     # 对话备份
        {session_id}.json
```

---

## 五、认证系统

### 5.1 JWT 工具函数

```python
# auth.py

from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24小时

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=401, detail="认证失败", headers={"WWW-Authenticate": "Bearer"}
    )
    payload = decode_token(token)
    if not payload:
        raise credentials_exception
    email = payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise credentials_exception
    return user
```

### 5.2 认证接口

| 端点 | 方法 | 说明 | 需要认证 |
|------|------|------|----------|
| `/auth/register` | POST | 邮箱+密码+邀请码注册 | ❌ |
| `/auth/login` | POST | 登录返回 JWT Token | ❌ |
| `/auth/me` | GET | 获取当前用户信息 | ✅ |
| `/auth/invite-codes` | POST | 生成邀请码（管理员） | ✅ |

### 5.3 需要改造的业务接口

| 端点 | 当前行为 | 改造后行为 | 需要认证 |
|------|----------|----------|----------|
| `/load_resume` | 读 `resume.json` | 从 SQLite 读取用户简历 | ✅ |
| `/save_resume` | 写 `resume.json` | 写入 SQLite 用户简历 | ✅ |
| `/load_jd` | 读 `jd.json` | 从 SQLite 读取用户JD | ✅ |
| `/save_jd` | 写 `jd.json` | 写入 SQLite 用户JD | ✅ |
| `/parse_jd` | 解析JD（无用户关联） | 解析后存入用户JD | ✅ |
| `/chat` | 无用户认证 | JWT认证 + 用户数据隔离 | ✅ |
| `/export_pdf` | 直接接收resume_data | 从用户SQLite读取 | ✅ |

### 5.4 需要移除的全局状态

| 变量 | 问题 | 改造方案 |
|------|------|----------|
| `resume_data_cache` | 单用户内存缓存 | 移除，改用 SQLite |
| `jd_data_cache` | 单用户内存缓存 | 移除，改用 SQLite |

---

## 六、聊天上下文持久化

**不需要改造 LangGraph 核心代码**，在应用层拦截：

```python
# mcp_service_simple.py

# 调用 graph 前：从数据库加载历史
messages = load_conversation_history(user_id, session_id)

# 调用 graph 时：把历史传进去
result = graph.invoke({
    "messages": messages,
    "input": user_message
})

# 调用 graph 后：保存新消息到数据库
save_conversation_history(user_id, session_id, new_messages)
```

### 数据结构

```python
# conversations 表
{
    "id": 1,
    "user_id": "user_abc123",
    "session_id": "session_1",
    "role": "user",      # 或 "assistant"
    "content": "帮我优化简历",
    "created_at": "2026-01-11 10:00:00"
}
```

---

## 七、改造文件清单

### 7.1 新建文件

| 文件 | 说明 |
|------|------|
| `database.py` | SQLite 连接和 5 个 SQLAlchemy 模型（User, InviteCode, Resume, JobDescription, Conversation） |
| `auth.py` | JWT 工具函数、密码加密 |
| `Dockerfile` | Docker 镜像构建 |
| `docker-compose.yml` | Docker 服务编排 |
| `frontend/src/views/Login.vue` | 登录页 |
| `frontend/src/views/Register.vue` | 注册页 |

### 7.2 改造文件

| 文件 | 改造内容 |
|------|----------|
| `tools.py` | read_file/write_file/update_resume/load_resume 改为数据库操作 |
| `resume_agent.py` | 工具函数逻辑改造、MemorySaver 改为 SQLite Checkpointer |
| `mcp_service_simple.py` | 全部 API 端点添加认证、全局缓存移除、数据读写改 SQLite |
| `frontend/src/App.vue` | 添加 token 状态、请求拦截器、认证守卫 |
| `.env` | 新增 JWT_SECRET_KEY、DATABASE_URL |

### 7.3 需要移除的代码

| 位置 | 代码 | 原因 |
|------|------|------|
| `mcp_service_simple.py:65-68` | `resume_data_cache`, `jd_data_cache` | 单用户内存缓存，改为 SQLite |
| `mcp_service_simple.py:169-179` | `/load_resume` 读文件 | 改为读 SQLite |
| `mcp_service_simple.py:182-193` | `/load_jd` 读文件 | 改为读 SQLite |
| `mcp_service_simple.py:255-296` | `/save_jd` 写文件+checkpoint | 改为写 SQLite |
| `mcp_service_simple.py:565-580` | `/save_resume` 写文件 | 改为写 SQLite |

### 7.4 API 端点改造清单

| 端点 | 改造内容 |
|------|----------|
| `/auth/register` | **新建**（邮箱+密码+邀请码） |
| `/auth/login` | **新建**（返回 JWT） |
| `/auth/me` | **新建**（获取用户信息） |
| `/load_resume` | 添加认证，从 SQLite 读取 |
| `/save_resume` | 添加认证，写入 SQLite |
| `/load_jd` | 添加认证，从 SQLite 读取 |
| `/save_jd` | 添加认证，写入 SQLite |
| `/parse_jd` | 添加认证，解析后存入用户JD |
| `/chat` | 添加认证，用户数据隔离 |
| `/export_pdf` | 添加认证，从用户 SQLite 读取 |

---

## 八、详细实现步骤

### Phase 1：创建数据库和认证模块

**新建 `database.py`：**
- SQLite 连接配置
- User、InviteCode、Resume、JobDescription、Conversation 模型
- get_db 依赖函数
- init_db 初始化函数

**新建 `auth.py`：**
- 密码加密（bcrypt）
- JWT Token 创建/验证
- get_current_user 依赖

**新增数据访问函数：**
```python
# database.py 或新建 storage.py

def get_user_resume(user_id: int, db: Session) -> dict:
    """获取用户简历"""
    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    return resume.resume_data if resume else {}

def save_user_resume(user_id: int, data: dict, db: Session):
    """保存用户简历"""
    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    if resume:
        resume.resume_data = data
    else:
        resume = Resume(user_id=user_id, resume_data=data, name="默认简历")
        db.add(resume)
    db.commit()

def get_user_jd(user_id: int, db: Session) -> dict:
    """获取用户JD"""
    jd = db.query(JobDescription).filter(JobDescription.user_id == user_id).first()
    return jd.jd_data if jd else {}

def save_user_jd(user_id: int, data: dict, db: Session):
    """保存用户JD"""
    jd = db.query(JobDescription).filter(JobDescription.user_id == user_id).first()
    if jd:
        jd.jd_data = data
    else:
        jd = JobDescription(user_id=user_id, jd_data=data)
        db.add(jd)
    db.commit()

def save_conversation(user_id: int, session_id: str, messages: list, db: Session):
    """保存对话历史"""
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    if conv:
        conv.messages = messages
    else:
        conv = Conversation(user_id=user_id, session_id=session_id, messages=messages)
        db.add(conv)
    db.commit()
```

### Phase 2：改造 tools.py（数据访问层）

**改造 `tools.py` - 所有文件操作改为数据库操作：**

| 函数 | 改造前 | 改造后 |
|------|--------|--------|
| `read_file()` | 直接读文件 | **移除或标记废弃**（不再使用） |
| `write_file()` | 直接写文件 | **移除或标记废弃**（不再使用） |
| `update_resume()` | 写 `resume.json` | 写入 SQLite 的 `resumes` 表 |
| `load_resume()` | 读 `resume.json` | 从 SQLite 的 `resumes` 表读取 |

**核心改造：**
```python
# tools.py

def update_resume(data: dict) -> str:
    """更新用户简历到 SQLite"""
    from database import get_db, Resume
    db = next(get_db())
    try:
        resume = db.query(Resume).filter(Resume.user_id == current_user_id).first()
        if resume:
            resume.resume_data = data
        else:
            resume = Resume(user_id=current_user_id, resume_data=data, name="默认简历")
            db.add(resume)
        db.commit()
        return "简历已成功保存"
    except Exception as e:
        return f"保存失败：{str(e)}"
    finally:
        db.close()

def load_resume() -> dict:
    """从 SQLite 加载用户简历"""
    from database import get_db, Resume
    db = next(get_db())
    try:
        resume = db.query(Resume).filter(Resume.user_id == current_user_id).first()
        return resume.resume_data if resume else {}
    except Exception as e:
        return {"error": f"加载失败：{str(e)}"}
    finally:
        db.close()
```

### Phase 3：改造 resume_agent.py

**3.1 工具函数改造：**

| 位置 | 改造前 | 改造后 | 原因 |
|------|--------|--------|------|
| 第342-345行 | `read_file_tool` 调用 `read_file()` | **不再调用文件函数**，优先使用 `state.resume_data`，如无数据返回提示 | 多用户下无法确定文件路径 |
| 第348-372行 | `write_file_tool` 调用 `write_file()` | 改为调用新的 `update_resume()` 写入 SQLite | 数据持久化到数据库 |
| 第776-777行 | `MemorySaver()` | `SqliteSaver.from_conn_string(DATABASE_URL)` | 对话状态持久化 |

**3.2 read_file_tool 改造示例：**
```python
@tool
def read_file_tool(file_path: str = "resume.json") -> str:
    """
    读取简历数据

    注意：此工具不再直接读取文件。简历数据应从 state.resume_data 获取。
    如果 state.resume_data 为空，说明尚未加载简历。
    """
    # 直接返回提示，数据应从 state 获取
    return "简历数据需要从当前会话状态中获取。如需重新加载，请联系系统支持。"
```

**3.3 write_file_tool 改造示例：**
```python
@tool
def write_file_tool(file_path: str = "resume.json", content: str = "") -> str:
    """
    写入 JSON 内容到用户简历

    Args:
        file_path: 文件路径（忽略，实际写入数据库）
        content: JSON 格式的内容
    """
    import re
    from tools import update_resume

    # 清理 markdown 代码块标记
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    content = content.strip()

    # 提取 JSON 对象
    if not content.startswith('{'):
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            content = match.group()

    # 解析并保存到数据库
    try:
        resume_data = json.loads(content)
        result = update_resume(resume_data)
        return result
    except json.JSONDecodeError:
        return "保存失败：JSON 格式错误"
```

**3.4 工具列表更新：**
```python
# 改造后 - 工具不再依赖文件操作
conversation_tools = [read_file_tool, signal_formatter_tool]
formatter_tools = [write_file_tool]
```

**3.5 Checkpointer 改造：**
```python
# 改造前
from langgraph.checkpoint.memory import MemorySaver
memory = MemorySaver()
graph = graph_builder.compile(checkpointer=memory)

# 改造后
import os
from langgraph.checkpoint.sqlite import SqliteSaver

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/deepagents.db")
checkpointer = SqliteSaver.from_conn_string(DATABASE_URL)
graph = graph_builder.compile(checkpointer=checkpointer)
```

### Phase 4：改造后端 API

**改造 `mcp_service_simple.py`：**

1. 新增认证端点：
   - `POST /auth/register` - 注册（邮箱+密码+邀请码）
   - `POST /auth/login` - 登录
   - `GET /auth/me` - 获取用户信息

2. 改造现有端点：
   - `/chat` - 添加认证依赖，从 SQLite 加载 resume_data/jd_data 放入 state
   - `/load_resume` - 从 SQLite 的 resumes 表读取
   - `/save_resume` - 写入 SQLite 的 resumes 表

3. 新增对话历史接口：
   - `GET /conversations` - 获取用户对话列表
   - `GET /conversations/{session_id}` - 获取单条对话

4. **数据加载逻辑：**
```python
# /chat 接口调用 graph 前
user = get_current_user(token, db)
resume_data = load_resume_from_db(user.id, db)
jd_data = load_jd_from_db(user.id, db)

# 放入初始 state
initial_state = {
    "messages": [HumanMessage(content=user_message)],
    "resume_data": resume_data or {},
    "jd_data": jd_data or {}
}

# graph 执行后保存
if final_resume_data:
    save_resume_to_db(user.id, final_resume_data, db)
```

### Phase 5：前端改造

**新建 `frontend/src/views/Login.vue`：**
- 登录表单（邮箱+密码）
- 调用登录 API
- 存储 token

**新建 `frontend/src/views/Register.vue`：**
- 注册表单（邮箱+密码+邀请码）
- 调用注册 API

**改造 `frontend/src/App.vue`：**
- 添加 token 状态管理
- 添加请求拦截器（Authorization Header）
- 未登录时跳转到登录页

### Phase 6：Docker 部署

**新建 `Dockerfile`：**
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p data/users

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "mcp_service_simple:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**新建 `docker-compose.yml`：**
```yaml
version: '3.8'

services:
  backend:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite:///./data/deepagents.db
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    restart: unless-stopped
```

**新建 `requirements.txt`：**
```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
sqlalchemy>=2.0.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.6
pydantic>=2.5.0
python-dotenv>=1.0.0
# LangGraph 相关
langgraph>=0.0.20
langchain-openai>=0.1.0
# PDF 生成
weasyprint>=60.0
```

---

## 九、环境变量配置

```bash
# .env

# JWT 认证（必填）
JWT_SECRET_KEY=your-super-secret-key-change-this-in-production

# 数据库
DATABASE_URL=sqlite:///./data/deepagents.db

# LLM
LLM_API_KEY=sk-your-api-key
BASE_URL=https://api.bltcy.ai/v1

# TAVILY
TAVILY_API_KEY=tvly-your-api-key

# 服务器
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

---

## 十、启动命令

```bash
# 开发环境
uvicorn mcp_service_simple:app --host 0.0.0.0 --port 8000 --reload

# 生产环境（Docker）
docker-compose up -d --build

# 或直接运行（单服务器）
python -m uvicorn mcp_service_simple:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 十一、目录结构

```
DeepAgents/
├── mcp_service_simple.py      # 主入口（改造）
├── resume_agent.py            # AI Agent（不改）
├── tools.py                   # 工具函数（不改）
├── pdf_generator.py           # PDF 生成（不改）
├── database.py                # 新建：数据库层
├── auth.py                    # 新建：认证模块
├── Dockerfile                 # 新建：Docker 构建
├── docker-compose.yml         # 新建：Docker 编排
├── requirements.txt           # 新建：依赖清单
├── .env                       # 新增：环境变量
│
├── data/                      # 数据目录（挂载）
│   ├── deepagents.db          # SQLite（自动创建）
│   └── users/
│       └── {user_id}/
│           ├── resume.json
│           ├── jd.json
│           └── conversations/
│               └── {session_id}.json
│
└── frontend/
    └── src/
        ├── App.vue            # 改造：认证逻辑
        ├── views/
        │   ├── Login.vue      # 新建
        │   └── Register.vue   # 新建
        └── router/
            └── index.js       # 新建：路由守卫
```

---

## 十二、工作量评估

| 阶段 | 工作量 | 说明 |
|------|--------|------|
| Phase 1 | 1.5天 | database.py（5个模型+数据访问函数）, auth.py |
| Phase 2 | 0.5天 | tools.py 改造 |
| Phase 3 | 1天 | resume_agent.py 改造（工具函数 + Checkpointer） |
| Phase 4 | 2-3天 | mcp_service_simple.py（7个接口改造+移除全局缓存） |
| Phase 5 | 1-2天 | Login.vue, Register.vue, App.vue |
| Phase 6 | 0.5天 | Dockerfile, docker-compose.yml |
| **总计** | **6.5-9天** | - |

---

## 十三、关键问题解答

### Q: Redis 邮箱验证是否前期不需要？
A: 是的。邀请码机制不需要 Redis，SQLite 足够存储邀请码。

### Q: 为什么不用 Celery？
A: FastAPI 异步 + 多进程 workers 已能应对 100-1000 用户。Celery 适合"提交后等待"场景，但聊天需要实时 SSE 流式输出。

### Q: 之前的 MySQL + Redis + Celery 架构是否过度设计？
A: 是的。对于简历助手这种轻量级应用：
- MySQL 需要独立服务，运维复杂
- Redis 需要额外内存
- Celery 增加架构复杂度

### Q: LangGraph 代码需要改吗？
A: **部分需要**。具体改造：
- `resume_agent.py` 的 `MemorySaver` → `SqliteSaver`（用于对话历史持久化）
- `tools.py` 的 `read_file`/`write_file` → 改为数据库操作
- `resume_agent.py` 的 `read_file_tool`/`write_file_tool` → 调整逻辑，优先使用 state 数据

### Q: 改造后数据存储在哪里？
A: **混合模式**：
- 用户账号、邀请码 → `deepagents.db`（SQLite）
- 简历数据、JD 数据、对话历史 → `deepagents.db` + JSON 文件（按用户隔离）
- 对话状态（LangGraph checkpoint）→ `SqliteSaver`（自动按 thread_id 隔离）

### Q: 多用户数据如何隔离？
A: 两种方案：
1. **SQLite Checkpointer**：按 `thread_id` 自动隔离（LangGraph 内置）
2. **应用层隔离**：所有查询加上 `user_id` 条件（推荐）

## 十四、数据流图

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  mcp_service_simple.py                                      │
│  1. 验证 JWT Token 获取 user_id                             │
│  2. 从 SQLite 加载 resume_data, jd_data                     │
│  3. 构造初始 state                                          │
│  4. 调用 graph.invoke(state)                                │
│  5. 从 state 取出结果，更新 SQLite                           │
└─────────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌──────────────────┐  ┌──────────────────┐
│ SQLite           │  │ LangGraph        │
│ (users, resumes, │  │ (SqliteSaver)    │
│  jds, invite_    │  │ (对话状态持久化)  │
│  codes)          │  │                  │
└──────────────────┘  └──────────────────┘
```

---

## 十五、后续扩展（可选）

当用户量增长到 5000+ 时，可平滑升级：

| 升级项 | 从 | 到 |
|--------|-----|-----|
| 数据库 | SQLite | PostgreSQL |
| 任务队列 | 无 | Redis + Celery |
| 缓存 | 无 | Redis |
| 部署 | 单机 | 多实例 + 负载均衡 |
