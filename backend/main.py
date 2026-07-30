"""
简历助手后端服务

提供 HTTP API 接口，连接前端和 AI 代理。

核心职责：
1. HTTP 请求处理和响应
2. SSE 流式输出
3. 用户认证（JWT）
4. 数据持久化（SQLAlchemy）
"""

import json
import asyncio
import base64
import platform
import subprocess
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from dotenv import set_key


def _configure_console_encoding():
    """Keep diagnostic output from crashing on Unicode characters on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (AttributeError, ValueError):
                pass


_configure_console_encoding()

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# 导入 resume_agent 中的 graph 和 conversation_llm
from . import resume_agent
from .resume_agent import LLM_ENABLED, conversation_llm, current_user_id, graph
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

# 导入自定义模块
from .database import (
    init_db, get_db, create_user, get_user_by_email,
    save_user_resume, get_user_resume, save_user_jd, get_user_jd,
    check_invite_code, use_invite_code, create_invite_code,
    get_parsing_status, set_parsing_status, get_user_photo,
    list_resume_projects, create_resume_project, get_resume_project,
    list_project_tasks, create_resume_task, get_resume_task,
    delete_resume_project, delete_resume_task
)
from .auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, oauth2_scheme, require_multi_user_mode
)
from .config import APP_MODE, LOCAL_USER_EMAIL, is_local_mode

# PDF 生成器 - 懒加载（在 API 调用时才导入）
_pdf_generator = None

# =============================================================================
# 上下文压缩状态管理
# =============================================================================

class CompressionState:
    """全局压缩状态管理"""
    compressing = False  # 是否正在压缩
    pending_futures = []  # 等待压缩完成的 Future 列表

compression_state = CompressionState()

# 上下文压缩配置
MAX_HUMAN_MESSAGES = 20  # 最多保留20条HumanMessage，提早触发压缩
KEEP_RECENT = 5  # 保留最近5条不压缩，减少上下文大小


def wait_for_compression():
    """等待当前压缩完成（如果正在压缩）"""
    if compression_state.compressing:
        future = asyncio.get_event_loop().create_future()
        compression_state.pending_futures.append(future)
        return future
    return None


def notify_compression_complete():
    """通知压缩完成，处理等待中的请求"""
    compression_state.compressing = False
    for future in compression_state.pending_futures:
        if not future.done():
            future.set_result(True)
    compression_state.pending_futures.clear()


def _setup_weasyprint_env():
    """Set platform-specific native library paths used by WeasyPrint."""
    if platform.system() == "Darwin":
        libs = ['pango', 'harfbuzz', 'cairo', 'fontconfig']
        lib_paths = []

        for lib in libs:
            result = subprocess.run(['brew', '--prefix', lib], capture_output=True, text=True)
            if result.returncode == 0:
                lib_path = os.path.join(result.stdout.strip(), 'lib')
                lib_paths.append(lib_path)

        if lib_paths:
            os.environ['DYLD_LIBRARY_PATH'] = ':'.join(lib_paths)
            print(f"已设置 DYLD_LIBRARY_PATH={' '.join(lib_paths)}")
    elif platform.system() == "Windows":
        dll_directory = os.getenv(
            "WEASYPRINT_DLL_DIRECTORIES",
            r"C:\resume-tools\msys64\ucrt64\bin"
        )
        if os.path.isdir(dll_directory):
            os.environ["WEASYPRINT_DLL_DIRECTORIES"] = dll_directory
        else:
            raise RuntimeError(
                f"WeasyPrint DLL directory not found: {dll_directory}"
            )


def get_pdf_generator():
    """懒加载 PDF 生成器"""
    global _pdf_generator
    if _pdf_generator is None:
        _setup_weasyprint_env()
        from .pdf_generator import generate_pdf
        _pdf_generator = generate_pdf
    return _pdf_generator


def generate_session_id() -> str:
    """生成唯一会话 ID"""
    return str(uuid.uuid4())


# =============================================================================
# Pydantic Models
# =============================================================================

class RegisterRequest(BaseModel):
    """注册请求"""
    email: str
    password: str
    invite_code: str


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str
    user: dict


class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    email: str
    created_at: datetime


class SaveResumeRequest(BaseModel):
    """保存简历请求"""
    resume_data: dict


class CreateProjectRequest(BaseModel):
    """创建简历项目请求"""
    title: str = "未命名简历"


class CreateTaskRequest(BaseModel):
    """创建岗位任务请求"""
    title: str = "新岗位版本"
    copy_base_resume: bool = True


class LLMSettingsRequest(BaseModel):
    """本地 LLM 设置。api_key 为空时保留现有密钥。"""
    provider: str = "moonshot"
    model: str
    base_url: str
    api_key: str | None = None


def serialize_task(task):
    resume_data = task.resume_data or {}
    basics = resume_data.get("basics", {}) if isinstance(resume_data, dict) else {}
    jd_data = task.jd_data or {}
    return {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "is_base": task.is_base,
        "session_id": task.session_id,
        "candidate_name": basics.get("name", ""),
        "target_position": (
            basics.get("target_position", "")
            or (jd_data.get("position", "") if isinstance(jd_data, dict) else "")
        ),
        "message_count": len(task.messages or []),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def serialize_project(project, task_count=0):
    resume_data = project.base_resume_data or {}
    basics = resume_data.get("basics", {}) if isinstance(resume_data, dict) else {}
    return {
        "id": project.id,
        "title": project.title,
        "candidate_name": basics.get("name", ""),
        "target_position": basics.get("target_position", ""),
        "task_count": task_count,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


# =============================================================================
# LLM 上下文压缩
# =============================================================================

async def compress_context_with_llm(messages, max_summary_length=1000):
    """
    使用 LLM 对早期对话进行语义压缩
    """
    if len(messages) <= 5:
        return messages

    early_messages = messages[:-5]
    recent_messages = messages[-5:]

    conversation_text = ""
    for msg in early_messages:
        role = getattr(msg, 'role', 'unknown') if hasattr(msg, 'role') else type(msg).__name__
        content = getattr(msg, 'content', str(msg))
        if isinstance(content, list):
            text_content = []
            for c in content:
                if isinstance(c, dict):
                    type_key = 'type'
                    if type_key in c and c[type_key] == 'text':
                        text_content.append(c)
            content = str(text_content)
        conversation_text += f"【{role}】{str(content)[:300]}\n"

    summary_prompt = ChatPromptTemplate.from_messages([
        ("system", f"""
        你是高效的对话压缩专家。你的任务是将对话压缩到指定长度，保留最有价值的关键信息与个性化信息。

## 压缩目标
- 输出摘要长度：不超过{max_summary_length}个汉字（但也不要太短）
- 每个字都要有价值

## 必须保留的信息（按优先级）
## 必须保留的信息（按优先级）

1. **讨论过的话题**
   - 用户和 AI 讨论过哪些主题/话题
   - 每个话题的关键结论或进展
   - 哪些话题已结束、哪些还在进行中

2. **用户明确表达的要求和偏好**
   - 用户对简历的具体修改要求
   - 用户提到的工作偏好、城市偏好、薪资期望等
   - 用户明确拒绝或喜欢的风格

3. **用户提及的个人背景**
   - 用户在对话中提到的额外经历、故事
   - 用户口头补充的信息（不在简历中的）
   - 用户的职业规划、转型原因等

4. **用户的性格特点**
   - 用户的沟通风格（简洁话唠严肃幽默等）
   - 用户做决策的方式（犹豫果断犹豫等）
   - 用户的特殊习惯或偏好

5. **修改历史和决策**
   - 用户确认过的修改点
   - 用户拒绝过的建议
   - 用户特别满意的修改

6. **当前上下文**
   - 用户当前最关心的问题
   - 当前对话的主题

## 可以丢弃的信息
- 简历中已有的结构化信息（姓名、岗位、技能等）
- 客套话、寒暄
- LLM 的解释性内容
- 重复的表达

## 输出格式
【讨论话题】列出所有讨论过的话题及关键结论
【用户个性化信息】用户提及的个人要求、偏好、背景等
【修改决策】确认的修改点、拒绝的建议
【当前状态】用户当前的需求和关注点
【重要备注】其他需要记住的个性化信息
"""),
        ("human", f"待压缩的对话：\n\n{conversation_text}")
    ])

    try:
        summary_chain = summary_prompt | conversation_llm
        summary_result = await summary_chain.ainvoke({})
        summary_content = summary_result.content.strip()
        print(f"[Context] LLM 摘要生成成功: {len(summary_content)}字")
        print(f"[Context] 摘要内容:\n{summary_content}")

        summary_message = SystemMessage(content=summary_content)
        return [summary_message] + recent_messages

    except Exception as e:
        print(f"[Context] LLM 摘要生成失败: {e}")
        return list(messages[-10:])


# =============================================================================
# FastAPI 应用
# =============================================================================

app = FastAPI(title="ResumeBranch API", version="2.0.0")


def require_llm_configured():
    """Return a clear local-mode error instead of attempting an unauthenticated call."""
    if not resume_agent.LLM_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="LLM_API_KEY 尚未配置；基础简历和数据库功能可继续使用。"
        )

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化数据库
init_db()


# =============================================================================
# 认证端点
# =============================================================================

@app.get("/app/config")
async def get_app_config():
    """Expose non-sensitive runtime capabilities to the frontend."""
    return {
        "app_mode": APP_MODE,
        "authentication_required": not is_local_mode(),
        "account_management_enabled": not is_local_mode(),
        "local_user_email": LOCAL_USER_EMAIL if is_local_mode() else None,
    }


def require_local_settings():
    """Keep machine-local secrets out of hosted or multi-user deployments."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="本地设置仅在本地模式可用")


def serialize_llm_settings():
    api_key = os.getenv("LLM_API_KEY", "").strip()
    return {
        "provider": os.getenv("LLM_PROVIDER", "moonshot").strip() or "moonshot",
        "model": os.getenv("LLM_MODEL", "").strip(),
        "base_url": os.getenv("BASE_URL", "").strip(),
        "configured": bool(api_key),
        "api_key_hint": f"••••{api_key[-4:]}" if api_key else "",
    }


@app.get("/settings/llm", dependencies=[Depends(require_local_settings)])
async def get_llm_settings(current_user=Depends(get_current_user)):
    """Return local LLM settings without exposing the stored API key."""
    return serialize_llm_settings()


@app.post("/settings/llm/test", dependencies=[Depends(require_local_settings)])
async def test_llm_settings(
    request: LLMSettingsRequest,
    current_user=Depends(get_current_user),
):
    model = request.model.strip()
    base_url = request.base_url.strip()
    api_key = (request.api_key or os.getenv("LLM_API_KEY", "")).strip()
    if not model or not base_url or not api_key:
        raise HTTPException(status_code=400, detail="请完整填写模型、Base URL 和 API Key")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Base URL 必须以 http:// 或 https:// 开头")

    try:
        test_llm = resume_agent.create_llm_for_config(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.0,
        )
        await asyncio.wait_for(
            test_llm.ainvoke([HumanMessage(content="Reply with OK only.")]),
            timeout=35,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="连接超时，请检查接口地址或网络") from exc
    except Exception as exc:
        print(f"[Settings] LLM connection test failed: {exc}")
        raise HTTPException(status_code=400, detail="连接失败，请检查模型、接口地址和密钥") from exc
    return {"success": True, "model": model}


@app.put("/settings/llm", dependencies=[Depends(require_local_settings)])
async def update_llm_settings(
    request: LLMSettingsRequest,
    current_user=Depends(get_current_user),
):
    global LLM_ENABLED, conversation_llm

    provider = request.provider.strip() or "custom"
    model = request.model.strip()
    base_url = request.base_url.strip()
    if not model or not base_url:
        raise HTTPException(status_code=400, detail="模型和 Base URL 不能为空")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Base URL 必须以 http:// 或 https:// 开头")

    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    updates = {
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model,
        "BASE_URL": base_url,
    }
    if request.api_key is not None and request.api_key.strip():
        updates["LLM_API_KEY"] = request.api_key.strip()

    for key, value in updates.items():
        os.environ[key] = value
        set_key(str(dotenv_path), key, value)

    runtime = resume_agent.reload_llm_config()
    # Keep legacy references in this module in sync for context compression.
    LLM_ENABLED = resume_agent.LLM_ENABLED
    conversation_llm = resume_agent.conversation_llm
    return {
        **serialize_llm_settings(),
        "configured": runtime["configured"],
    }


@app.post(
    "/auth/register",
    response_model=TokenResponse,
    dependencies=[Depends(require_multi_user_mode)],
)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    用户注册

    - 邮箱+密码+邀请码
    - 返回 JWT Token
    """
    # 检查邀请码
    if not check_invite_code(db, request.invite_code):
        raise HTTPException(status_code=400, detail="邀请码无效或已使用")

    # 检查邮箱是否已存在
    if get_user_by_email(db, request.email):
        raise HTTPException(status_code=400, detail="邮箱已注册")

    # 创建用户
    hashed_password = get_password_hash(request.password)
    user = create_user(db, request.email, hashed_password, request.invite_code)

    # 使用邀请码
    use_invite_code(db, request.invite_code)

    # 生成 Token
    token = create_access_token({"sub": user.email})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={"id": user.id, "email": user.email, "created_at": user.created_at.isoformat()}
    )


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    dependencies=[Depends(require_multi_user_mode)],
)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    用户登录

    - 邮箱+密码
    - 返回 JWT Token
    """
    user = get_user_by_email(db, form_data.username)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")

    token = create_access_token({"sub": user.email})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={"id": user.id, "email": user.email, "created_at": user.created_at.isoformat()}
    )


@app.get("/auth/me", response_model=UserResponse)
async def get_me(current_user = Depends(get_current_user)):
    """
    获取当前用户信息
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        created_at=current_user.created_at
    )


@app.get("/auth/invite-codes", dependencies=[Depends(require_multi_user_mode)])
async def list_invites(current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    获取邀请码列表（需要登录）
    """
    from .database import InviteCode
    codes = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
    return [
        {"code": c.code, "is_used": c.is_used, "created_at": c.created_at.isoformat()}
        for c in codes
    ]


@app.post("/auth/invite-codes", dependencies=[Depends(require_multi_user_mode)])
async def create_invite(request: Request, current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    生成邀请码（需要登录）
    """
    import random
    import string

    # 解析请求体
    try:
        body = await request.json()
        count = min(int(body.get('count', 1)), 20)
    except:
        count = 1

    codes = []
    for _ in range(count):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        create_invite_code(db, code)
        codes.append({"code": code, "is_used": False, "created_at": None})

    return codes if count > 1 else {"code": codes[0]["code"]}


# =============================================================================
# 业务端点
# =============================================================================

@app.get("/projects")
async def get_projects(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """列出简历项目，并自动迁移旧版单简历数据。"""
    projects = list_resume_projects(db, current_user.id)
    return [
        serialize_project(project, len(list_project_tasks(db, current_user.id, project.id)))
        for project in projects
    ]


@app.post("/projects")
async def create_project(
    request: CreateProjectRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    project, base_task = create_resume_project(db, current_user.id, request.title)
    return {**serialize_project(project, 1), "base_task_id": base_task.id}


@app.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    project = get_resume_project(db, current_user.id, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    tasks = list_project_tasks(db, current_user.id, project_id)
    return {**serialize_project(project, len(tasks)), "tasks": [serialize_task(t) for t in tasks]}


@app.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not delete_resume_project(db, current_user.id, project_id):
        raise HTTPException(status_code=404, detail="主简历不存在")
    return {"success": True}


@app.post("/projects/{project_id}/tasks")
async def create_task(
    project_id: str,
    request: CreateTaskRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    task = create_resume_task(
        db,
        current_user.id,
        project_id,
        request.title,
        copy_base_resume=request.copy_base_resume,
    )
    if not task:
        raise HTTPException(status_code=404, detail="项目不存在")
    return serialize_task(task)


@app.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    task = get_resume_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return serialize_task(task)


@app.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    result = delete_resume_task(db, current_user.id, task_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="岗位版本不存在")
    if result == "base_task":
        raise HTTPException(status_code=400, detail="基础简历不能单独删除，请删除整份主简历")
    return {"success": True}


@app.post("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "2.0.0", "app_mode": APP_MODE}


@app.post("/load_resume")
async def load_resume_endpoint(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    加载当前用户的简历数据
    """
    try:
        print(f"[load_resume] user_id={current_user.id}, email={current_user.email}")
        resume_data = get_user_resume(db, current_user.id)

        # 打印加载的数据
        if resume_data and isinstance(resume_data, dict):
            basics = resume_data.get('basics', {})
            print(f"[load_resume] 加载简历: name={basics.get('name', 'N/A')}, target_position={basics.get('target_position', 'N/A')}")
        else:
            print(f"[load_resume] 未找到简历数据")

        # 获取证件照
        photo = get_user_photo(db, current_user.id)

        # 将 photo 放入 resume_data 的 basics 中（保持向前兼容）
        if resume_data and isinstance(resume_data, dict):
            if 'basics' not in resume_data:
                resume_data['basics'] = {}
            resume_data['basics']['photo'] = photo
        else:
            resume_data = {'basics': {'photo': photo}}

        # 安全获取解析状态
        try:
            parsing_status = get_parsing_status(db, current_user.id)
        except Exception as statusError:
            print(f"[WARN] get_parsing_status failed: {statusError}, using default")
            parsing_status = "none"

        if isinstance(resume_data, dict) and "error" in resume_data:
            return JSONResponse(content={}, status_code=500)
        return JSONResponse(content={
            **resume_data,
            "parsing_status": parsing_status
        })
    except Exception as e:
        print(f"[ERROR] load_resume: {str(e)}")
        import traceback
        traceback.print_exc()
        # 返回空简历数据，避免前端崩溃
        return JSONResponse(content={"parsing_status": "none"}, status_code=200)


@app.post("/save_resume")
async def save_resume_endpoint(request: SaveResumeRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    保存当前用户的简历数据
    """
    try:
        save_user_resume(db, current_user.id, request.resume_data)
        return JSONResponse(content={"success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/load_jd")
async def load_jd_endpoint(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    加载当前用户的JD数据
    """
    try:
        jd_data = get_user_jd(db, current_user.id)
        if isinstance(jd_data, dict) and "error" in jd_data:
            return JSONResponse(content={}, status_code=500)
        return JSONResponse(content=jd_data)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/save_jd")
async def save_jd_endpoint(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    保存当前用户的JD数据
    """
    try:
        request_data = await request.json()
        jd_data = request_data.get('jd_data', {})

        company = jd_data.get('company', '')
        position = jd_data.get('position', '')
        save_user_jd(db, current_user.id, jd_data, company, position)

        return JSONResponse(content={"success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


def filter_images_from_message_dict(msg_dict):
    """过滤消息字典中的图片内容"""
    if not isinstance(msg_dict, dict):
        return msg_dict

    content = msg_dict.get('content', '')

    # 如果 content 是列表（多模态内容），过滤掉图片
    if isinstance(content, list):
        filtered = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                filtered.append(item)
            # 跳过 type == 'image_url' 的图片
        if filtered:
            msg_dict['content'] = filtered
        else:
            msg_dict['content'] = ''

    return msg_dict


@app.post("/save_conversation")
async def save_conversation_endpoint(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    保存对话历史
    """
    try:
        request_data = await request.json()
        session_id = request_data.get('session_id', 'default')
        messages = request_data.get('messages', [])

        # 过滤掉消息中的图片
        filtered_messages = [filter_images_from_message_dict(msg) for msg in messages]

        from .database import save_conversation
        save_conversation(db, current_user.id, session_id, filtered_messages)

        return JSONResponse(content={"success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/load_conversation")
async def load_conversation_endpoint(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    加载对话历史
    """
    try:
        request_data = await request.json()
        session_id = request_data.get('session_id', 'default')

        from .database import get_conversation
        messages = get_conversation(db, current_user.id, session_id)

        return JSONResponse(content=messages)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/parse_jd")
async def parse_jd_endpoint(request: Request, current_user = Depends(get_current_user)):
    """
    解析JD文本/图片为结构化JSON
    """
    require_llm_configured()
    try:
        import re
        request_data = await request.json()
        jd_text = request_data.get('text', '')
        jd_image = request_data.get('image', '')

        from .resume_agent import JD_PARSER_PROMPT, jd_parser_llm

        if jd_image:
            if jd_image.startswith('data:image'):
                jd_image = jd_image.split(',')[1]

            message = HumanMessage(
                content=[
                    {"type": "text", "text": "请解析这张JD图片，提取结构化信息为JSON"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jd_image}"}}
                ]
            )
        else:
            if not jd_text.strip():
                return JSONResponse(content={"error": "没有收到JD内容"}, status_code=400)
            message = HumanMessage(content=f"请解析以下JD内容：\n\n{jd_text}")

        response = await jd_parser_llm.ainvoke([
            SystemMessage(content=JD_PARSER_PROMPT),
            message
        ])

        content = response.content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'^```\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

        try:
            parsed_jd = json.loads(content)
        except json.JSONDecodeError:
            parsed_jd = {"error": "解析失败", "raw": content}

        return JSONResponse(content=parsed_jd)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/resume/parse_and_save")
async def parse_and_save_resume_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    解析简历图片并保存（首次上传流程）
    支持 multipart/form-data 上传文件
    """
    require_llm_configured()
    try:
        import re

        if not file:
            return JSONResponse(content={"success": False, "error": "未收到文件"}, status_code=400)

        # 验证文件类型
        content_type = file.content_type
        if not content_type.startswith('image/') and content_type != 'application/pdf':
            return JSONResponse(content={"success": False, "error": "只支持图片或PDF文件"}, status_code=400)

        # 读取文件内容
        file_content = await file.read()

        from .resume_agent import RESUME_FULL_EXTRACT_PROMPT, jd_parser_llm

        # 设置解析状态为进行中
        set_parsing_status(db, current_user.id, "parsing")

        # Kimi/OpenAI 视觉接口不接收 application/pdf 类型的 image_url。
        # PDF 先在本地逐页渲染为 PNG，再作为多张图片交给视觉模型。
        message_content = [
            {"type": "text", "text": "请完整提取这份简历中的所有信息，**不要省略任何内容**。"}
        ]
        if content_type == 'application/pdf':
            import fitz

            document = fitz.open(stream=file_content, filetype="pdf")
            try:
                if document.page_count == 0:
                    return JSONResponse(
                        content={"success": False, "error": "PDF 没有可解析页面"},
                        status_code=400,
                    )
                if document.page_count > 10:
                    return JSONResponse(
                        content={"success": False, "error": "PDF 最多支持 10 页"},
                        status_code=400,
                    )

                for page in document:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    page_base64 = base64.b64encode(
                        pixmap.tobytes("png")
                    ).decode("utf-8")
                    message_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{page_base64}"
                        },
                    })
            finally:
                document.close()
        else:
            if content_type == 'image/png':
                mime_type = 'image/png'
            elif content_type == 'image/webp':
                mime_type = 'image/webp'
            else:
                mime_type = 'image/jpeg'

            base64_content = base64.b64encode(file_content).decode('utf-8')
            message_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_content}"
                },
            })

        message = HumanMessage(content=message_content)

        # 调用 LLM 解析
        response = await jd_parser_llm.ainvoke([
            SystemMessage(content=RESUME_FULL_EXTRACT_PROMPT),
            message
        ])

        # 清理 JSON
        content = response.content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'^```\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

        try:
            resume_data = json.loads(content)
        except json.JSONDecodeError:
            # 解析失败
            set_parsing_status(db, current_user.id, "failed")
            return JSONResponse(content={"success": False, "error": "解析失败", "raw": content}, status_code=500)

        # 保存到数据库
        from .database import save_user_resume
        save_user_resume(db, current_user.id, resume_data)
        # 设置解析状态为完成
        set_parsing_status(db, current_user.id, "completed")

        return JSONResponse(content={
            "success": True,
            "resume_data": resume_data,
            "message": "简历解析并保存成功"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 解析失败
        set_parsing_status(db, current_user.id, "failed")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.get("/api/resume/parsing_status")
async def get_parsing_status_endpoint(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """获取简历解析状态"""
    status = get_parsing_status(db, current_user.id)
    return {"parsing_status": status}


@app.post("/export_pdf")
async def export_pdf_endpoint(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    导出 PDF（从数据库读取简历）
    """
    try:
        # 尝试获取JSON，如果请求体为空则使用空字典
        try:
            request_data = await request.json()
        except Exception:
            request_data = {}
        style = request_data.get('style', {})
        lang = request_data.get('lang', 'zh')  # 默认中文

        # 从数据库获取简历
        resume_data = get_user_resume(db, current_user.id)
        if not resume_data:
            return JSONResponse(content="错误: 没有找到简历数据，请先创建或加载简历", status_code=400)

        # 从数据库获取证件照
        photo = get_user_photo(db, current_user.id) or None

        generate_pdf = get_pdf_generator()
        pdf_bytes = generate_pdf(resume_data, style, photo, lang)

        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=resume_{current_user.id}.pdf"}
        )
    except Exception as e:
        print(f"PDF 导出错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content=f"错误: {str(e)}", status_code=500)


@app.post("/chat")
async def chat_endpoint(
    message: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    session_id: str = Form(""),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    聊天接口

    - 需要认证
    - 从数据库加载用户数据
    - 设置全局用户ID供工具使用
    """
    require_llm_configured()
    try:
        task_id = db.info.get("task_id")
        if not task_id:
            return JSONResponse(content={"error": "请先选择一个简历任务"}, status_code=400)
        from . import resume_agent
        resume_agent.current_user_id = current_user.id
        resume_agent.current_task_id = task_id

        # 生成会话 ID
        if not session_id:
            session_id = generate_session_id()
        elif len(session_id) > 36:
            return JSONResponse(
                content={"error": "session_id 最长为 36 个字符"},
                status_code=400,
            )

        # 构建 graph 配置（用于状态追踪）
        config = {"configurable": {"thread_id": f"task_{task_id}_session_{session_id}"}}

        # 检测用户是否点击了确认按钮（必须在使用 message 之前）
        is_confirm_click = '[CONFIRM_REPLY:' in message.strip()

        print(f"[DEBUG] session_id: {session_id}")
        print(f"[DEBUG] is_confirm_click: {is_confirm_click}")
        print(f"[DEBUG] message.strip(): {message.strip()[:100]}...")

        # 构建消息内容
        message_content = []
        if message.strip():
            message_content.append({"type": "text", "text": message.strip()})

        # 处理文件上传
        for file in files:
            content = await file.read()
            if file.content_type.startswith("image/"):
                base64_content = base64.b64encode(content).decode("utf-8")
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{file.content_type};base64,{base64_content}"}
                })
            elif file.content_type == "application/pdf":
                import fitz

                document = fitz.open(stream=content, filetype="pdf")
                try:
                    if document.page_count == 0:
                        return JSONResponse(
                            content={"error": "PDF 没有可解析页面"},
                            status_code=400,
                        )
                    if document.page_count > 10:
                        return JSONResponse(
                            content={"error": "PDF 最多支持 10 页"},
                            status_code=400,
                        )

                    for page in document:
                        pixmap = page.get_pixmap(
                            matrix=fitz.Matrix(2, 2),
                            alpha=False,
                        )
                        page_base64 = base64.b64encode(
                            pixmap.tobytes("png")
                        ).decode("utf-8")
                        message_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{page_base64}"
                            },
                        })
                finally:
                    document.close()

        # 从数据库加载用户数据
        resume_data = get_user_resume(db, current_user.id)
        jd_data = get_user_jd(db, current_user.id)

        # 创建用户消息（包含文本和图片附件）
        # 检查是否有图片附件
        has_image = any(item.get("type") == "image_url" for item in message_content)
        if has_image:
            # 有图片附件，使用多模态内容（包含文本和图片）
            current_message = HumanMessage(content=message_content)
        else:
            # 只有文本
            current_message = HumanMessage(content=message.strip())

        # 从数据库获取压缩后的上下文（这是唯一的消息来源）
        from .database import get_conversation_context
        db_context_raw = get_conversation_context(db, current_user.id, session_id)

        # 转换数据库中的消息为 Message 对象
        historical_messages = []
        for msg_dict in db_context_raw:
            msg_type = msg_dict.get("type", "").lower()
            content = msg_dict.get("content", "")
            tool_calls = msg_dict.get("tool_calls", [])
            if tool_calls:
                continue
            if msg_type == "human":
                historical_messages.append(HumanMessage(content=content))
            elif msg_type == "ai":
                historical_messages.append(AIMessage(content=content))
            elif msg_type == "system" or msg_type == "systemmessage":
                historical_messages.append(SystemMessage(content=content))

        # 构建 all_messages：数据库中的历史消息 + 当前用户消息
        all_messages = list(historical_messages) + [current_message]
        print(f"[InitState] 从数据库加载 {len(historical_messages)} 条历史消息 + 当前消息")

        # 使用数据库中的数据
        initial_resume_data = resume_data if resume_data else (get_user_resume(db, current_user.id) or {})
        initial_jd_data = jd_data if jd_data else (get_user_jd(db, current_user.id) or {})

        # 从数据库获取待确认状态
        from .database import get_pending_confirmation
        initial_pending_confirmation = get_pending_confirmation(db, current_user.id, session_id)
        if initial_pending_confirmation:
            print(f"[InitState] 从数据库加载 pending_confirmation: confirm_id={initial_pending_confirmation.get('confirm_id')}")
        else:
            print(f"[InitState] 从数据库加载 pending_confirmation: None")

        # 创建初始状态
        # 注意：当用户点击确认时，initial_state 包含完整的消息历史
        # 这样 tool_node 和 conversation_llm 才能正确访问上下文
        initial_state = {
            "messages": all_messages,  # 保留完整的历史消息
            "resume_data": initial_resume_data,
            "jd_data": initial_jd_data,
            "pending_confirmation": initial_pending_confirmation,  # 从数据库加载待确认状态
            "user_id": current_user.id,  # 添加用户ID，用于数据隔离
            "task_id": task_id,
        }
        print(f"[InitState] initial_state 创建完成: {len(all_messages)} 条消息, pending_confirmation={initial_state.get('pending_confirmation') is not None}")
        for i, msg in enumerate(all_messages):
            print(f"  {i}: {type(msg).__name__}: {getattr(msg, 'content', '')[:30]}...")

        def filter_images_from_content(content):
            """过滤消息内容中的图片，只保留文本"""
            if isinstance(content, list):
                # 过滤掉图片，只保留文本
                filtered = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            filtered.append(item)
                        # 跳过 type == "image_url" 的图片
                return filtered if filtered else ""
            return content

        def filter_images_from_message(msg):
            """过滤消息中的图片内容"""
            content = getattr(msg, 'content', '')
            filtered_content = filter_images_from_content(content)

            # 创建新的消息对象，只包含过滤后的内容
            if isinstance(msg, HumanMessage):
                return HumanMessage(content=filtered_content)
            elif isinstance(msg, AIMessage):
                return AIMessage(content=filtered_content)
            elif isinstance(msg, SystemMessage):
                return SystemMessage(content=filtered_content)
            return msg

        async def save_state_async(db, user_id, session_id, messages_list, resume_data_result, initial_jd_data, pending_confirmation=None):
            """异步保存状态到数据库，不阻塞 SSE 响应"""
            try:
                if pending_confirmation:
                    print(f"[SaveStateAsync] 开始保存状态, confirm_id={pending_confirmation.get('confirm_id')}")
                else:
                    print(f"[SaveStateAsync] 开始保存状态, pending_confirmation=None")

                # 过滤掉消息中的图片
                filtered_messages_list = [filter_images_from_message(msg) for msg in messages_list]

                # 从 filtered_messages_list 中提取 HumanMessage 和 AIMessage（跳过 ToolMessage）
                all_human = [msg for msg in filtered_messages_list if isinstance(msg, HumanMessage)]
                all_ai = [msg for msg in filtered_messages_list if isinstance(msg, AIMessage)]

                # 提取最后一条 AIMessage
                new_ai = all_ai[-1] if all_ai else None

                # 确定最终数据
                final_resume_data = resume_data_result if resume_data_result else {}
                final_jd_data = initial_jd_data if initial_jd_data else {}

                print(f"[SaveState] 待保存: {len(all_human)} HumanMessage, {len(all_ai)} AIMessage, pending_confirmation={pending_confirmation is not None}")

                # 保存到数据库
                if final_resume_data:
                    save_user_resume(db, user_id, final_resume_data)
                if final_jd_data:
                    save_user_jd(db, user_id, final_jd_data)

                # 保存上下文（带压缩逻辑）
                from .database import save_conversation_context

                # 1. 构建压缩上下文（按原始顺序保存 HumanMessage 和 AIMessage）
                compressed_context = []
                for msg in filtered_messages_list:
                    if isinstance(msg, HumanMessage):
                        if hasattr(msg, 'model_dump'):
                            compressed_context.append({**msg.model_dump(), "type": "human"})
                        else:
                            compressed_context.append({**dict(msg), "type": "human"})
                    elif isinstance(msg, AIMessage):
                        if hasattr(msg, 'model_dump'):
                            compressed_context.append({**msg.model_dump(), "type": "ai"})
                        else:
                            compressed_context.append({**dict(msg), "type": "ai"})
                    elif isinstance(msg, SystemMessage):
                        if hasattr(msg, 'model_dump'):
                            compressed_context.append({**msg.model_dump(), "type": "system"})
                        else:
                            compressed_context.append({**dict(msg), "type": "system"})

                # 检查是否需要压缩
                if len(all_human) > MAX_HUMAN_MESSAGES:
                    # 设置压缩状态
                    compression_state.compressing = True
                    print(f"[Context Compression] 开始压缩上下文 ({len(all_human)} 条 HumanMessage)")

                    try:
                        # 压缩前 N-K 条为摘要
                        to_compress = all_human[:-(KEEP_RECENT)]
                        recent = all_human[-(KEEP_RECENT):]  # 最近 K 条 HumanMessage
                        compressed = await compress_context_with_llm(to_compress)

                        # 将压缩结果转换为字典
                        new_compressed_context = []
                        for msg in compressed:
                            if hasattr(msg, 'model_dump'):
                                msg_dict = {**msg.model_dump(), "type": type(msg).__name__.lower()}
                            else:
                                msg_dict = {**dict(msg), "type": type(msg).__name__.lower()}
                            new_compressed_context.append(msg_dict)

                        # 添加最近 K 条 HumanMessage
                        for msg in recent:
                            if hasattr(msg, 'model_dump'):
                                new_compressed_context.append({**msg.model_dump(), "type": "human"})
                            else:
                                new_compressed_context.append({**dict(msg), "type": "human"})

                        # 添加最后一条 AIMessage
                        if new_ai:
                            if hasattr(new_ai, 'model_dump'):
                                new_compressed_context.append({**new_ai.model_dump(), "type": "ai"})
                            else:
                                new_compressed_context.append({**dict(new_ai), "type": "ai"})

                        # 替换 compressed_context 为压缩后的版本
                        compressed_context = new_compressed_context
                    finally:
                        # 通知压缩完成
                        notify_compression_complete()

                # 保存到数据库
                save_conversation_context(db, user_id, session_id, compressed_context, pending_confirmation)

            except Exception as e:
                print(f"[Warning] 异步保存失败: {e}")
                import traceback
                traceback.print_exc()

        async def stream_response(config):
            """流式生成响应"""
            import time
            total_start = time.time()

            # 累积所有消息，而不是每轮重置
            # 这样 save_state_async 才能获取完整的消息历史
            messages_list = list(all_messages)  # 从 initial_state 开始
            print(f"[StreamResponse] messages_list 初始化: {len(messages_list)} 条消息")
            resume_data_result = {}
            pending_confirmation_result = None  # 保存待确认状态
            final_content = None
            accumulated_content = ""
            current_node = None
            node_start_time = {}

            try:
                # 统一使用 graph.astream_events
                # 入口路由会在 Graph 内部处理（通过 entry_router）
                print(f"[SSE] 开始流式处理, 消息数量: {len(initial_state.get('messages', []))}")
                async for event in graph.astream_events(initial_state, config=config, version="v1"):
                    event_type = event.get("event", "")
                    node_name = event.get("name", "")

                    if event_type == "on_chain_start":
                        current_node = node_name
                        node_start_time[node_name] = time.time()
                        print(f"[SSE] 节点开始: {node_name}")

                    if event_type == "on_chat_model_stream" and current_node == "conversation_llm":
                        chunk = event.get("data", {}).get("chunk", {})
                        token = ""
                        if hasattr(chunk, "content"):
                            content = chunk.content
                            if isinstance(content, str):
                                token = content
                            elif hasattr(content, "text"):
                                text = content.text
                                if isinstance(text, str):
                                    token = text

                        if not token and hasattr(chunk, "text"):
                            text = chunk.text
                            if isinstance(text, str):
                                token = text

                        if token:
                            accumulated_content += token
                            yield f'data: {json.dumps({"type": "stream", "content": accumulated_content})}\n\n'

                    elif event_type == "on_chain_end":
                        if node_name in node_start_time:
                            del node_start_time[node_name]

                        # 跳过内部节点（__start__, entry_router），只处理实际的工作节点
                        if node_name in ["__start__", "entry_router"]:
                            continue

                        if node_name == "tool_node":
                            output_data = event.get('data', {}).get('output', {})
                            output_keys = list(output_data.keys()) if isinstance(output_data, dict) else []
                            print(f"[SSE] tool_node output keys: {output_keys}")
                            if isinstance(event.get("data", {}).get("output"), dict):
                                output = event["data"]["output"]
                                print(f"[SSE] pending_confirmation in output: {output.get('pending_confirmation')}")
                                if "pending_confirmation" in output and output["pending_confirmation"]:
                                    confirm_data = output["pending_confirmation"]
                                    confirm_msg_id = str(uuid.uuid4())
                                    # 同步保存 pending_confirmation 到数据库，确保立即可用
                                    try:
                                        from .database import get_conversation_context, save_conversation_context
                                        # 先获取当前压缩上下文
                                        current_context = get_conversation_context(db, current_user.id, session_id)
                                        # 保存 pending_confirmation，保留当前上下文
                                        save_conversation_context(db, current_user.id, session_id, current_context, confirm_data)
                                        print(f"[SSE] 同步保存 pending_confirmation: confirm_id={confirm_data.get('confirm_id')}")
                                    except Exception as e:
                                        print(f"[Warning] 同步保存 pending_confirmation 失败: {e}")
                                    pending_confirmation_result = confirm_data  # 保存待确认状态
                                    yield 'data: ' + json.dumps({
                                        "type": "confirm",
                                        "id": confirm_msg_id,
                                        "content": confirm_data["content"],
                                        "options": confirm_data["options"],
                                        "confirm_id": confirm_data["confirm_id"],
                                        "session_id": session_id
                                    }) + '\n\n'
                                    if "messages" in output:
                                        # 替换为最新消息，而不是追加（避免消息重复累积）
                                        messages_list = list(output["messages"])
                                    continue

                        if isinstance(event.get("data", {}).get("output"), dict):
                            output = event["data"]["output"]
                            if "messages" in output:
                                # 替换为最新消息，而不是追加（避免消息重复累积）
                                messages_list = list(output["messages"])
                            if "resume_data" in output and not output.get("pending_confirmation"):
                                resume_data_result = output["resume_data"]
                            # 更新 pending_confirmation_result（包括 None，用于清除状态）
                            if "pending_confirmation" in output:
                                pending_confirmation_result = output["pending_confirmation"]

                if not accumulated_content:
                    for msg in reversed(messages_list):
                        if isinstance(msg, AIMessage) and msg.content and msg.content != "简历已成功保存到数据库":
                            final_content = str(msg.content)
                            break
                        # 也检查 ToolMessage（如 save_resume_tool 的返回）
                        if isinstance(msg, ToolMessage) and msg.content:
                            final_content = str(msg.content)
                            break
                else:
                    final_content = accumulated_content

            except Exception as e:
                import traceback
                print(f"[Error] 执行错误: {str(e)}")
                print(f"[Error] 异常堆栈: {traceback.format_exc()}")
                final_content = f"抱歉，处理请求时出错: {str(e)}"

            if not final_content:
                final_content = "抱歉，我无法理解您的请求。"

            print(f"[SSE] 准备发送 final 事件, pending_confirmation={pending_confirmation_result is not None}")
            yield 'data: ' + json.dumps({
                "type": "final",
                "content": final_content,
                "session_id": session_id
            }) + '\n\n'

            # 保存消息到数据库（异步执行，不阻塞 SSE 响应）
            import asyncio
            asyncio.create_task(save_state_async(
                db, current_user.id, session_id,
                messages_list, resume_data_result, initial_jd_data, pending_confirmation_result
            ))

            print(f"[SSE] 准备发送 end 事件")
            yield 'data: ' + json.dumps({"type": "end", "session_id": session_id}) + '\n\n'

        return StreamingResponse(stream_response(config), media_type="text/event-stream")

    except Exception as e:
        print(f"聊天接口错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content=f"错误: {str(e)}", status_code=500)


@app.post("/confirm")
async def confirm_endpoint(
    confirm_id: str = Form(""),
    action: str = Form(""),  # "confirm" or "cancel"
    session_id: str = Form(""),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    确认按钮点击接口

    直接处理确认/取消操作，不经过 LLM
    """
    try:
        # 设置全局用户ID
        from . import resume_agent
        resume_agent.current_user_id = current_user.id
        resume_agent.current_task_id = db.info.get("task_id")

        # 从数据库获取 pending_confirmation
        from .database import clear_pending_confirmation, get_pending_confirmation, get_user_resume
        pending_confirmation = get_pending_confirmation(db, current_user.id, session_id)

        if not pending_confirmation:
            return JSONResponse(content={"error": "没有待确认的操作"}, status_code=400)

        if pending_confirmation.get("confirm_id") != confirm_id:
            return JSONResponse(content={"error": "确认ID不匹配"}, status_code=400)

        # 根据操作处理
        if action == "confirm":
            # 从 pending_confirmation 获取修改后的简历数据
            tool_args = pending_confirmation.get("tool_args", {})
            content = tool_args.get("content", "")

            if not content:
                return JSONResponse(content={"error": "没有找到修改后的简历数据"}, status_code=400)

            # 解析 JSON
            import json as json_module
            try:
                updated_resume_data = json_module.loads(content)
                print(f"[Confirm] 解析修改后的简历数据成功，包含 {len(updated_resume_data)} 个顶级字段")
            except json_module.JSONDecodeError as e:
                return JSONResponse(content={"error": f"简历数据格式错误: {str(e)}"}, status_code=400)

            # 保存修改后的简历数据
            from .tools import update_resume
            result = update_resume(
                updated_resume_data,
                user_id=current_user.id,
                task_id=db.info.get("task_id"),
            )
            print(f"[Confirm] 保存结果: {result}")

            # 清除 pending_confirmation 状态
            clear_pending_confirmation(db, current_user.id, session_id)

            return JSONResponse(content={
                "success": True,
                "message": result,
                "action": "saved"
            })

        else:
            # 取消 - 清除 pending_confirmation 状态
            clear_pending_confirmation(db, current_user.id, session_id)

            return JSONResponse(content={
                "success": True,
                "message": "已取消保存操作",
                "action": "cancelled"
            })

    except Exception as e:
        print(f"确认接口错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)



# =============================================================================
# 首次提问 Prompt 模板
# =============================================================================

FIRST_MESSAGE_FOR_CUSTOM_IDENTITY_PROMPT = """
# 角色
你是资深职业顾问，擅长通过对话了解用户的背景并帮助他们打造专业简历。

# 任务
根据用户描述的身份信息，生成 2-4 个针对性的首次提问，帮助开始建立简历。

# 用户身份描述
{custom_identity}

# 分析要点
用户可能描述的身份类型包括但不限于：
- 应届生但非典型毕业时间（如间隔年、创业后回归职场）
- 有工作经验但非标准职场路径（如自由职业、间歇性工作）
- 转行者（如从技术转产品、从医疗转互联网）
- 海归/归国人员
- 其他非标准身份

# 提问原则
1. 基于用户描述的身份信息，理解其独特背景
2. 提问要自然、友好，像朋友聊天一样
3. 关注用户尚未提及但建立简历所需的关键信息
4. 问题要具体，不要太泛泛
5. 适当回应用户描述的身份，表达理解
6. 通用问题方向（根据用户身份调整）：
   - 当前状态/最近在做什么
   - 目标岗位/职业方向
   - 核心技能/优势
   - 项目/工作经历
   - 教育背景

# 输出格式
开场先简短回应用户的身份描述，表达理解。
然后列出 2-4 个问题，对关键信息使用 Markdown 加粗语法。
在所有问题之后，添加一行友好的引导语，例如：
"💡 你可以先选择一个最想聊的告诉我，比如：'我想先说说我的**项目经历**' 或 '先回答我关于**第三个问题**'"
用自然的口语化表达，不要太正式。
不要输出 JSON，不要有任何前缀。
"""

FIRST_MESSAGE_FROM_RESUME_PROMPT = """
# 角色
你是资深职业顾问，擅长通过对话挖掘用户的职业经历和优势。

# 任务
根据用户已解析的简历内容，生成 2-4 个针对性的首次提问，帮助完善简历。

# 简历数据
{resume_data}

# 要求
1. 首先分析简历中的关键信息：
   - 目标岗位（target_position）
   - 教育背景（education）
   - 工作经历（work_experience）
   - 项目经历（project_experience）
   - 技能（skills）
   - 自我评价（self_evaluation）
   - 其他信息（others）

2. 提问原则：
   - 挖掘简历中缺失或描述不完整的重要信息
   - 针对简历中的亮点进行深入了解
   - 提问要有针对性，不能是泛泛的问题
   - 每个问题都要有明确的信息挖掘目标

3. 提问数量：2-4 个问题

4. 提问示例（根据简历内容调整）：
   - 如果缺少项目细节："我看到你提到了[项目名]，能详细说说你在其中担任什么角色、遇到的最大挑战是什么吗？"
   - 如果缺少量化数据："你提到[工作/项目]提升了效率，能具体说说提升了多少吗？"
   - 如果缺少技能应用："你掌握了[技能]，有没有实际应用这个技能解决问题的经历？"

# 输出格式
直接输出提问内容，用自然的口语化表达。
对关键信息使用 Markdown 加粗语法（如 **专业**、**项目** 等）。

在所有问题之后，添加一行友好的引导语，例如：
"💡 你可以先选择一个最想聊的告诉我，比如：'我想先说说我的**项目经历**' 或 '先回答我关于**第三个问题**'"
不要输出 JSON，不要有任何前缀。
"""


class FirstMessageRequest(BaseModel):
    user_type: str
    custom_identity: str
    session_id: str = ""

@app.post("/api/chat/first_message")
async def first_message_endpoint(
    request: FirstMessageRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取自定义身份的首次提问

    - user_type: 'custom' 表示自定义身份
    - custom_identity: 用户描述的身份信息
    """
    require_llm_configured()
    try:
        user_type = request.user_type
        custom_identity = request.custom_identity
        session_id = request.session_id

        if user_type != 'custom':
            return JSONResponse(content={"error": "请使用 custom 类型"}, status_code=400)

        if not custom_identity or not custom_identity.strip():
            return JSONResponse(content={"error": "请输入身份描述"}, status_code=400)

        # 生成会话 ID
        if not session_id:
            session_id = generate_session_id()

        # 填充 prompt
        prompt = FIRST_MESSAGE_FOR_CUSTOM_IDENTITY_PROMPT.format(custom_identity=custom_identity)

        # 调用 LLM 生成首次提问（使用 conversation_llm）
        from langchain_core.prompts import ChatPromptTemplate
        from .resume_agent import conversation_llm

        # 创建提示模板
        prompt_template = ChatPromptTemplate.from_template("{prompt}")
        chain = prompt_template | conversation_llm

        # 调用 LLM
        response = chain.invoke({"prompt": prompt})
        ai_message = response.content

        # 保存 AI 消息到数据库（同时保存到 messages 和 compressed_context）
        from .database import save_conversation, save_conversation_context
        from langchain_core.messages import HumanMessage, AIMessage

        # 保存到 messages 字段
        save_conversation(db, current_user.id, session_id, [
            {"type": "human", "content": f"我的身份描述：{custom_identity}"},
            {"type": "ai", "content": ai_message}
        ])

        # 保存到 compressed_context 字段
        human_msg = HumanMessage(content=f"我的身份描述：{custom_identity}")
        ai_msg = AIMessage(content=ai_message)
        save_conversation_context(
            db,
            current_user.id,
            session_id,
            [
                {"type": "human", "content": f"我的身份描述：{custom_identity}"},
                {"type": "ai", "content": ai_message}
            ]
        )

        return JSONResponse(content={
            "message": ai_message,
            "session_id": session_id
        })

    except Exception as e:
        print(f"首次提问接口错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


class FirstMessageFromResumeRequest(BaseModel):
    session_id: str = ""

@app.post("/api/chat/first_message_from_resume")
async def first_message_from_resume_endpoint(
    request: FirstMessageFromResumeRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    根据已解析的简历内容获取首次提问
    """
    require_llm_configured()
    try:
        session_id = request.session_id

        # 生成会话 ID
        if not session_id:
            session_id = generate_session_id()

        # 从数据库获取用户简历数据
        resume_data = get_user_resume(db, current_user.id)

        if not resume_data:
            return JSONResponse(content={
                "message": "简历已解析完成！我是简历助手，有什么可以帮助你的吗？",
                "session_id": session_id
            })

        # 填充 prompt
        prompt = FIRST_MESSAGE_FROM_RESUME_PROMPT.format(resume_data=json.dumps(resume_data, ensure_ascii=False, indent=2))

        # 调用 LLM 生成首次提问（使用 conversation_llm）
        from langchain_core.prompts import ChatPromptTemplate
        from .resume_agent import conversation_llm

        # 创建提示模板
        prompt_template = ChatPromptTemplate.from_template("{prompt}")
        chain = prompt_template | conversation_llm

        # 调用 LLM
        response = chain.invoke({"prompt": prompt})
        ai_message = response.content

        # 保存 AI 消息到数据库（同时保存到 messages 和 compressed_context）
        from .database import save_conversation, save_conversation_context

        # 保存到 messages 字段
        save_conversation(db, current_user.id, session_id, [
            {"type": "ai", "content": ai_message}
        ])

        # 保存到 compressed_context 字段
        save_conversation_context(
            db,
            current_user.id,
            session_id,
            [
                {"type": "ai", "content": ai_message}
            ]
        )

        return JSONResponse(content={
            "message": ai_message,
            "session_id": session_id
        })

    except Exception as e:
        print(f"简历首次提问接口错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


class SaveAIMessageRequest(BaseModel):
    message: str
    session_id: str = ""

@app.post("/api/chat/save_ai_message")
async def save_ai_message_endpoint(
    request: SaveAIMessageRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    保存 AI 消息到数据库（同时保存到 messages 和 compressed_context）
    """
    try:
        message = request.message
        session_id = request.session_id

        if not message or not message.strip():
            return JSONResponse(content={"error": "消息不能为空"}, status_code=400)

        # 生成会话 ID
        if not session_id:
            session_id = generate_session_id()

        # 保存 AI 消息到数据库
        from .database import save_conversation, save_conversation_context

        # 保存到 messages 字段
        save_conversation(db, current_user.id, session_id, [
            {"type": "ai", "content": message}
        ])

        # 保存到 compressed_context 字段
        save_conversation_context(
            db,
            current_user.id,
            session_id,
            [
                {"type": "ai", "content": message}
            ]
        )

        return JSONResponse(content={
            "success": True,
            "session_id": session_id
        })

    except Exception as e:
        print(f"保存 AI 消息接口错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    from .auth import get_password_hash
    from .database import SessionLocal, cleanup_old_contexts, create_user, get_user_by_email

    print("Resume Assistant 后端服务启动中...")
    print("支持多用户认证和数据库持久化")

    # 启动时清理 7 天未访问的上下文
    try:
        db = SessionLocal()
        deleted = cleanup_old_contexts(db, days=7)
        if deleted:
            print(f"[Context] 已清理 {deleted} 条过期上下文")
        db.close()
    except Exception as e:
        print(f"[Context] 清理过期上下文失败: {e}")

    # 创建本地管理员账号（凭据只从 .env 读取）
    try:
        db = SessionLocal()
        if is_local_mode():
            print(f"[User] 本地模式已启用，使用本地用户: {LOCAL_USER_EMAIL}")
        else:
            admin_email = os.getenv("ADMIN_EMAIL", "").strip()
            admin_password = os.getenv("ADMIN_PASSWORD", "")
            if not admin_email or not admin_password:
                print("[User] 未配置 ADMIN_EMAIL/ADMIN_PASSWORD，跳过管理员初始化")
            else:
                existing_admin = get_user_by_email(db, admin_email)
                if existing_admin:
                    print(f"[User] 管理员账号已存在: {admin_email}")
                else:
                    hashed_pw = get_password_hash(admin_password)
                    create_user(db, admin_email, hashed_pw, invite_code="admin")
                    print(f"[User] 已创建管理员账号: {admin_email}")
        db.close()
    except Exception as e:
        print(f"[User] 创建管理员账号失败: {e}")

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000"))
    )
