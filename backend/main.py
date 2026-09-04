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
import hashlib
import logging
import subprocess
import os
import sys
import uuid
import re
import secrets
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx

from .layout_capabilities import (
    localize_user_visible_layout_text,
    user_visible_layout_internal_identifiers,
)


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

LOGGER = logging.getLogger(__name__)
APP_VERSION = "1.0.0"


def _public_error_response(code: str, message: str, status_code: int = 500):
    """Return a stable Chinese error contract without exposing diagnostics."""
    return JSONResponse(
        content={
            "success": False,
            "code": code,
            "message": message,
            # Compatibility keys for existing frontend callers.
            "error": message,
            "detail": message,
        },
        status_code=status_code,
    )


def _sanitize_user_visible_text(value: object) -> str:
    """Last-line guard for protocol markers and known internal identifiers."""
    text_value = localize_user_visible_layout_text(value)
    text_value = re.sub(r"\[CONFIRM_REPLY:[^\]]+\]", "确认操作", text_value)
    text_value = re.sub(
        r"\b(?:activate_agent_skill|resume_edit|resume_snapshot|resume_coach|request_resume_edit|render_resume_pdf_images)\b",
        "系统能力",
        text_value,
    )
    text_value = re.sub(
        r"\b(?:layout_config|resume_data|jd_data|session_id|confirm_id|request_id)\b",
        "内部信息",
        text_value,
    )
    text_value = re.sub(r"(?:Traceback[\s\S]*|[A-Za-z_]+Error:\s*[^\n]+)", "系统处理异常", text_value)
    return text_value


_STREAM_INTERNAL_IDENTIFIERS = frozenset({
    *user_visible_layout_internal_identifiers(),
    "activate_agent_skill", "resume_edit", "resume_snapshot", "resume_coach",
    "request_resume_edit", "render_resume_pdf_images",
    "layout_config", "resume_data", "jd_data", "session_id", "confirm_id", "request_id",
})


def _stable_user_visible_stream_prefix(value: object) -> str:
    """Withhold an incomplete internal identifier until it can be localized."""
    text_value = str(value or "")
    if text_value.count("`") % 2:
        text_value = text_value[:text_value.rfind("`")]
    marker_match = re.search(r"\[[A-Z_]*(?::[^\]]*)?$", text_value)
    if marker_match and "[CONFIRM_REPLY:".startswith(marker_match.group(0)):
        text_value = text_value[:marker_match.start()]
    token_match = re.search(r"[A-Za-z_][A-Za-z0-9_.-]*$", text_value)
    if token_match:
        token = token_match.group(0)
        if any(identifier != token and identifier.startswith(token) for identifier in _STREAM_INTERNAL_IDENTIFIERS):
            text_value = text_value[:token_match.start()]
    return text_value


def _sanitize_streaming_user_visible_text(value: object) -> str:
    return _sanitize_user_visible_text(_stable_user_visible_stream_prefix(value))

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
# 导入 resume_agent 中的 graph 和 conversation_llm
from . import resume_agent
from .resume_agent import LLM_ENABLED, conversation_llm, graph
from .resume_schema import validate_resume_data
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

# 导入自定义模块
from .database import (
    init_db, get_db, create_user, get_user_by_email,
    database_backend, register_user_with_invite,
    save_user_resume, get_user_resume, save_user_jd, get_user_jd,
    create_invite_code,
    get_parsing_status, set_parsing_status, set_source_page_count, get_user_photo,
    list_resume_projects, create_resume_project, get_resume_project,
    list_project_tasks, list_user_resume_sources, create_resume_task, get_resume_task,
    rename_resume_project, rename_resume_task, switch_base_resume_task,
    CONTEXT_TYPES, create_or_resume_conversation_context,
    list_conversation_contexts,
    get_conversation_context_record,
    close_conversation_context, serialize_conversation_context,
    append_context_event, get_context_by_session,
    delete_resume_project, delete_resume_task, undo_latest_resume_revision,
    get_task_layout_config, save_task_layout_config, attach_source_document,
    delete_unreferenced_source_documents, discard_pending_source_document,
    get_source_document, get_task_source_document,
    get_resume_translation_state, save_resume_translation_state,
    rotate_auth_session, revoke_auth_session,
    acquire_resume_edit_lock, mark_resume_edit_awaiting_confirmation,
    release_resume_edit_lock, get_resume_edit_state,
    get_agent_skill_state, save_agent_skill_state,
)
from .auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_admin, get_current_user, oauth2_scheme, require_multi_user_mode
)
from .datetime_utils import serialize_utc_datetime
from .config import APP_MODE, CORS_ALLOW_ORIGINS, LOCAL_USER_EMAIL, SERVER_HOST, is_local_mode
from .llm_providers import (
    gateway_config,
    get_role_config,
    load_profiles,
    save_role_config,
    serialize_settings,
    validate_role_config,
)
from .llm_gateway import test_chat_connection
from .parser_capability import verify_parser_capabilities
from .model_discovery import discover_models
from .llm_gateway import invoke_document, parse_json_output
from .source_documents import (
    persist_source_document,
    remove_source_document_file,
    source_document_path,
)
from .harness.memory import (
    CompressionState,
    compress_context_with_llm as _compress_context_with_llm,
    notify_compression_complete as _notify_compression_complete,
    wait_for_compression as _wait_for_compression,
)
from .harness.persistence import persist_turn_state
from .harness.observability import harness_metrics
from .layout_config import LAYOUT_SCHEMA_VERSION, default_layout_config, resolve_layout_tokens
from .inline_formatting import plain_inline_text
from .pdf_generator import generate_pdf as _pdf_generator
from .docx_generator import generate_docx as _docx_generator

# Export modules are imported as one startup contract. This prevents a
# long-running backend from mixing an old layout module with newly loaded
# PDF/DOCX modules after source files change on disk.
resolve_layout_tokens()


def _safe_filename_part(value: object, fallback: str, max_length: int = 60) -> str:
    """Return a Windows-safe, readable filename segment."""
    cleaned = plain_inline_text(str(value or "")).strip()
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "_", cleaned).strip(" .")
    return cleaned[:max_length] or fallback


def _resume_export_filename(
    resume_data: dict,
    extension: str,
    project_name: str = "",
    version_name: str = "",
    exported_at: datetime | None = None,
) -> str:
    """Build ``简历组_版本_日期`` export names for both runtime profiles."""
    basics = resume_data.get("basics") if isinstance(resume_data, dict) else {}
    display_name = _safe_filename_part((basics or {}).get("name", ""), "简历")
    project = _safe_filename_part(project_name, display_name)
    version = _safe_filename_part(version_name, "基础版本")
    export_date = (exported_at or datetime.now()).strftime("%Y-%m-%d")
    return f"{project}_{version}_{export_date}.{extension}"


def _export_labels(db: Session, current_user, request_data: dict, resume_data: dict) -> tuple[str, str]:
    """Resolve names from the authorized task, with request values as fallback."""
    project_name = str(request_data.get("project_name") or "")
    version_name = str(request_data.get("version_name") or "")
    task_id = db.info.get("task_id")
    if task_id:
        task = get_resume_task(db, current_user.id, task_id)
        if task:
            version_name = task.title
            project = get_resume_project(db, current_user.id, task.project_id)
            if project:
                project_name = project.title
    if not project_name:
        basics = resume_data.get("basics", {}) if isinstance(resume_data, dict) else {}
        project_name = basics.get("name", "")
    return project_name, version_name


def _persist_local_export(content: bytes, filename: str) -> Path:
    """Atomically persist a local export, adding a numeric collision suffix."""
    output_dir = _local_export_directory()
    base = Path(filename)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".resume-export-",
            suffix=".tmp",
            dir=output_dir,
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)

        for index in range(1000):
            suffix = "" if index == 0 else f"_{index:02d}"
            candidate = output_dir / f"{base.stem}{suffix}{base.suffix}"
            try:
                # A hard link publishes the completed temp file atomically and
                # fails instead of overwriting an export created concurrently.
                os.link(temporary_path, candidate)
                return candidate
            except FileExistsError:
                continue
        raise RuntimeError("同名导出文件过多，请整理 output/resumes 后重试")
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def _local_export_directory() -> Path:
    """Return the configured local export directory and ensure it exists."""
    output_dir = Path(os.getenv("LOCAL_EXPORT_DIR", "./output/resumes")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _open_local_export_directory(output_dir: Path) -> None:
    """Open the trusted local export directory with the operating-system shell."""
    if os.name == "nt":
        os.startfile(str(output_dir))
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen(
        [command, str(output_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


_RENDER_STYLE_KEYS = frozenset({
    "marginTop", "marginBottom", "marginLeft", "marginRight",
    "moduleMargin", "lineHeight", "fontSize", "pageMode",
    "sourcePageCount", "pageBreakBefore",
})
_RENDER_STYLE_NUMERIC_KEYS = frozenset({
    "marginTop", "marginBottom", "marginLeft", "marginRight",
    "moduleMargin", "lineHeight", "fontSize", "sourcePageCount",
})


def _parse_render_style(raw_style: str | dict | None) -> dict:
    """Parse the ephemeral preview style sent with a visual chat request.

    Only the fields used by the shared PDF/DOCX renderer are accepted. The
    value is request-scoped and never persisted as resume content.
    """
    if isinstance(raw_style, dict):
        candidate = raw_style
    elif isinstance(raw_style, str) and raw_style.strip():
        try:
            candidate = json.loads(raw_style)
        except (TypeError, ValueError):
            return {}
    else:
        return {}
    if not isinstance(candidate, dict):
        return {}

    parsed = {}
    for key in _RENDER_STYLE_KEYS:
        if key not in candidate:
            continue
        value = candidate[key]
        if key in _RENDER_STYLE_NUMERIC_KEYS:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number != number or number in (float("inf"), float("-inf")):
                continue
            parsed[key] = int(number) if key == "sourcePageCount" else number
        elif key == "pageMode":
            parsed[key] = "auto"
        elif key == "pageBreakBefore" and isinstance(value, str):
            parsed[key] = value[:80]
    return parsed

# PDF 生成器 - 懒加载（在 API 调用时才导入）
# =============================================================================
# 上下文压缩状态管理
# =============================================================================

compression_state = CompressionState()

def wait_for_compression():
    """等待当前压缩完成（如果正在压缩）"""
    return _wait_for_compression(compression_state)


def notify_compression_complete():
    """通知压缩完成，处理等待中的请求"""
    _notify_compression_complete(compression_state)


def generate_session_id() -> str:
    """生成唯一会话 ID"""
    return str(uuid.uuid4())


# =============================================================================
# Pydantic Models
# =============================================================================

class RegisterRequest(BaseModel):
    """注册请求"""
    email: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    invite_code: str = Field(min_length=1, max_length=50)


def _is_email_identifier(value: object) -> bool:
    """Return whether an identifier satisfies the public user email contract."""
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(value or "").strip()))


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
    is_active: bool
    is_admin: bool


class SaveResumeRequest(BaseModel):
    """保存简历请求"""
    resume_data: dict


class TranslateResumeRequest(BaseModel):
    source_language: str = "zh"
    target_language: str = "en"


class CreateProjectRequest(BaseModel):
    """创建简历项目请求"""
    title: str = "未命名简历组"


class CreateTaskRequest(BaseModel):
    """创建岗位任务请求"""
    title: str = "新岗位版本"
    copy_base_resume: bool = True
    source_task_id: str | None = None
    jd_data: dict | None = None


class RenameTitleRequest(BaseModel):
    """Rename a project or task without changing its resume content."""
    title: str


class ConversationContextRequest(BaseModel):
    context_type: str
    title: str | None = None


class SaveLayoutRequest(BaseModel):
    layout_config: dict


class ResetLayoutRequest(BaseModel):
    section: str = "all"


class DirectReplaceRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=36)
    scope: str = Field(min_length=1, max_length=50)
    original_text: str = Field(min_length=1, max_length=4000)
    target_text: str = Field(max_length=4000)


class LLMSettingsRequest(BaseModel):
    """Role-specific LLM configuration. Empty api_key preserves the stored key."""
    role: str = "chat"
    model: str
    base_url: str
    api_key: str | None = None
    adapter: str = "auto"
    verified: bool = False
    capabilities: dict = Field(default_factory=dict)


class LLMModelsRequest(BaseModel):
    """Best-effort model listing; api_key may reuse the stored provider key."""
    role: str = "chat"
    base_url: str
    api_key: str | None = None


class ConfirmResumeImportRequest(BaseModel):
    resume_data: dict
    source_page_count: int = 1
    source_document_token: str | None = None


def serialize_task(task):
    from .layout_config import normalize_layout_config
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
        "source_page_count": max(1, int(task.source_page_count or 1)),
        "has_source_document": bool(task.source_document_id),
        "layout_config": normalize_layout_config(task.layout_config),
        "created_at": serialize_utc_datetime(task.created_at),
        "updated_at": serialize_utc_datetime(task.updated_at),
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
        "created_at": serialize_utc_datetime(project.created_at),
        "updated_at": serialize_utc_datetime(project.updated_at),
    }


# =============================================================================
# LLM 上下文压缩
# =============================================================================

async def compress_context_with_llm(messages, max_summary_length=1000):
    """Compatibility wrapper for the extracted legacy compression behavior."""
    return await _compress_context_with_llm(
        messages,
        conversation_llm,
        max_summary_length=max_summary_length,
    )


# =============================================================================
# FastAPI 应用
# =============================================================================

app = FastAPI(title="ResumeBranch API", version=APP_VERSION)
_edit_preview_guard = asyncio.Lock()


def require_llm_configured():
    """Return a clear local-mode error instead of attempting an unauthenticated call."""
    if not resume_agent.LLM_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="LLM_API_KEY 尚未配置；主简历和数据库功能可继续使用。"
        )

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=bool(CORS_ALLOW_ORIGINS),
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
        "local_export_enabled": is_local_mode(),
        "database_backend": database_backend,
    }


def require_local_settings():
    """Keep machine-local secrets out of hosted or multi-user deployments."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="本地设置仅在本地模式可用")


def require_llm_settings_access(current_user=Depends(get_current_user)):
    """Allow machine-local configuration or a multi-user administrator."""
    if not is_local_mode() and not bool(current_user.is_admin):
        raise HTTPException(status_code=403, detail="仅管理员可以调整 API 设置")


@app.post("/local/exports/open", dependencies=[Depends(require_local_settings)])
async def open_local_exports(current_user=Depends(get_current_user)):
    """Open the configured export folder on the machine running local mode."""
    output_dir = _local_export_directory()
    try:
        _open_local_export_directory(output_dir)
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="无法打开导出文件夹，请手动打开项目下的 output/resumes",
        ) from exc
    return {"opened": True, "path": str(output_dir)}


@app.get("/settings/llm", dependencies=[Depends(require_llm_settings_access)])
async def get_llm_settings(current_user=Depends(get_current_user)):
    """Return all provider profiles without exposing stored API keys."""
    return serialize_settings()


@app.get("/settings/harness-metrics")
async def get_harness_metrics(current_user=Depends(get_current_user)):
    """Expose process-local, data-free counters for operational monitoring."""
    return harness_metrics.snapshot()


@app.post("/settings/llm/test", dependencies=[Depends(require_llm_settings_access)])
async def test_llm_settings(
    request: LLMSettingsRequest,
    current_user=Depends(get_current_user),
):
    model = request.model.strip()
    base_url = request.base_url.strip()
    stored = get_role_config(request.role)
    api_key = (request.api_key or stored.get("api_key", "")).strip()
    try:
        validate_role_config(request.role, model, base_url, request.adapter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="配置内容不完整或格式不正确") from exc
    if not api_key:
        raise HTTPException(status_code=400, detail="请填写该服务商的 API Key")

    try:
        candidate = gateway_config(
            request.role,
            api_key_override=api_key,
            base_url=base_url,
            model=model,
            adapter=request.adapter,
        )
        result = (
            await verify_parser_capabilities(candidate)
            if request.role == "parser"
            else await test_chat_connection(candidate)
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="连接超时，请检查接口地址或网络") from exc
    except ValueError as exc:
        LOGGER.warning("LLM 能力测试被拒绝: %s", exc)
        raise HTTPException(status_code=400, detail="当前模型或接口不支持所需能力") from exc
    except Exception as exc:
        LOGGER.warning("LLM 连接测试失败: %s", exc)
        raise HTTPException(status_code=400, detail="连接失败，请检查模型、接口地址和密钥") from exc
    return {"model": model, **result}


@app.post("/settings/llm/models", dependencies=[Depends(require_llm_settings_access)])
async def list_llm_models(
    request: LLMModelsRequest,
    current_user=Depends(get_current_user),
):
    if request.role not in {"chat", "parser"}:
        raise HTTPException(status_code=400, detail="配置用途不受支持")
    stored = get_role_config(request.role)
    api_key = (request.api_key or stored.get("api_key", "")).strip()
    try:
        return await discover_models(request.base_url, api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/settings/llm", dependencies=[Depends(require_llm_settings_access)])
async def update_llm_settings(
    request: LLMSettingsRequest,
    current_user=Depends(get_current_user),
):
    global LLM_ENABLED, conversation_llm

    role = request.role.strip()
    model = request.model.strip()
    base_url = request.base_url.strip()
    try:
        validate_role_config(role, model, base_url, request.adapter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_role_config(role, {
        "model": model,
        "base_url": base_url,
        "api_key": (request.api_key or "").strip(),
        "adapter": request.adapter,
        "verified": bool(request.verified),
        "capabilities": request.capabilities if request.verified else {},
        "verified_at": datetime.now().isoformat() if request.verified else None,
    })

    runtime = {"configured": True}
    if role == "chat":
        runtime = resume_agent.reload_llm_config()
        # Keep legacy references in this module in sync for context compression.
        LLM_ENABLED = resume_agent.LLM_ENABLED
        conversation_llm = resume_agent.conversation_llm
    return {
        **serialize_settings(),
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
    email = request.email.strip().lower()
    if not _is_email_identifier(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    try:
        user = register_user_with_invite(
            db,
            email,
            get_password_hash(request.password),
            request.invite_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="模型列表查询失败，请检查接口地址和密钥") from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="邮箱或邀请码已被使用") from exc

    # 生成 Token
    auth_session_id = rotate_auth_session(db, user.id)
    token = create_access_token({"sub": user.email, "sid": auth_session_id})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={
            "id": user.id,
            "email": user.email,
            "created_at": user.created_at.isoformat(),
            "is_active": bool(user.is_active),
            "is_admin": bool(user.is_admin),
        }
    )


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    dependencies=[Depends(require_multi_user_mode)],
)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    用户登录

    - 普通用户使用邮箱；管理员也可使用专用账号
    - 返回 JWT Token
    """
    identifier = form_data.username.strip().lower()
    user = get_user_by_email(db, identifier)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱、管理员账号或密码错误")

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="邮箱、管理员账号或密码错误")

    if not _is_email_identifier(identifier) and not user.is_admin:
        raise HTTPException(status_code=401, detail="普通用户必须使用邮箱登录")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")

    auth_session_id = rotate_auth_session(db, user.id)
    token = create_access_token({"sub": user.email, "sid": auth_session_id})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={
            "id": user.id,
            "email": user.email,
            "created_at": user.created_at.isoformat(),
            "is_active": bool(user.is_active),
            "is_admin": bool(user.is_admin),
        }
    )


@app.get("/auth/me", response_model=UserResponse)
async def get_me(current_user = Depends(get_current_user)):
    """
    获取当前用户信息
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        created_at=current_user.created_at,
        is_active=bool(current_user.is_active),
        is_admin=bool(current_user.is_admin),
    )


@app.post("/auth/logout", dependencies=[Depends(require_multi_user_mode)])
async def logout(
    token: str | None = Depends(oauth2_scheme),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from .auth import decode_token
    payload = decode_token(token or "") or {}
    revoke_auth_session(db, current_user.id, str(payload.get("sid") or ""))
    return {"success": True}


@app.get("/auth/invite-codes", dependencies=[Depends(require_multi_user_mode)])
async def list_invites(current_user = Depends(get_current_admin), db: Session = Depends(get_db)):
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
async def create_invite(request: Request, current_user = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    生成邀请码（需要登录）
    """
    import string

    # 解析请求体
    try:
        body = await request.json()
        count = max(1, min(int(body.get('count', 1)), 20))
    except (TypeError, ValueError, json.JSONDecodeError):
        count = 1

    codes = []
    for _ in range(count):
        for _attempt in range(10):
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
            try:
                create_invite_code(db, code)
                break
            except IntegrityError:
                db.rollback()
        else:
            raise HTTPException(status_code=503, detail="邀请码生成失败，请重试")
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


def _validated_rename_title(value: str) -> str:
    title = str(value or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="名称不能为空")
    if len(title) > 120:
        raise HTTPException(status_code=400, detail="名称不能超过 120 个字符")
    return title


@app.patch("/projects/{project_id}")
async def rename_project(
    project_id: str,
    request: RenameTitleRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Rename a resume group without changing any resume data."""
    title = _validated_rename_title(request.title)
    project = rename_resume_project(db, current_user.id, project_id, title)
    if not project:
        raise HTTPException(status_code=404, detail="简历组不存在")
    return serialize_project(project, len(list_project_tasks(db, current_user.id, project_id)))


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


@app.get("/resume-sources")
async def get_resume_sources(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Return all of the current user's resumes, grouped by project in the UI."""
    projects = {project.id: project for project in list_resume_projects(db, current_user.id)}
    sources = []
    for task in list_user_resume_sources(db, current_user.id):
        project = projects.get(task.project_id)
        item = serialize_task(task)
        item["project_title"] = project.title if project else "未命名简历组"
        sources.append(item)
    return sources


@app.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not delete_resume_project(db, current_user.id, project_id):
        raise HTTPException(status_code=404, detail="简历组不存在")
    for storage_key in delete_unreferenced_source_documents(db, current_user.id):
        remove_source_document_file(storage_key)
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
        source_task_id=request.source_task_id,
        jd_data=request.jd_data,
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


@app.get("/tasks/{task_id}/contexts")
async def get_task_contexts(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """List the main conversation and mission contexts for one resume version."""
    task = get_resume_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    contexts = list_conversation_contexts(db, current_user.id, task_id)
    return {
        "contexts": [serialize_conversation_context(context) for context in contexts],
        "edit_state": get_resume_edit_state(db, current_user.id, task_id),
    }


@app.post("/tasks/{task_id}/contexts")
async def start_task_context(
    task_id: str,
    request: ConversationContextRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Resume the active command context or create a fresh mission."""
    normalized_type = str(request.context_type or "").strip().lower()
    if normalized_type not in CONTEXT_TYPES - {"main"}:
        raise HTTPException(status_code=400, detail="不支持的任务类型")
    task = get_resume_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    previous = next(
        (
            context for context in list_conversation_contexts(db, current_user.id, task_id)
            if context.context_type == normalized_type and context.status == "active"
        ),
        None,
    )
    context = create_or_resume_conversation_context(
        db,
        current_user.id,
        task_id,
        normalized_type,
        title=request.title,
    )
    if not context:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    if previous is None:
        append_context_event(db, current_user.id, task_id, context, "started")
    return {"context": serialize_conversation_context(context), "resumed": previous is not None}


@app.delete("/tasks/{task_id}/contexts/{context_id}")
async def close_task_context(
    task_id: str,
    context_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Close a mission context and clear its pending mutable state."""
    task = get_resume_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    context = get_conversation_context_record(db, current_user.id, context_id)
    if not context or context.task_id != task_id:
        raise HTTPException(status_code=404, detail="任务会话不存在")
    try:
        closed = close_conversation_context(db, current_user.id, context_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="配置内容不完整或格式不正确") from exc
    append_context_event(db, current_user.id, task_id, context, "closed")
    return {"success": True, "context": serialize_conversation_context(closed)}


@app.patch("/tasks/{task_id}")
async def rename_task(
    task_id: str,
    request: RenameTitleRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Rename a base resume or a job-specific version."""
    title = _validated_rename_title(request.title)
    task = rename_resume_task(db, current_user.id, task_id, title)
    if not task:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    return serialize_task(task)


@app.post("/tasks/{task_id}/set-as-base")
async def set_task_as_base(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Switch a version into the project's base-resume role."""
    result, base_task, former_base_task = switch_base_resume_task(db, current_user.id, task_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="简历版本不存在")
    if result == "base_missing":
        raise HTTPException(status_code=409, detail="当前项目缺少主简历")
    project = get_resume_project(db, current_user.id, base_task.project_id)
    return {
        "success": True,
        "base_task": serialize_task(base_task),
        "former_base_task": serialize_task(former_base_task) if former_base_task else None,
        "project": serialize_project(
            project,
            len(list_project_tasks(db, current_user.id, base_task.project_id)),
        ) if project else None,
    }


@app.get("/tasks/{task_id}/source-document")
async def get_task_source_document_endpoint(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    document = get_task_source_document(db, current_user.id, task_id)
    if not document or document.status != "ready":
        raise HTTPException(status_code=404, detail="当前简历没有可查看的原版")
    try:
        path = source_document_path(document.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="原版文件不存在，请重新导入") from exc
    return FileResponse(
        path,
        media_type=document.mime_type,
        filename=document.original_filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, max-age=60",
            "X-Source-Filename": quote(document.original_filename),
        },
    )


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
        raise HTTPException(status_code=400, detail="主简历不能单独删除，请删除整份简历组")
    for storage_key in delete_unreferenced_source_documents(db, current_user.id):
        remove_source_document_file(storage_key)
    return {"success": True}


@app.post("/tasks/{task_id}/undo")
async def undo_task_resume_change(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Undo the latest assistant-applied revision when it is still current."""
    result, resume_data, layout_config = undo_latest_resume_revision(db, current_user.id, task_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="岗位版本不存在")
    if result == "no_revision":
        raise HTTPException(status_code=409, detail="没有可以撤回的修改")
    if result == "conflict":
        raise HTTPException(status_code=409, detail="简历在本次修改后又发生了变化，无法直接撤回")
    return {
        "success": True,
        "message": "已撤回本次修改",
        "resume_data": resume_data,
        "layout_config": layout_config,
    }


@app.get("/tasks/{task_id}/layout")
async def get_task_layout(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    config = get_task_layout_config(db, current_user.id, task_id)
    if config is None:
        raise HTTPException(status_code=404, detail="岗位版本不存在")
    return {"layout_config": config}


@app.put("/tasks/{task_id}/layout")
async def put_task_layout(
    task_id: str,
    request: SaveLayoutRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    config = save_task_layout_config(db, current_user.id, task_id, request.layout_config)
    if config is None:
        raise HTTPException(status_code=404, detail="岗位版本不存在")
    return {"success": True, "layout_config": config}


@app.post("/tasks/{task_id}/layout/reset")
async def reset_task_layout(
    task_id: str,
    request: ResetLayoutRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    from .layout_config import reset_layout_section
    current = get_task_layout_config(db, current_user.id, task_id)
    if current is None:
        raise HTTPException(status_code=404, detail="岗位版本不存在")
    if request.section in {"", "all", None}:
        config = save_task_layout_config(db, current_user.id, task_id, default_layout_config())
        return {"success": True, "layout_config": config}
    config = save_task_layout_config(
        db, current_user.id, task_id, reset_layout_section(current, request.section)
    )
    return {"success": True, "layout_config": config}


_DIRECT_REPLACE_SCOPES = {
    "all": ((),),
    "basics": (("basics",),),
    "education": (("education",), ("education_supplement",)),
    "honors": (("honors",),),
    "publications": (("publications",),),
    "research_interests": (("research_interests",),),
    "skills": (("others", "skills"),),
    "work_experience": (("work_experience",),),
    "project_experience": (("project_experience",),),
    "custom_sections": (("custom_sections",),),
    "certificates_languages": (
        ("others", "certificates"),
        ("others", "languages"),
        ("others", "field_labels"),
    ),
    "self_evaluation": (("self_evaluation",),),
}


def _direct_replace_scope_paths(scope: str, current: dict) -> tuple[tuple[str | int, ...], ...]:
    if scope in _DIRECT_REPLACE_SCOPES:
        return _DIRECT_REPLACE_SCOPES[scope]
    match = re.fullmatch(r"custom_sections:(\d+)", scope)
    if not match:
        raise HTTPException(status_code=400, detail="不支持的作用区域")
    index = int(match.group(1))
    sections = current.get("custom_sections")
    if not isinstance(sections, list) or index >= len(sections):
        raise HTTPException(status_code=400, detail="所选自定义栏目当前不存在")
    return (("custom_sections", index),)


def _direct_replace_path_value(current: dict, path: tuple[str | int, ...]):
    value = current
    for part in path:
        if isinstance(part, int):
            if not isinstance(value, list) or part >= len(value):
                return None
            value = value[part]
        else:
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
    return value


def _set_direct_replace_path(current: dict, path: tuple[str | int, ...], value) -> dict:
    if not path:
        return value
    parent = current
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = value
    return current


def _replace_unique_resume_text(value, original: str, target: str) -> tuple[object, int]:
    if isinstance(value, str):
        count = value.count(original)
        return (value.replace(original, target), count) if count else (value, 0)
    if isinstance(value, list):
        result = []
        total = 0
        for item in value:
            replaced, count = _replace_unique_resume_text(item, original, target)
            result.append(replaced)
            total += count
        return result, total
    if isinstance(value, dict):
        result = {}
        total = 0
        for key, item in value.items():
            replaced, count = _replace_unique_resume_text(item, original, target)
            result[key] = replaced
            total += count
        return result, total
    return value, 0


@app.post("/tasks/{task_id}/direct-replace-preview")
async def direct_replace_preview(
    task_id: str,
    request: DirectReplaceRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Build one deterministic literal-replacement preview without an LLM call."""
    task = get_resume_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    if request.session_id != task.session_id:
        context = get_context_by_session(db, current_user.id, task_id, request.session_id)
        if not context or context.status != "active":
            raise HTTPException(status_code=409, detail="当前任务会话不可用")
    original = request.original_text.strip()
    target = request.target_text.strip()
    if not original:
        raise HTTPException(status_code=400, detail="原内容不能为空")
    current = deepcopy(task.resume_data or {})
    scope_paths = _direct_replace_scope_paths(request.scope, current)
    available_paths = [
        path for path in scope_paths
        if _direct_replace_path_value(current, path) is not None
    ]
    if not available_paths:
        raise HTTPException(status_code=400, detail="所选区域当前没有可修改内容")
    candidate = deepcopy(current)
    count = 0
    for path in available_paths:
        subtree = _direct_replace_path_value(current, path)
        replaced, subtree_count = _replace_unique_resume_text(subtree, original, target)
        count += subtree_count
        candidate = _set_direct_replace_path(candidate, path, replaced)
    if count == 0:
        raise HTTPException(status_code=400, detail="所选区域中未找到完全一致的原内容")
    if count > 1:
        raise HTTPException(status_code=409, detail="所选区域中找到多处相同内容，请缩小作用区域或补充更完整的原文")

    from .database import (
        find_task_pending_confirmation,
        get_conversation_context,
        save_conversation_context,
    )
    request_id = str(uuid.uuid4())
    async with _edit_preview_guard:
        if find_task_pending_confirmation(db, current_user.id, task_id) or not acquire_resume_edit_lock(
            db, current_user.id, task_id, request.session_id, request_id
        ):
            raise HTTPException(status_code=409, detail="当前简历存在正在处理的修改，请先完成或取消后再请求")
        state = resume_agent.AgentState(
            resume_data=current,
            layout_data=task.layout_config or {},
            user_id=current_user.id,
            task_id=task_id,
            request_id=request_id,
            context_id=request.session_id,
        )
        try:
            pending = resume_agent.make_pending_confirmation(state, candidate, task.layout_config or {})
        except ValueError as exc:
            release_resume_edit_lock(
                db, current_user.id, task_id,
                owner_session_id=request.session_id, request_id=request_id,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        pending["owner_session_id"] = request.session_id
        pending["request_id"] = state.request_id
        pending["source"] = "direct_replace"
        try:
            compressed_context = get_conversation_context(db, current_user.id, request.session_id)
            save_conversation_context(
                db,
                current_user.id,
                request.session_id,
                compressed_context,
                pending,
            )
            mark_resume_edit_awaiting_confirmation(
                db, current_user.id, task_id, request.session_id, request_id
            )
        except Exception:
            release_resume_edit_lock(
                db, current_user.id, task_id,
                owner_session_id=request.session_id, request_id=request_id,
            )
            raise
    return {
        "success": True,
        "content": pending["content"],
        "options": pending["options"],
        "changes": pending["changes"],
        "resume_candidate": pending["resume_candidate"],
        "layout_candidate": pending["layout_candidate"],
        "confirm_id": pending["confirm_id"],
        "source": "direct_replace",
    }


@app.post("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "version": APP_VERSION,
        "app_mode": APP_MODE,
        "layout_schema_version": LAYOUT_SCHEMA_VERSION,
        "export_contract": "ready",
    }


@app.post("/load_resume")
async def load_resume_endpoint(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    加载当前用户的简历数据
    """
    try:
        resume_data = get_user_resume(db, current_user.id)

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
            LOGGER.warning("读取解析状态失败，使用默认状态: %s", statusError)
            parsing_status = "none"

        if isinstance(resume_data, dict) and "error" in resume_data:
            return JSONResponse(content={}, status_code=500)
        return JSONResponse(content={
            **resume_data,
            "parsing_status": parsing_status
        })
    except Exception:
        LOGGER.exception("读取简历失败")
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
        return _public_error_response("RESUME_SAVE_FAILED", "简历保存失败，请稍后重试。")


@app.post("/translate_resume")
async def translate_resume_endpoint(
    request: TranslateResumeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Translate the active resume through a dedicated, cache-aware workflow."""
    from .resume_changes import resume_digest
    from .resume_translation import translate_resume

    try:
        source_data = get_user_resume(db, current_user.id)
        if not source_data:
            raise HTTPException(status_code=400, detail="当前没有可翻译的简历内容")
        current_digest = resume_digest(source_data)
        state = get_resume_translation_state(db, current_user.id)
        if state and current_digest in {
            state.source_digest,
            resume_digest(state.translated_data or {}),
        }:
            result = {
                "resume_data": state.translated_data,
                "cache_hits": 0,
                "new_translations": 0,
                "total_translatable": 0,
                "full_snapshot_reused": True,
            }
        else:
            result = await translate_resume(
                db,
                current_user.id,
                source_data,
                source_language=request.source_language,
                target_language=request.target_language,
            )
            save_resume_translation_state(
                db,
                current_user.id,
                source_digest=current_digest,
                source_data=source_data,
                translated_data=result["resume_data"],
            )
            result["full_snapshot_reused"] = False
        save_user_resume(db, current_user.id, result["resume_data"])
        return {"success": True, **result}
    except HTTPException:
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        LOGGER.warning("简历翻译失败: %s", exc)
        raise HTTPException(status_code=502, detail="简历翻译失败，请检查模型配置后重试") from exc


@app.post("/restore_resume_translation")
async def restore_resume_translation_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Restore the durable Chinese source snapshot for the active resume."""
    from .resume_changes import resume_digest
    from .resume_translation import restore_from_translation_memory

    try:
        current_data = get_user_resume(db, current_user.id)
        state = get_resume_translation_state(db, current_user.id)
        if state and state.source_data:
            source_data = state.source_data
            restored_fields = 0
        else:
            recovered = restore_from_translation_memory(db, current_user.id, current_data)
            source_data = recovered["resume_data"]
            restored_fields = recovered["restored_fields"]
            if restored_fields == 0:
                raise HTTPException(status_code=409, detail="没有可恢复的中文翻译基线")
            save_resume_translation_state(
                db,
                current_user.id,
                source_digest=resume_digest(source_data),
                source_data=source_data,
                translated_data=current_data,
            )
        save_user_resume(db, current_user.id, source_data)
        return {
            "success": True,
            "resume_data": source_data,
            "restored_fields": restored_fields,
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        LOGGER.warning("恢复简历翻译失败: %s", exc)
        raise HTTPException(status_code=500, detail="中文简历恢复失败，请稍后重试") from exc


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
        return _public_error_response("JD_LOAD_FAILED", "岗位信息加载失败，请稍后重试。")


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
        return _public_error_response("JD_SAVE_FAILED", "岗位信息保存失败，请稍后重试。")


def filter_images_from_message_dict(msg_dict):
    """过滤消息字典中的图片内容"""
    if not isinstance(msg_dict, dict):
        return msg_dict

    filtered_message = dict(msg_dict)
    content = filtered_message.get('content', '')

    # 如果 content 是列表（多模态内容），过滤掉图片
    if isinstance(content, list):
        filtered = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                filtered.append(item)
            # 跳过 type == 'image_url' 的图片
        if filtered:
            filtered_message['content'] = filtered
        else:
            filtered_message['content'] = ''

    return filtered_message


def _message_dict_has_text(message: dict) -> bool:
    content = message.get('content', '')
    if isinstance(content, list):
        return any(
            isinstance(item, dict)
            and item.get('type') == 'text'
            and str(item.get('text', '') or '').strip()
            for item in content
        )
    return bool(str(content or '').strip())


def sanitize_conversation_message_dicts(messages):
    """Keep durable visible messages and discard empty stream/tool artifacts."""
    sanitized = []
    for raw_message in messages or []:
        if not isinstance(raw_message, dict):
            continue
        message = filter_images_from_message_dict(raw_message)
        if message.get('streaming') is True:
            continue
        role = str(message.get('role') or message.get('type') or '').strip().lower()
        if role in {'assistant', 'ai', 'human', 'user', 'system', 'systemmessage'}:
            if not _message_dict_has_text(message):
                continue
        sanitized.append(message)
    return sanitized


@app.post("/save_conversation")
async def save_conversation_endpoint(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    保存对话历史
    """
    try:
        request_data = await request.json()
        session_id = request_data.get('session_id', 'default')
        messages = request_data.get('messages', [])

        # 图片、流式占位符和空 assistant 都不是可持久化的对话历史。
        filtered_messages = sanitize_conversation_message_dicts(messages)

        from .database import save_conversation
        save_conversation(db, current_user.id, session_id, filtered_messages)

        return JSONResponse(content={"success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _public_error_response("CONVERSATION_SAVE_FAILED", "对话保存失败，请稍后重试。")


@app.post("/load_conversation")
async def load_conversation_endpoint(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    加载对话历史
    """
    try:
        request_data = await request.json()
        session_id = request_data.get('session_id', 'default')

        from .database import get_conversation
        messages = sanitize_conversation_message_dicts(
            get_conversation(db, current_user.id, session_id)
        )

        return JSONResponse(content=messages)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _public_error_response("CONVERSATION_LOAD_FAILED", "对话加载失败，请稍后重试。")


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
        return _public_error_response("JD_PARSE_FAILED", "岗位描述识别失败，请稍后重试。")


@app.post("/api/resume/parse_and_save")
async def parse_and_save_resume_endpoint(
    file: UploadFile = File(...),
    draft_only: bool = Form(False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    解析简历图片并保存（首次上传流程）
    支持 multipart/form-data 上传文件
    """
    source_document = None
    try:
        if not file:
            return JSONResponse(content={"success": False, "error": "未收到文件"}, status_code=400)

        # 验证文件类型
        content_type = file.content_type
        if not content_type.startswith('image/') and content_type != 'application/pdf':
            return JSONResponse(content={"success": False, "error": "只支持图片或PDF文件"}, status_code=400)

        parser_profile = get_role_config("parser")
        if not parser_profile.get("api_key") or not parser_profile.get("base_url") or not parser_profile.get("model"):
            return JSONResponse(
                content={"success": False, "error": "尚未配置解析 API，请先在 API 设置的“解析 API”中完成配置和测试。", "error_code": "parser_not_configured"},
                status_code=409,
            )
        if not parser_profile.get("verified"):
            return JSONResponse(
                content={"success": False, "error": "解析 API 尚未通过 PDF 与图片能力测试，请先完成测试后再导入。", "error_code": "parser_not_verified"},
                status_code=409,
            )

        file_content = await file.read()
        from .source_documents import detect_source_page_count
        source_page_count = detect_source_page_count(file_content, content_type)

        from .resume_agent import build_resume_extract_prompt
        from .import_contract import finalize_import_resume

        # 设置解析状态为进行中
        set_parsing_status(db, current_user.id, "parsing")

        schema_prompt = build_resume_extract_prompt()
        parser_gateway = gateway_config("parser")
        raw = await invoke_document(
            parser_gateway,
            content=file_content,
            mime_type=content_type,
            filename=file.filename or ("resume.pdf" if content_type == "application/pdf" else "resume.png"),
            prompt=schema_prompt,
            timeout=150,
        )
        resume_data, import_quality = finalize_import_resume(parse_json_output(raw))

        for storage_key in delete_unreferenced_source_documents(db, current_user.id):
            remove_source_document_file(storage_key)
        source_document = persist_source_document(
            db,
            current_user.id,
            file_content,
            content_type,
            file.filename or ("resume.pdf" if content_type == "application/pdf" else "resume.png"),
        )

        if not draft_only:
            save_user_resume(db, current_user.id, resume_data)
            set_source_page_count(db, current_user.id, source_page_count)
            attached = attach_source_document(db, current_user.id, source_document.id)
            if attached:
                for storage_key in delete_unreferenced_source_documents(db, current_user.id):
                    remove_source_document_file(storage_key)
            else:
                storage_key = discard_pending_source_document(db, current_user.id, source_document.id)
                if storage_key:
                    remove_source_document_file(storage_key)
                source_document = None
        # 设置解析状态为完成
        set_parsing_status(db, current_user.id, "completed")

        return JSONResponse(content={
            "success": True,
            "resume_data": resume_data,
            "source_page_count": source_page_count,
            "source_fingerprint": hashlib.sha256(file_content).hexdigest()[:12],
            "parser_adapter": parser_gateway.resolved_adapter(),
            "parser_transport": {
                "gemini_native": "Gemini Native（PDF 原生）",
                "openai_responses": "OpenAI Responses（文件输入）",
                "openai_chat": "OpenAI Chat（图片视觉）",
            }.get(parser_gateway.resolved_adapter(), parser_gateway.resolved_adapter()),
            "import_quality": import_quality.as_dict(),
            "source_document_token": source_document.id if source_document and draft_only else None,
            "has_source_document": bool(source_document and not draft_only),
            "draft": bool(draft_only),
            "message": "简历解析完成" if draft_only else "简历解析并保存成功"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 解析失败
        set_parsing_status(db, current_user.id, "failed")
        error_message = "解析失败，请检查解析服务配置后重试。"
        if isinstance(e, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
            error_message = "解析 API 响应超时，请稍后重试；若持续出现，请更换解析模型或接口。"
        if source_document and source_document.status == "pending":
            storage_key = discard_pending_source_document(db, current_user.id, source_document.id)
            if storage_key:
                remove_source_document_file(storage_key)
        return JSONResponse(content={"success": False, "error": error_message}, status_code=500)


@app.post("/api/resume/confirm_import")
async def confirm_resume_import_endpoint(
    request: ConfirmResumeImportRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    from .import_contract import finalize_import_resume
    try:
        resume_data, _ = finalize_import_resume(request.resume_data)
        if request.source_document_token:
            document = get_source_document(db, current_user.id, request.source_document_token)
            if not document or document.status != "pending":
                raise ValueError("原版确认凭证已失效，请重新选择文件")
        save_user_resume(db, current_user.id, resume_data)
        page_count = max(1, min(1000, int(request.source_page_count or 1)))
        set_source_page_count(db, current_user.id, page_count)
        attached = None
        if request.source_document_token:
            attached = attach_source_document(db, current_user.id, request.source_document_token)
            if not attached:
                raise ValueError("原版无法绑定到当前简历，请重新导入")
            for storage_key in delete_unreferenced_source_documents(db, current_user.id):
                remove_source_document_file(storage_key)
        set_parsing_status(db, current_user.id, "completed")
        return {
            "success": True,
            "resume_data": resume_data,
            "source_page_count": page_count,
            "has_source_document": bool(attached),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"导入草稿校验失败：{exc}") from exc


@app.delete("/api/resume/import_drafts/{document_id}")
async def discard_resume_import_draft_endpoint(
    document_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    storage_key = discard_pending_source_document(db, current_user.id, document_id)
    if not storage_key:
        raise HTTPException(status_code=404, detail="待确认原版不存在或已经使用")
    remove_source_document_file(storage_key)
    return {"success": True}


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

        pdf_bytes = _pdf_generator(
            resume_data, style, photo, lang, request_data.get("layout_config")
        )

        project_name, version_name = _export_labels(db, current_user, request_data, resume_data)
        filename = _resume_export_filename(
            resume_data, "pdf", project_name, version_name
        )
        response_headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        }
        if is_local_mode():
            saved_path = _persist_local_export(pdf_bytes, filename)
            response_headers["X-Local-Export-Saved"] = "true"
            response_headers["X-Local-Export-Name"] = quote(saved_path.name)

        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers=response_headers,
        )
    except Exception as e:
        LOGGER.exception("PDF 导出失败")
        import traceback
        traceback.print_exc()
        return _public_error_response("PDF_EXPORT_FAILED", "PDF 导出失败，请稍后重试。")


@app.post("/export_docx")
async def export_docx_endpoint(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """导出可继续编辑的 Word（DOCX）简历。"""
    try:
        try:
            request_data = await request.json()
        except Exception:
            request_data = {}
        resume_data = get_user_resume(db, current_user.id)
        if not resume_data:
            raise HTTPException(status_code=400, detail="没有找到简历数据，请先创建或加载简历")

        docx_bytes = _docx_generator(
            resume_data,
            request_data.get("style", {}),
            get_user_photo(db, current_user.id) or None,
            request_data.get("lang", "zh"),
            request_data.get("layout_config"),
        )
        project_name, version_name = _export_labels(db, current_user, request_data, resume_data)
        filename = _resume_export_filename(
            resume_data, "docx", project_name, version_name
        )
        response_headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        }
        if is_local_mode():
            saved_path = _persist_local_export(docx_bytes, filename)
            response_headers["X-Local-Export-Saved"] = "true"
            response_headers["X-Local-Export-Name"] = quote(saved_path.name)
        return StreamingResponse(
            iter([docx_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=response_headers,
        )
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("Word 导出失败")
        import traceback
        traceback.print_exc()
        return _public_error_response("DOCX_EXPORT_FAILED", "Word 导出失败，请稍后重试。")


@app.post("/chat")
async def chat_endpoint(
    message: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    session_id: str = Form(""),
    request_id: str = Form(""),
    assistant_command: str = Form(""),
    render_style: str = Form(""),
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
        context_record = None
        if hasattr(db, "query") and session_id:
            context_record = get_context_by_session(db, current_user.id, task_id, session_id)
            if context_record and context_record.status != "active":
                return JSONResponse(content={"error": "该任务会话已关闭，请重新开启命令"}, status_code=409)
            task_record = get_resume_task(db, current_user.id, task_id)
            if task_record and session_id != task_record.session_id and context_record is None:
                return JSONResponse(content={"error": "无效的任务会话"}, status_code=409)
        context_type = context_record.context_type if context_record else "main"
        context_metadata = dict(getattr(context_record, "metadata_json", {}) or {}) if context_record else {}
        # 生成会话 ID
        if not session_id:
            session_id = generate_session_id()
        elif len(session_id) > 36:
            return JSONResponse(
                content={"error": "session_id 最长为 36 个字符"},
                status_code=400,
            )
        request_id = (request_id or str(uuid.uuid4())).strip()[:64]
        render_style_data = _parse_render_style(render_style)
        requested_command = assistant_command.strip().lower() if isinstance(assistant_command, str) else ""
        command_context = {"layout": "layout", "coaching": "coaching"}
        if requested_command not in {"", *command_context}:
            return JSONResponse(content={"error": "不支持的助手命令"}, status_code=400)
        if requested_command and context_type != command_context[requested_command]:
            return JSONResponse(content={"error": "助手命令与当前任务会话不匹配"}, status_code=409)

        # 图本身不持久化业务载荷；thread_id 仅用于本轮追踪。
        config = {
            "configurable": {
                "thread_id": f"user:{current_user.id}:task:{task_id}:session:{session_id}",
            }
        }

        # 检测用户是否点击了确认按钮（必须在使用 message 之前）
        is_confirm_click = '[CONFIRM_REPLY:' in message.strip()

        # A normal user message supersedes any older preview.  Clear it before
        # loading graph state so stale confirmations cannot be re-emitted.
        if not is_confirm_click:
            from .database import clear_pending_confirmation
            clear_pending_confirmation(db, current_user.id, session_id)


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
                message_content.append(build_file_message_part(content, file.content_type))

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

        # 从分层记忆读取摘要、近期完整对话和乐观版本；旧任务会自动回退旧上下文。
        from .database import get_agent_memory_state
        memory_state = get_agent_memory_state(db, current_user.id, session_id)
        db_context_raw = memory_state.get("recent_messages", [])
        memory_summary = str(memory_state.get("summary", "") or "")
        memory_version = int(memory_state.get("version", 0) or 0)

        # 转换数据库中的消息为 Message 对象
        historical_messages = []
        for msg_dict in db_context_raw:
            msg_type = msg_dict.get("type", "").lower()
            content = msg_dict.get("content", "")
            tool_calls = msg_dict.get("tool_calls", [])
            if tool_calls:
                continue
            if msg_type in {"ai", "assistant", "human", "user", "system", "systemmessage"}:
                message_for_check = {"type": msg_type, "content": content}
                if not _message_dict_has_text(message_for_check):
                    continue
            if msg_type == "human":
                historical_messages.append(HumanMessage(content=content))
            elif msg_type == "ai":
                historical_messages.append(AIMessage(content=content))
            elif msg_type == "system" or msg_type == "systemmessage":
                historical_messages.append(SystemMessage(content=content))

        # 构建 all_messages：数据库中的历史消息 + 当前用户消息
        all_messages = list(historical_messages) + [current_message]
        LOGGER.debug("从数据库加载 %s 条历史消息", len(historical_messages))

        # 使用数据库中的数据
        initial_resume_data = resume_data if resume_data else (get_user_resume(db, current_user.id) or {})
        initial_jd_data = jd_data if jd_data else (get_user_jd(db, current_user.id) or {})
        initial_layout_data = get_task_layout_config(db, current_user.id, task_id)

        # 从数据库获取待确认状态
        from .database import get_pending_confirmation
        initial_pending_confirmation = get_pending_confirmation(db, current_user.id, session_id)
        if initial_pending_confirmation:
            if not is_confirm_click:
                from .database import clear_pending_confirmation
                clear_pending_confirmation(db, current_user.id, session_id)
                initial_pending_confirmation = None

        coach_record = (
            get_agent_skill_state(
                db, current_user.id, session_id, resume_agent.COACH_SKILL_NAME
            )
            if hasattr(db, "query")
            else {"state": {}, "version": 0}
        )
        coach_state = resume_agent.skill_runtime.get(
            resume_agent.COACH_SKILL_NAME
        ).module.normalize_coach_state(coach_record.get("state"))
        coach_required = requested_command == "coaching" or bool(coach_state.get("active"))
        active_skill_names = []
        if coach_required:
            active_skill_names.append(resume_agent.COACH_SKILL_NAME)

        # 证件照单独存储在任务记录中；在真实数据库会话中一并带入快照渲染。
        # 轻量测试替身可能没有 query 接口，此时沿用无照片快照即可。
        initial_photo = (
            get_user_photo(db, current_user.id) or ""
            if hasattr(db, "query")
            else ""
        )

        # 创建初始状态。确认点击仍保留完整消息历史；结构化深度打磨仅通过显式
        # 模式或已恢复的活动状态进入，不改变普通聊天/修改请求的入口。
        initial_state = {
            "messages": all_messages,
            "resume_data": initial_resume_data,
            "jd_data": initial_jd_data,
            "layout_data": initial_layout_data,
            "pending_confirmation": initial_pending_confirmation,
            "user_id": current_user.id,
            "task_id": task_id,
            "proposal_error": None,
            "memory_summary": memory_summary,
            "memory_version": memory_version,
            "coach_state": coach_state,
            "coach_state_version": int(coach_record.get("version", 0) or 0),
            "coach_state_changed": False,
            "coach_turn_processed": False,
            "coach_required": coach_required,
            "coach_edit_handoff": None,
            "assistant_command": requested_command,
            "request_id": request_id,
            "context_id": session_id,
            "context_type": context_type,
            "context_metadata": context_metadata,
            "photo": initial_photo,
            "render_style": render_style_data,
            "visual_snapshot_parts": [],
            "visual_snapshot_calls": 0,
            "visual_snapshot_revision": "",
            "visual_snapshot_error": "",
            "context_metadata_updates": {},
            "active_skill_names": active_skill_names,
        }
        LOGGER.debug(
            "Agent 初始状态已创建，消息数=%s，存在待确认=%s",
            len(all_messages),
            initial_state.get("pending_confirmation") is not None,
        )

        async def save_state_async(
            db, user_id, session_id, messages_list, resume_data_result,
            initial_jd_data, pending_confirmation=None,
            context_metadata_updates=None,
        ):
            """Compatibility wrapper around the extracted turn persistence service."""
            await persist_turn_state(
                db,
                user_id,
                session_id,
                messages_list,
                resume_data_result,
                initial_jd_data,
                pending_confirmation,
                conversation_llm=conversation_llm,
                compression_state=compression_state,
                previous_summary=memory_summary,
                expected_version=memory_version,
                context_metadata_updates=context_metadata_updates or {},
            )

        async def stream_response(config):
            """流式生成响应"""
            import time
            total_start = time.time()

            # 累积所有消息，而不是每轮重置
            # 这样 save_state_async 才能获取完整的消息历史
            messages_list = list(all_messages)  # 从 initial_state 开始
            LOGGER.debug("流式响应消息数=%s", len(messages_list))
            resume_data_result = {}
            layout_data_result = initial_layout_data
            pending_confirmation_result = None  # 保存待确认状态
            confirmation_processed = False
            confirmation_success = False
            final_content = None
            accumulated_content = ""
            last_streamed_content = ""
            current_node = None
            node_start_time = {}
            sent_progress_phases = set()
            sent_confirm_ids = set()
            confirmation_sent = False
            edit_lock_acquired = False
            proposal_error_result = None
            coach_state_result = coach_state
            coach_state_changed = False
            context_metadata_updates_result = {}

            def acquire_turn_edit_lock():
                nonlocal edit_lock_acquired
                if edit_lock_acquired:
                    return
                from .database import find_task_pending_confirmation
                existing = find_task_pending_confirmation(
                    db, current_user.id, task_id, exclude_session_id=session_id
                )
                lock = None if existing else acquire_resume_edit_lock(
                    db, current_user.id, task_id, session_id, request_id
                )
                if not lock:
                    raise RuntimeError("当前简历存在正在处理的修改，请先完成或取消后再请求。")
                edit_lock_acquired = True

            def progress_event(phase, text):
                sent_progress_phases.add(phase)
                return 'data: ' + json.dumps({
                    "type": "progress",
                    "request_id": request_id,
                    "phase": phase,
                    "text": text,
                }) + '\n\n'

            edit_lock_token = resume_agent.set_edit_lock_acquirer(acquire_turn_edit_lock)
            try:
                # 统一使用 graph.astream_events
                # 入口路由会在 Graph 内部处理（通过 entry_router）
                LOGGER.debug("SSE 流式处理开始")
                async for event in graph.astream_events(initial_state, config=config, version="v1"):
                    event_type = event.get("event", "")
                    node_name = event.get("name", "")

                    if event_type == "on_chain_start":
                        current_node = node_name
                        node_start_time[node_name] = time.time()
                        LOGGER.debug("Agent 节点开始: %s", node_name)
                        preview_node = node_name in {"tool_node", "direct_edit", "proposal_generator"}
                        if preview_node and not is_confirm_click:
                            if "building_preview" not in sent_progress_phases:
                                yield progress_event("building_preview", "正在生成修改预览…")

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
                            visible_content = _sanitize_streaming_user_visible_text(accumulated_content)
                            if visible_content != last_streamed_content:
                                last_streamed_content = visible_content
                                yield f'data: {json.dumps({"type": "stream", "content": visible_content, "request_id": request_id})}\n\n'

                    elif event_type == "on_chain_end":
                        if node_name in node_start_time:
                            del node_start_time[node_name]

                        # 跳过内部节点（__start__, entry_router），只处理实际的工作节点
                        if node_name in ["__start__", "entry_router"]:
                            continue

                        output = event.get("data", {}).get("output", {})
                        if not isinstance(output, dict):
                            continue

                        if "messages" in output:
                            messages_list = list(output["messages"])
                        if isinstance(output.get("coach_state"), dict):
                            coach_state_result = output["coach_state"]
                        coach_state_changed = coach_state_changed or bool(output.get("coach_state_changed"))
                        if isinstance(output.get("context_metadata_updates"), dict):
                            context_metadata_updates_result.update(output["context_metadata_updates"])

                        output_messages = output.get("messages", [])
                        if node_name == "tool_node" and is_confirm_click and any(
                            isinstance(item, ToolMessage)
                            and getattr(item, "name", "") == "confirmation_handler"
                            for item in output_messages
                        ):
                            confirmation_processed = True
                            confirmation_success = bool(output.get("just_saved"))

                        proposal_error = (
                            output.get("proposal_error")
                            if node_name in {"proposal_generator", "tool_node"}
                            else None
                        )
                        if proposal_error and proposal_error != proposal_error_result:
                            proposal_error_result = str(proposal_error)
                            pending_confirmation_result = None
                            yield 'data: ' + json.dumps({
                                "type": "proposal_error",
                                "request_id": request_id,
                                "message": proposal_error_result,
                                "retryable": True,
                            }) + '\n\n'

                        confirm_data = (
                            output.get("pending_confirmation")
                            if node_name in {"tool_node", "direct_edit", "proposal_generator"}
                            else None
                        )
                        confirm_id = confirm_data.get("confirm_id") if isinstance(confirm_data, dict) else None
                        if confirm_id and confirm_id not in sent_confirm_ids and not confirmation_sent:
                            # The assistant reply occupies the streaming
                            # placeholder created before the request.  Emit it
                            # before the confirmation event so a mixed
                            # "answer + edit" turn never opens the modal first
                            # and silently drops the answer.
                            if not accumulated_content:
                                for item in reversed(output_messages):
                                    if not isinstance(item, AIMessage):
                                        continue
                                    reply = str(getattr(item, "content", "") or "").strip()
                                    if not reply or getattr(item, "tool_calls", None):
                                        continue
                                    accumulated_content = _sanitize_user_visible_text(reply)
                                    last_streamed_content = accumulated_content
                                    yield f'data: {json.dumps({"type": "stream", "content": accumulated_content, "request_id": request_id})}\n\n'
                                    break
                            sent_confirm_ids.add(confirm_id)
                            confirmation_sent = True
                            if "validating" not in sent_progress_phases:
                                yield progress_event("validating", "正在校验修改内容…")
                            try:
                                from .database import (
                                    find_task_pending_confirmation,
                                    get_conversation_context,
                                    save_conversation_context,
                                )
                                async with _edit_preview_guard:
                                    existing_edit = find_task_pending_confirmation(
                                        db, current_user.id, task_id
                                    )
                                    if existing_edit:
                                        raise RuntimeError("当前简历存在正在处理的修改，请先完成或取消后再请求。")
                                    confirm_data["owner_session_id"] = session_id
                                    confirm_data["request_id"] = request_id
                                    current_context = get_conversation_context(db, current_user.id, session_id)
                                    save_conversation_context(
                                        db,
                                        current_user.id,
                                        session_id,
                                        current_context,
                                        confirm_data,
                                    )
                                    if not mark_resume_edit_awaiting_confirmation(
                                        db, current_user.id, task_id, session_id, request_id
                                    ):
                                        raise RuntimeError("修改预览状态未能安全保存")
                            except Exception as exc:
                                if edit_lock_acquired:
                                    from .database import clear_pending_confirmation
                                    clear_pending_confirmation(db, current_user.id, session_id)
                                pending_confirmation_result = None
                                proposal_error_result = (
                                    str(exc)
                                    if "正在处理的修改" in str(exc)
                                    else "修改预览暂时无法保存，请重试。"
                                )
                                LOGGER.warning("同步保存待确认修改失败: %s", exc)
                                yield 'data: ' + json.dumps({
                                    "type": "proposal_error",
                                    "request_id": request_id,
                                    "message": proposal_error_result,
                                    "retryable": True,
                                }) + '\n\n'
                            else:
                                pending_confirmation_result = confirm_data
                                yield progress_event("ready", "修改预览已准备好")
                                yield 'data: ' + json.dumps({
                                    "type": "confirm",
                                    "request_id": request_id,
                                    "id": str(uuid.uuid4()),
                                    "content": confirm_data["content"],
                                    "options": confirm_data["options"],
                                    "changes": confirm_data.get("changes", []),
                                    "resume_candidate": confirm_data.get("resume_candidate"),
                                    "layout_candidate": confirm_data.get("layout_candidate"),
                                    "confirm_id": confirm_id,
                                    "session_id": session_id,
                                }) + '\n\n'
                        elif (
                            node_name in {"tool_node", "direct_edit", "proposal_generator"}
                            and "pending_confirmation" in output
                            and not confirm_data
                        ):
                            pending_confirmation_result = None

                        if "resume_data" in output and not confirm_data:
                            resume_data_result = output["resume_data"]
                        if "layout_data" in output and not confirm_data:
                            layout_data_result = output["layout_data"]

                if proposal_error_result:
                    final_content = proposal_error_result
                elif not accumulated_content:
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
                LOGGER.exception("Agent 请求执行失败")
                final_content = (
                    "当前简历存在正在处理的修改，请先完成或取消后再请求。"
                    if "正在处理的修改" in str(e)
                    else "抱歉，本次请求未能安全完成，请稍后重试。"
                )
            finally:
                resume_agent.reset_edit_lock_acquirer(edit_lock_token)

            if edit_lock_acquired and not pending_confirmation_result:
                release_resume_edit_lock(
                    db, current_user.id, task_id,
                    owner_session_id=session_id, request_id=request_id,
                )

            if not final_content:
                final_content = "抱歉，我无法理解您的请求。"
            final_content = _sanitize_user_visible_text(final_content)

            if confirmation_processed:
                from .database import clear_pending_confirmation
                clear_pending_confirmation(db, current_user.id, session_id)

            # Persist before final/end so a following request cannot observe a
            # stale context. Optimistic version conflicts fail closed instead
            # of overwriting newer memory.
            resume_data_to_persist = {} if confirmation_processed else resume_data_result
            try:
                await save_state_async(
                    db,
                    current_user.id,
                    session_id,
                    messages_list,
                    resume_data_to_persist,
                    initial_jd_data,
                    pending_confirmation_result,
                    context_metadata_updates_result,
                )
                if coach_state_changed and hasattr(db, "query"):
                    save_agent_skill_state(
                        db,
                        current_user.id,
                        session_id,
                        resume_agent.COACH_SKILL_NAME,
                        coach_state_result,
                        int(coach_record.get("version", 0) or 0),
                    )
            except Exception as exc:
                LOGGER.warning("回合状态保存失败: %s", exc)
                harness_metrics.increment("persistence_errors_total")
                yield 'data: ' + json.dumps({
                    "type": "persistence_error",
                    "request_id": request_id,
                    "message": "对话状态未能安全保存，请重新发送上一条消息。",
                    "retryable": True,
                }) + '\n\n'

            yield 'data: ' + json.dumps({
                "type": "final",
                "content": final_content,
                "session_id": session_id,
                "request_id": request_id,
                "confirmation_processed": confirmation_processed,
                "confirmation_success": confirmation_success,
                "layout_config": layout_data_result,
            }) + '\n\n'

            yield 'data: ' + json.dumps({
                "type": "end",
                "session_id": session_id,
                "request_id": request_id,
                "confirmation_processed": confirmation_processed,
                "confirmation_success": confirmation_success,
                "layout_config": layout_data_result,
            }) + '\n\n'

        return StreamingResponse(stream_response(config), media_type="text/event-stream")

    except Exception:
        LOGGER.exception("聊天接口失败")
        return _public_error_response("CHAT_FAILED", "本次请求未能安全完成，请稍后重试。")


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
        task_id = db.info.get("task_id")
        if not task_id:
            return JSONResponse(content={"error": "请先选择一个简历任务"}, status_code=400)

        # 从数据库获取 pending_confirmation
        from .database import clear_pending_confirmation, get_pending_confirmation, get_user_resume
        pending_confirmation = get_pending_confirmation(db, current_user.id, session_id)

        if not pending_confirmation:
            return JSONResponse(content={"error": "没有待确认的操作"}, status_code=400)

        if pending_confirmation.get("confirm_id") != confirm_id:
            return JSONResponse(content={"error": "确认ID不匹配"}, status_code=400)

        if action not in {"confirm", "cancel"}:
            return JSONResponse(content={"error": "无效的确认操作"}, status_code=400)

        # 根据操作处理
        if action == "confirm":
            # 从 pending_confirmation 获取修改后的简历数据
            tool_args = pending_confirmation.get("tool_args", {})
            pending_task_id = tool_args.get("task_id")
            if pending_task_id and pending_task_id != task_id:
                return JSONResponse(content={"error": "待确认操作不属于当前简历任务"}, status_code=409)
            content = tool_args.get("content", "")

            if not content:
                return JSONResponse(content={"error": "没有找到修改后的简历数据"}, status_code=400)

            from .resume_changes import resume_state_version_matches
            live_task = get_resume_task(db, current_user.id, task_id)
            before_resume_data = deepcopy((live_task.resume_data if live_task else {}) or {})
            before_layout_data = deepcopy((live_task.layout_config if live_task else {}) or {})
            if not resume_state_version_matches(
                pending_confirmation.get("base_version"),
                before_resume_data,
                before_layout_data,
                check_content=True,
                check_layout=False,
            ):
                clear_pending_confirmation(db, current_user.id, session_id)
                return JSONResponse(
                    content={"error": "简历已发生其他修改，请重新生成修改预览"},
                    status_code=409,
                )

            # 解析 JSON
            import json as json_module
            try:
                updated_resume_data = json_module.loads(content)
                updated_resume_data = validate_resume_data(updated_resume_data)
            except (json_module.JSONDecodeError, TypeError, ValueError) as e:
                return JSONResponse(content={"error": "简历数据格式不正确，请重新生成修改预览"}, status_code=400)

            # 保存修改后的简历数据
            from .tools import update_resume
            result = update_resume(
                updated_resume_data,
                user_id=current_user.id,
                task_id=task_id,
                db=db,
            )
            if result.startswith("保存失败") or result.startswith("错误"):
                return JSONResponse(content={"error": result}, status_code=400)

            if pending_confirmation.get("source") == "direct_replace":
                from .database import record_resume_revision
                record_resume_revision(
                    db,
                    current_user.id,
                    task_id,
                    before_resume_data,
                    updated_resume_data,
                    [item.get("id") for item in pending_confirmation.get("changes", []) if item.get("id")],
                    before_layout=(live_task.layout_config if live_task else None),
                    after_layout=(live_task.layout_config if live_task else None),
                )

            # 清除 pending_confirmation 状态
            clear_pending_confirmation(db, current_user.id, session_id)

            return JSONResponse(content={
                "success": True,
                "message": result,
                "action": "saved",
                "resume_data": updated_resume_data,
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
        LOGGER.exception("确认接口失败")
        import traceback
        traceback.print_exc()
        return _public_error_response("CONFIRM_FAILED", "确认操作处理失败，请重新加载后重试。")



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
        LOGGER.exception("首次提问接口失败")
        import traceback
        traceback.print_exc()
        return _public_error_response("FIRST_MESSAGE_FAILED", "首次提问生成失败，请稍后重试。")


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
        LOGGER.exception("简历首次提问接口失败")
        import traceback
        traceback.print_exc()
        return _public_error_response("RESUME_QUESTION_FAILED", "简历提问生成失败，请稍后重试。")


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
        LOGGER.exception("保存 AI 消息接口失败")
        import traceback
        traceback.print_exc()
        return _public_error_response("MESSAGE_SAVE_FAILED", "消息保存失败，请稍后重试。")


if __name__ == "__main__":
    import uvicorn
    from .auth import get_password_hash
    from .database import SessionLocal, cleanup_old_contexts, create_user, get_user_by_email

    LOGGER.info("Resume Assistant 后端服务启动中")

    # 启动时清理 7 天未访问的上下文
    try:
        db = SessionLocal()
        deleted = cleanup_old_contexts(db, days=7)
        if deleted:
            LOGGER.info("已清理 %s 条过期上下文", deleted)
        db.close()
    except Exception as e:
        LOGGER.warning("清理过期上下文失败: %s", e)

    # 创建本地管理员账号（凭据只从 .env 读取）
    try:
        db = SessionLocal()
        if is_local_mode():
            LOGGER.info("本地模式已启用")
        else:
            admin_email = os.getenv("ADMIN_EMAIL", "").strip()
            admin_password = os.getenv("ADMIN_PASSWORD", "")
            if not admin_email or not admin_password:
                LOGGER.warning("未配置管理员凭据，跳过管理员初始化")
            else:
                existing_admin = get_user_by_email(db, admin_email)
                if existing_admin:
                    if not existing_admin.is_admin:
                        existing_admin.is_admin = True
                        db.commit()
                    LOGGER.info("管理员账号已存在")
                else:
                    hashed_pw = get_password_hash(admin_password)
                    create_user(
                        db,
                        admin_email,
                        hashed_pw,
                        invite_code="admin",
                        is_admin=True,
                    )
                    LOGGER.info("已创建管理员账号")
        db.close()
    except Exception as e:
        LOGGER.exception("创建管理员账号失败")

    uvicorn.run(
        app,
        host=SERVER_HOST,
        port=int(os.getenv("PORT", "8000"))
    )
