"""
数据库模块
SQLAlchemy 模型定义和数据库连接
"""

import logging
import os
import secrets
import uuid
from copy import deepcopy
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, JSON, Text, event, func, inspect, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
from dotenv import load_dotenv

from .resume_data import normalize_resume_data
from .layout_config import default_layout_config, normalize_layout_config

LOGGER = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/resumebranch.db")

database_backend = make_url(DATABASE_URL).get_backend_name()
engine_options = {}

if database_backend == "sqlite":
    sqlite_database = make_url(DATABASE_URL).database
    if sqlite_database and sqlite_database != ":memory:":
        Path(sqlite_database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    engine_options["connect_args"] = {"check_same_thread": False, "timeout": 30}
elif database_backend == "mysql":
    # Detect stale pooled connections and recycle them before MySQL's idle timeout.
    engine_options.update(pool_pre_ping=True, pool_recycle=3600)

engine = create_engine(DATABASE_URL, **engine_options)


if database_backend == "sqlite":
    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record):
        """Improve local durability and tolerate short concurrent write bursts."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
_PENDING_CONFIRMATION_UNSET = object()

# MySQL TEXT is limited to 64 KiB, which is too small for base64 profile photos.
large_text_type = Text().with_variant(LONGTEXT(), "mysql")


class User(Base):
    """用户表"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    invite_code = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False, nullable=False)


class AuthSession(Base):
    """The single server-side login session currently active for one user."""
    __tablename__ = "auth_sessions"
    user_id = Column(Integer, primary_key=True)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


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
    photo = Column(large_text_type, default="")
    parsing_status = Column(String(20), default="none")  # none, parsing, completed, failed
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
    messages = Column(JSON, default=list)  # 完整的聊天历史
    compressed_context = Column(JSON, default=list)  # 压缩后的上下文（用于性能）
    pending_confirmation = Column(JSON, default=None)  # 待确认状态
    last_accessed = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConversationContext(Base):
    """A lightweight mission context belonging to one resume version.

    ``ProjectTask.session_id`` remains the legacy/main conversation id.  Mission
    contexts get their own session id and keep their lifecycle metadata here so
    the existing message and confirmation storage can be reused safely.
    """
    __tablename__ = "conversation_contexts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, nullable=False, index=True)
    task_id = Column(String(36), nullable=False, index=True)
    context_type = Column(String(32), nullable=False)
    title = Column(String(80), nullable=False, default="新任务")
    status = Column(String(20), nullable=False, default="active")
    session_id = Column(String(36), nullable=False, unique=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)


class ResumeProject(Base):
    """A canonical resume shared as the source for JD-specific tasks."""
    __tablename__ = "resume_projects"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(120), nullable=False, default="未命名简历组")
    base_resume_data = Column(JSON, default=dict)
    photo = Column(large_text_type, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SourceDocument(Base):
    """Immutable uploaded PDF/image retained for read-only reference."""
    __tablename__ = "source_documents"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, nullable=False, index=True)
    storage_key = Column(String(255), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ProjectTask(Base):
    """A JD-specific resume version and its independent conversation."""
    __tablename__ = "project_tasks"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(120), nullable=False, default="主简历")
    is_base = Column(Boolean, default=False)
    session_id = Column(String(36), nullable=False, unique=True)
    resume_data = Column(JSON, default=dict)
    photo = Column(large_text_type, default="")
    parsing_status = Column(String(20), default="none")
    source_page_count = Column(Integer, default=1, nullable=False)
    source_document_id = Column(String(36), nullable=True, index=True)
    jd_data = Column(JSON, default=dict)
    messages = Column(JSON, default=list)
    compressed_context = Column(JSON, default=list)
    pending_confirmation = Column(JSON, default=None)
    layout_config = Column(JSON, default=dict)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResumeEditLock(Base):
    """Database-backed, task-wide ownership for one mutable preview lifecycle."""
    __tablename__ = "resume_edit_locks"
    task_id = Column(String(36), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    owner_session_id = Column(String(36), nullable=False)
    request_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="generating")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AgentMemoryState(Base):
    """Layered conversation memory stored separately from canonical resume data."""
    __tablename__ = "agent_memory_states"
    scope_id = Column(String(100), primary_key=True)
    task_id = Column(String(36), nullable=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String(36), nullable=False)
    summary = Column(large_text_type, default="")
    recent_messages = Column(JSON, default=list)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentSkillState(Base):
    """Private, versioned state owned by one Agent Skill and conversation."""
    __tablename__ = "agent_skill_states"
    scope_id = Column(String(180), primary_key=True)
    task_id = Column(String(36), nullable=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String(36), nullable=False)
    skill_name = Column(String(64), nullable=False, index=True)
    state_json = Column(JSON, default=dict)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResumeRevision(Base):
    """A reversible snapshot created by an assistant-confirmed resume update."""
    __tablename__ = "resume_revisions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    before_data = Column(JSON, nullable=False)
    after_data = Column(JSON, nullable=False)
    selected_change_ids = Column(JSON, default=list)
    before_layout = Column(JSON, default=None)
    after_layout = Column(JSON, default=None)
    undone_at = Column(DateTime, default=None)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class WorkspaceState(Base):
    """Tracks completion of the one-time legacy workspace migration."""
    __tablename__ = "workspace_states"
    user_id = Column(Integer, primary_key=True)
    legacy_migrated = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TranslationMemory(Base):
    """Reusable, user-scoped translations for unchanged resume text fields."""
    __tablename__ = "translation_memories"
    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    source_language = Column(String(12), nullable=False)
    target_language = Column(String(12), nullable=False)
    context_key = Column(String(120), nullable=False, default="")
    source_hash = Column(String(64), nullable=False, index=True)
    source_text = Column(large_text_type, nullable=False)
    translated_text = Column(large_text_type, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResumeTranslationState(Base):
    """Durable Chinese/English snapshots for one active resume task."""
    __tablename__ = "resume_translation_states"
    scope_id = Column(String(100), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    task_id = Column(String(36), nullable=True, index=True)
    source_digest = Column(String(64), nullable=False, index=True)
    source_data = Column(JSON, nullable=False)
    translated_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MemoryVersionConflict(RuntimeError):
    """Raised when a stale request attempts to overwrite newer agent memory."""


def get_db():
    """数据库依赖"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库（创建所有表）"""
    Base.metadata.create_all(bind=engine)
    migrate_project_task_source_page_count()
    migrate_project_task_source_document()
    migrate_layout_config_fields()
    migrate_user_admin_field()
    migrate_resume_academic_fields()


def migrate_project_task_source_page_count():
    """Add automatic source-page metadata to existing SQLite/MySQL databases."""
    inspector = inspect(engine)
    if "project_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("project_tasks")}
    if "source_page_count" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE project_tasks ADD COLUMN source_page_count INTEGER NOT NULL DEFAULT 1"
        ))


def migrate_project_task_source_document():
    """Link existing tasks to optional immutable source documents."""
    inspector = inspect(engine)
    if "project_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("project_tasks")}
    if "source_document_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE project_tasks ADD COLUMN source_document_id VARCHAR(36)"
            ))


def migrate_layout_config_fields():
    """Add layout configuration and reversible layout snapshots."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "project_tasks" in tables:
            columns = {column["name"] for column in inspector.get_columns("project_tasks")}
            if "layout_config" not in columns:
                connection.execute(text("ALTER TABLE project_tasks ADD COLUMN layout_config JSON"))
        if "resume_revisions" in tables:
            columns = {column["name"] for column in inspector.get_columns("resume_revisions")}
            if "before_layout" not in columns:
                connection.execute(text("ALTER TABLE resume_revisions ADD COLUMN before_layout JSON"))
            if "after_layout" not in columns:
                connection.execute(text("ALTER TABLE resume_revisions ADD COLUMN after_layout JSON"))


def migrate_user_admin_field():
    """Add explicit server-side administrator authorization to old databases."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_admin" in columns:
        return
    with engine.begin() as connection:
        if database_backend == "mysql":
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"
            ))
        else:
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
            ))


def migrate_resume_academic_fields():
    """Migrate legacy GPA-in-thesis records into explicit education fields."""
    db = SessionLocal()
    changed = 0
    try:
        for resume in db.query(Resume).all():
            try:
                normalized = normalize_resume_data(resume.resume_data or {})
            except (TypeError, ValueError) as exc:
                LOGGER.warning("跳过旧版简历数据迁移 id=%s: %s", resume.id, exc)
                continue
            if normalized != (resume.resume_data or {}):
                resume.resume_data = normalized
                changed += 1

        for project in db.query(ResumeProject).all():
            try:
                normalized = normalize_resume_data(project.base_resume_data or {})
            except (TypeError, ValueError) as exc:
                LOGGER.warning("跳过简历项目迁移 id=%s: %s", project.id, exc)
                continue
            if normalized != (project.base_resume_data or {}):
                project.base_resume_data = normalized
                changed += 1

        for task in db.query(ProjectTask).all():
            try:
                normalized = normalize_resume_data(task.resume_data or {})
            except (TypeError, ValueError) as exc:
                LOGGER.warning("跳过简历任务迁移 id=%s: %s", task.id, exc)
                continue
            if normalized != (task.resume_data or {}):
                task.resume_data = normalized
                changed += 1

        if changed:
            db.commit()
            LOGGER.info("已规范化 %s 份简历的教育成绩字段", changed)
    except Exception as exc:
        db.rollback()
        # A normalization issue should not prevent the application from starting.
        LOGGER.warning("教育成绩字段迁移已跳过: %s", exc)
    finally:
        db.close()


# =============================================================================
# 数据访问函数
# =============================================================================

def get_user_by_email(db, email: str):
    """根据邮箱获取用户"""
    normalized = str(email or "").strip().lower()
    return db.query(User).filter(func.lower(User.email) == normalized).first()


def get_user_by_id(db, user_id: int):
    """根据ID获取用户"""
    return db.query(User).filter(User.id == user_id).first()


def create_user(
    db,
    email: str,
    hashed_password: str,
    invite_code: str,
    *,
    is_admin: bool = False,
    commit: bool = True,
):
    """创建用户"""
    user = User(
        email=str(email or "").strip().lower(),
        hashed_password=hashed_password,
        invite_code=invite_code,
        is_admin=bool(is_admin),
    )
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)
    return user


def rotate_auth_session(db, user_id: int) -> str:
    """Replace a user's active login session and return its opaque id."""
    session_id = secrets.token_urlsafe(32)
    row = db.query(AuthSession).filter(AuthSession.user_id == user_id).first()
    if row:
        row.session_id = session_id
        row.updated_at = datetime.utcnow()
    else:
        db.add(AuthSession(user_id=user_id, session_id=session_id))
    try:
        db.commit()
    except IntegrityError:
        # Two near-simultaneous logins still converge on one final session.
        db.rollback()
        row = db.query(AuthSession).filter(AuthSession.user_id == user_id).one()
        row.session_id = session_id
        row.updated_at = datetime.utcnow()
        db.commit()
    return session_id


def auth_session_is_active(db, user_id: int, session_id: str) -> bool:
    if not session_id:
        return False
    return db.query(AuthSession).filter(
        AuthSession.user_id == user_id,
        AuthSession.session_id == session_id,
    ).first() is not None


def revoke_auth_session(db, user_id: int, session_id: str = "") -> bool:
    query = db.query(AuthSession).filter(AuthSession.user_id == user_id)
    if session_id:
        query = query.filter(AuthSession.session_id == session_id)
    deleted = query.delete(synchronize_session=False)
    db.commit()
    return bool(deleted)


def _active_task(db, user_id: int):
    task_id = db.info.get("task_id")
    if not task_id:
        return None
    task = db.query(ProjectTask).filter(
        ProjectTask.id == task_id,
        ProjectTask.user_id == user_id,
    ).first()
    if not task:
        raise ValueError("当前简历任务不存在或不属于该用户")
    return task


CONTEXT_TYPES = frozenset({"main", "layout", "jd_review", "coaching"})
CONTEXT_STATUSES = frozenset({"active", "closed"})
CONTEXT_TITLES = {
    "main": "主对话",
    "layout": "排版建议",
    "jd_review": "对照 JD",
    "coaching": "深度打磨",
}


def _context_query(db, user_id: int, session_id: str):
    """Return a context for the active task/session, if one exists."""
    task = _active_task(db, user_id)
    if not task or not session_id:
        return None
    return db.query(ConversationContext).filter(
        ConversationContext.user_id == user_id,
        ConversationContext.task_id == task.id,
        ConversationContext.session_id == str(session_id),
    ).first()


def ensure_main_context(db, user_id: int, task_id: str | None = None):
    """Create the durable main context for a task without changing legacy data."""
    task = get_resume_task(db, user_id, task_id) if task_id else _active_task(db, user_id)
    if not task:
        return None
    context = db.query(ConversationContext).filter(
        ConversationContext.user_id == user_id,
        ConversationContext.task_id == task.id,
        ConversationContext.context_type == "main",
    ).first()
    if context:
        return context
    context = ConversationContext(
        id=str(uuid.uuid4()),
        user_id=user_id,
        task_id=task.id,
        context_type="main",
        title=CONTEXT_TITLES["main"],
        status="active",
        session_id=task.session_id,
        metadata_json={},
    )
    db.add(context)
    db.commit()
    db.refresh(context)
    return context


def list_conversation_contexts(db, user_id: int, task_id: str):
    """List the main context and active/closed mission records for a task."""
    task = get_resume_task(db, user_id, task_id)
    if not task:
        return []
    ensure_main_context(db, user_id, task.id)
    return db.query(ConversationContext).filter(
        ConversationContext.user_id == user_id,
        ConversationContext.task_id == task.id,
    ).order_by(
        (ConversationContext.context_type == "main").desc(),
        ConversationContext.updated_at.desc(),
    ).all()


def get_conversation_context_record(db, user_id: int, context_id: str):
    """Get a context record with ownership validation."""
    return db.query(ConversationContext).filter(
        ConversationContext.id == str(context_id or ""),
        ConversationContext.user_id == user_id,
    ).first()


def get_context_by_session(db, user_id: int, task_id: str, session_id: str):
    return db.query(ConversationContext).filter(
        ConversationContext.user_id == user_id,
        ConversationContext.task_id == task_id,
        ConversationContext.session_id == str(session_id or ""),
    ).first()


def create_or_resume_conversation_context(
    db,
    user_id: int,
    task_id: str,
    context_type: str,
    *,
    title: str | None = None,
):
    """Resume the single active context of a command type or create one.

    A closed context is never reopened; starting the command again creates a
    fresh session while preserving the closed record for audit/history.
    """
    normalized_type = str(context_type or "").strip().lower()
    if normalized_type not in CONTEXT_TYPES - {"main"}:
        raise ValueError("不支持的任务类型")
    task = get_resume_task(db, user_id, task_id)
    if not task:
        return None
    ensure_main_context(db, user_id, task.id)
    context = db.query(ConversationContext).filter(
        ConversationContext.user_id == user_id,
        ConversationContext.task_id == task.id,
        ConversationContext.context_type == normalized_type,
        ConversationContext.status == "active",
    ).order_by(ConversationContext.updated_at.desc()).first()
    if context:
        context.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(context)
        return context
    context = ConversationContext(
        id=str(uuid.uuid4()),
        user_id=user_id,
        task_id=task.id,
        context_type=normalized_type,
        title=(title or CONTEXT_TITLES.get(normalized_type, "新任务"))[:80],
        status="active",
        session_id=str(uuid.uuid4()),
        metadata_json={"command": normalized_type},
    )
    db.add(context)
    db.commit()
    db.refresh(context)
    return context


def close_conversation_context(db, user_id: int, context_id: str):
    """Close a mission and clear its mutable conversation state."""
    context = get_conversation_context_record(db, user_id, context_id)
    if not context:
        return None
    if context.context_type == "main":
        raise ValueError("主对话不能关闭")
    context.status = "closed"
    context.closed_at = datetime.utcnow()
    context.updated_at = datetime.utcnow()
    db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == context.session_id,
    ).delete(synchronize_session=False)
    db.query(AgentMemoryState).filter(
        AgentMemoryState.user_id == user_id,
        AgentMemoryState.scope_id == f"task:{context.task_id}:context:{context.session_id}",
    ).delete(synchronize_session=False)
    db.query(AgentSkillState).filter(
        AgentSkillState.user_id == user_id,
        AgentSkillState.task_id == context.task_id,
        AgentSkillState.session_id == context.session_id,
    ).delete(synchronize_session=False)
    db.query(ResumeEditLock).filter(
        ResumeEditLock.task_id == context.task_id,
        ResumeEditLock.user_id == user_id,
        ResumeEditLock.owner_session_id == context.session_id,
    ).delete(synchronize_session=False)
    db.commit()
    return context


def serialize_conversation_context(context):
    return {
        "id": context.id,
        "task_id": context.task_id,
        "context_type": context.context_type,
        "title": context.title,
        "status": context.status,
        "session_id": context.session_id,
        "created_at": context.created_at.isoformat() if context.created_at else None,
        "updated_at": context.updated_at.isoformat() if context.updated_at else None,
        "closed_at": context.closed_at.isoformat() if context.closed_at else None,
    }


def update_conversation_context_metadata(
    db,
    user_id: int,
    session_id: str,
    updates: dict | None,
):
    """Merge small, non-authoritative context metadata without storing transcripts."""
    if not isinstance(updates, dict) or not updates:
        return None
    task = _active_task(db, user_id)
    context = _context_query(db, user_id, session_id) if task else None
    if not context:
        return None
    metadata = dict(context.metadata_json or {})
    metadata.update(updates)
    context.metadata_json = metadata
    context.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(context)
    return context


def append_context_event(db, user_id: int, task_id: str, context, action: str = "started"):
    """Record a short mission lifecycle event in the task's main chat."""
    task = get_resume_task(db, user_id, task_id)
    if not task or not context:
        return None
    messages = list(task.messages or [])
    # A mission has one lifecycle record in the main conversation.  Closing it
    # updates the opening record instead of appending a second, still-looking
    # active card.  This keeps the audit trail visible while allowing the UI to
    # render the same record as closed/grey.
    if action == "closed":
        matching_indexes = [
            index for index, item in enumerate(messages)
            if (
                isinstance(item, dict)
                and item.get("type") == "context_event"
                and item.get("context_id") == context.id
            )
        ]
        if matching_indexes:
            messages = deepcopy(messages)
            closed_at = datetime.utcnow().isoformat()
            for index in matching_indexes:
                item = messages[index]
                item["action"] = "closed"
                item["status"] = "closed"
                item["closed_at"] = closed_at
                item["content"] = f"已结束“{context.title}”任务。"
            task.messages = messages
            task.updated_at = datetime.utcnow()
            db.commit()
            return messages[matching_indexes[-1]]
    content = {
        "id": str(uuid.uuid4()),
        "type": "context_event",
        "role": "system",
        "context_id": context.id,
        "context_type": context.context_type,
        "title": context.title,
        "action": action,
        "status": "active" if action == "started" else "closed",
        "content": (
            f"已开启“{context.title}”任务。"
            if action == "started" else f"已结束“{context.title}”任务。"
        ),
        "created_at": datetime.utcnow().isoformat(),
    }
    task.messages = messages + [content]
    task.updated_at = datetime.utcnow()
    db.commit()
    return content


def get_active_task(db, user_id: int):
    return _active_task(db, user_id)


def get_or_create_legacy_project(db, user_id: int):
    """Copy the legacy single workspace into one project and one base task."""
    project = db.query(ResumeProject).filter(ResumeProject.user_id == user_id).order_by(
        ResumeProject.updated_at.desc()
    ).first()
    if project:
        if not db.query(WorkspaceState).filter(WorkspaceState.user_id == user_id).first():
            db.add(WorkspaceState(user_id=user_id, legacy_migrated=True))
            db.commit()
        base_task = db.query(ProjectTask).filter(
            ProjectTask.project_id == project.id,
            ProjectTask.is_base.is_(True),
        ).first()
        if not base_task:
            task_id = str(uuid.uuid4())
            db.add(ProjectTask(
                id=task_id,
                project_id=project.id,
                user_id=user_id,
                title="主简历",
                is_base=True,
                session_id=task_id,
                resume_data=project.base_resume_data or {},
                photo=project.photo or "",
                layout_config=default_layout_config(),
            ))
            db.commit()
        return project

    if db.query(WorkspaceState).filter(WorkspaceState.user_id == user_id).first():
        return None

    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    jd = db.query(JobDescription).filter(JobDescription.user_id == user_id).first()
    conv = db.query(Conversation).filter(Conversation.user_id == user_id).order_by(
        Conversation.updated_at.desc()
    ).first()
    if not any((resume, jd, conv)):
        db.add(WorkspaceState(user_id=user_id, legacy_migrated=True))
        db.commit()
        return None

    project_id = str(uuid.uuid4())
    base_task_id = str(uuid.uuid4())
    title = resume.name if resume and resume.name else "我的简历"
    project = ResumeProject(
        id=project_id,
        user_id=user_id,
        title=title,
        base_resume_data=(resume.resume_data if resume else {}),
        photo=(resume.photo if resume else ""),
    )
    base_task = ProjectTask(
        id=base_task_id,
        project_id=project_id,
        user_id=user_id,
        title="主简历",
        is_base=True,
        session_id=base_task_id,
        resume_data=(resume.resume_data if resume else {}),
        photo=(resume.photo if resume else ""),
        parsing_status=(resume.parsing_status if resume else "none"),
        layout_config=default_layout_config(),
    )
    db.add_all([project, base_task, WorkspaceState(user_id=user_id, legacy_migrated=True)])
    if jd or conv:
        jd_task_id = str(uuid.uuid4())
        db.add(ProjectTask(
            id=jd_task_id,
            project_id=project_id,
            user_id=user_id,
            title=(jd.position or jd.company or "首个岗位版本") if jd else "旧版对话",
            is_base=False,
            session_id=jd_task_id,
            resume_data=(resume.resume_data if resume else {}),
            photo=(resume.photo if resume else ""),
            parsing_status=(resume.parsing_status if resume else "none"),
            jd_data=(jd.jd_data if jd else {}),
            messages=(conv.messages if conv else []),
            compressed_context=(conv.compressed_context if conv else []),
            pending_confirmation=(conv.pending_confirmation if conv else None),
            layout_config=default_layout_config(),
        ))
    db.commit()
    db.refresh(project)
    return project


def list_resume_projects(db, user_id: int):
    get_or_create_legacy_project(db, user_id)
    return db.query(ResumeProject).filter(ResumeProject.user_id == user_id).order_by(
        ResumeProject.updated_at.desc()
    ).all()


def create_resume_project(db, user_id: int, title: str = "未命名简历组"):
    project_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    project = ResumeProject(
        id=project_id,
        user_id=user_id,
        title=(title or "未命名简历组").strip()[:120],
    )
    task = ProjectTask(
        id=task_id,
        project_id=project_id,
        user_id=user_id,
        title="主简历",
        is_base=True,
        session_id=task_id,
        layout_config=default_layout_config(),
    )
    db.add_all([project, task])
    if not db.query(WorkspaceState).filter(WorkspaceState.user_id == user_id).first():
        db.add(WorkspaceState(user_id=user_id, legacy_migrated=True))
    db.commit()
    db.refresh(project)
    db.refresh(task)
    return project, task


def rename_resume_project(db, user_id: int, project_id: str, title: str):
    """Rename a resume project and make the rename visible to recent-edit sorting."""
    project = get_resume_project(db, user_id, project_id)
    if not project:
        return None
    project.title = str(title or "").strip()[:120]
    project.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(project)
    return project


def get_resume_project(db, user_id: int, project_id: str):
    return db.query(ResumeProject).filter(
        ResumeProject.id == project_id,
        ResumeProject.user_id == user_id,
    ).first()


def list_project_tasks(db, user_id: int, project_id: str):
    return db.query(ProjectTask).filter(
        ProjectTask.project_id == project_id,
        ProjectTask.user_id == user_id,
    ).order_by(ProjectTask.is_base.desc(), ProjectTask.updated_at.desc()).all()


def list_user_resume_sources(db, user_id: int):
    """List every resume task owned by the user as an independent copy source."""
    return db.query(ProjectTask).filter(ProjectTask.user_id == user_id).order_by(
        ProjectTask.updated_at.desc()
    ).all()


def create_resume_task(
    db,
    user_id: int,
    project_id: str,
    title: str = "新岗位版本",
    copy_base_resume: bool = True,
    source_task_id: str | None = None,
    jd_data: dict | None = None,
):
    project = get_resume_project(db, user_id, project_id)
    if not project:
        return None
    source_task = None
    if source_task_id:
        source_task = get_resume_task(db, user_id, source_task_id)
        if not source_task:
            return None
    elif copy_base_resume:
        source_task = db.query(ProjectTask).filter(
            ProjectTask.project_id == project_id,
            ProjectTask.user_id == user_id,
            ProjectTask.is_base.is_(True),
        ).first()

    task_id = str(uuid.uuid4())
    task = ProjectTask(
        id=task_id,
        project_id=project_id,
        user_id=user_id,
        title=(title or "新岗位版本").strip()[:120],
        is_base=False,
        session_id=task_id,
        resume_data=normalize_resume_data(source_task.resume_data or {}) if source_task else {},
        photo=(source_task.photo or "") if source_task else "",
        source_page_count=max(1, int(source_task.source_page_count or 1)) if source_task else 1,
        source_document_id=(source_task.source_document_id if source_task else None),
        jd_data=jd_data or {},
        layout_config=(
            normalize_layout_config(source_task.layout_config)
            if source_task else default_layout_config()
        ),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_resume_task(db, user_id: int, task_id: str):
    return db.query(ProjectTask).filter(
        ProjectTask.id == task_id,
        ProjectTask.user_id == user_id,
    ).first()


def rename_resume_task(db, user_id: int, task_id: str, title: str):
    """Rename any task, including the protected base task."""
    task = get_resume_task(db, user_id, task_id)
    if not task:
        return None
    task.title = str(title or "").strip()[:120]
    now = datetime.utcnow()
    task.updated_at = now
    project = get_resume_project(db, user_id, task.project_id)
    if project:
        project.updated_at = now
    db.commit()
    db.refresh(task)
    return task


def switch_base_resume_task(db, user_id: int, task_id: str):
    """Switch the base role between two tasks in the same resume project.

    The selected version becomes the base task, while the previous base task
    becomes an ordinary version named ``版本简历``. No data is copied or deleted.
    """
    selected_task = get_resume_task(db, user_id, task_id)
    if not selected_task:
        return "not_found", None, None

    base_task = db.query(ProjectTask).filter(
        ProjectTask.project_id == selected_task.project_id,
        ProjectTask.user_id == user_id,
        ProjectTask.is_base.is_(True),
    ).first()
    if not base_task:
        return "base_missing", None, selected_task
    if selected_task.id == base_task.id:
        return "ok", base_task, None

    now = datetime.utcnow()
    base_task.is_base = False
    base_task.title = "版本简历"
    base_task.updated_at = now
    selected_task.is_base = True
    selected_task.updated_at = now

    project = get_resume_project(db, user_id, selected_task.project_id)
    if project:
        project.base_resume_data = normalize_resume_data(selected_task.resume_data or {})
        project.photo = selected_task.photo or ""
        project.updated_at = now

    db.commit()
    db.refresh(selected_task)
    db.refresh(base_task)
    if project:
        db.refresh(project)
    return "ok", selected_task, base_task


def get_source_document(db, user_id: int, document_id: str):
    return db.query(SourceDocument).filter(
        SourceDocument.id == document_id,
        SourceDocument.user_id == user_id,
    ).first()


def get_task_source_document(db, user_id: int, task_id: str):
    task = get_resume_task(db, user_id, task_id)
    if not task or not task.source_document_id:
        return None
    return get_source_document(db, user_id, task.source_document_id)


def attach_source_document(db, user_id: int, document_id: str, task_id: str | None = None):
    task = get_resume_task(db, user_id, task_id) if task_id else _active_task(db, user_id)
    document = get_source_document(db, user_id, document_id)
    if not task or not document or document.status not in {"pending", "ready"}:
        return None
    task.source_document_id = document.id
    task.updated_at = datetime.utcnow()
    document.status = "ready"
    db.commit()
    db.refresh(task)
    return document


def discard_pending_source_document(db, user_id: int, document_id: str) -> str | None:
    document = get_source_document(db, user_id, document_id)
    if not document or document.status != "pending":
        return None
    storage_key = document.storage_key
    db.delete(document)
    db.commit()
    return storage_key


def delete_unreferenced_source_documents(db, user_id: int) -> list[str]:
    """Delete ready or expired pending metadata no longer referenced by a task."""
    referenced = {
        value for (value,) in db.query(ProjectTask.source_document_id).filter(
            ProjectTask.user_id == user_id,
            ProjectTask.source_document_id.isnot(None),
        ).all() if value
    }
    cutoff = datetime.utcnow() - timedelta(hours=24)
    removed: list[str] = []
    for document in db.query(SourceDocument).filter(SourceDocument.user_id == user_id).all():
        orphan_ready = document.status == "ready" and document.id not in referenced
        expired_pending = document.status == "pending" and document.created_at and document.created_at < cutoff
        if orphan_ready or expired_pending:
            removed.append(document.storage_key)
            db.delete(document)
    if removed:
        db.commit()
    return removed


def record_resume_revision(
    db,
    user_id: int,
    task_id: str,
    before_data: dict,
    after_data: dict,
    selected_change_ids: list[str] | None = None,
    before_layout: dict | None = None,
    after_layout: dict | None = None,
):
    """Record a successful assistant update so it can be safely undone once."""
    revision = ResumeRevision(
        task_id=task_id,
        user_id=user_id,
        before_data=normalize_resume_data(before_data or {}),
        after_data=normalize_resume_data(after_data or {}),
        selected_change_ids=list(selected_change_ids or []),
        before_layout=(normalize_layout_config(before_layout) if before_layout is not None else None),
        after_layout=(normalize_layout_config(after_layout) if after_layout is not None else None),
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


def undo_latest_resume_revision(db, user_id: int, task_id: str) -> tuple[str, dict | None, dict | None]:
    """Undo the latest revision only when no later edit has changed its result."""
    from .resume_changes import resume_digest

    task = get_resume_task(db, user_id, task_id)
    if not task:
        return "not_found", None, None
    revision = db.query(ResumeRevision).filter(
        ResumeRevision.task_id == task_id,
        ResumeRevision.user_id == user_id,
        ResumeRevision.undone_at.is_(None),
    ).order_by(ResumeRevision.created_at.desc()).first()
    if not revision:
        return "no_revision", None, None
    current_data = normalize_resume_data(task.resume_data or {})
    # Stored revisions may predate removal of empty experience-level ``details``.
    # Normalize both sides before comparing so legacy test snapshots remain undoable
    # without retaining the deprecated field in the active data contract.
    if resume_digest(current_data) != resume_digest(normalize_resume_data(revision.after_data or {})):
        return "conflict", None, None
    current_layout = normalize_layout_config(task.layout_config)
    if revision.after_layout is not None and current_layout != normalize_layout_config(revision.after_layout):
        return "conflict", None, None

    restored = normalize_resume_data(revision.before_data or {})
    task.resume_data = restored
    restored_layout = (
        normalize_layout_config(revision.before_layout)
        if revision.before_layout is not None else current_layout
    )
    task.layout_config = restored_layout
    task.pending_confirmation = None
    undo_event = {
        "type": "system",
        "content": (
            "系统事件：用户已撤回上一轮简历修改。当前数据库中的简历内容已恢复；"
            "后续判断必须以当前简历数据为准，不得沿用历史消息中‘修改已生效’的描述。"
        ),
    }
    task.compressed_context = list(task.compressed_context or []) + [undo_event]
    memory = db.query(AgentMemoryState).filter(
        AgentMemoryState.scope_id == f"task:{task_id}",
        AgentMemoryState.user_id == user_id,
    ).first()
    if memory:
        memory.recent_messages = list(memory.recent_messages or []) + [undo_event]
        memory.version = int(memory.version or 0) + 1
        memory.updated_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    if task.is_base:
        project = db.query(ResumeProject).filter(ResumeProject.id == task.project_id).first()
        if project:
            project.base_resume_data = restored
            project.updated_at = datetime.utcnow()
    revision.undone_at = datetime.utcnow()
    db.commit()
    return "undone", restored, restored_layout


def get_task_layout_config(db, user_id: int, task_id: str) -> dict | None:
    task = get_resume_task(db, user_id, task_id)
    if not task:
        return None
    return normalize_layout_config(task.layout_config)


def save_task_layout_config(db, user_id: int, task_id: str, config: dict) -> dict | None:
    task = get_resume_task(db, user_id, task_id)
    if not task:
        return None
    normalized = normalize_layout_config(config)
    task.layout_config = normalized
    task.updated_at = datetime.utcnow()
    db.commit()
    return normalized


def delete_resume_project(db, user_id: int, project_id: str) -> bool:
    project = get_resume_project(db, user_id, project_id)
    if not project:
        return False
    task_rows = db.query(ProjectTask.id, ProjectTask.session_id).filter(
        ProjectTask.project_id == project_id,
        ProjectTask.user_id == user_id,
    ).all()
    task_ids = [row[0] for row in task_rows]
    task_session_ids = [row[1] for row in task_rows]
    if task_ids:
        db.query(ResumeEditLock).filter(
            ResumeEditLock.user_id == user_id,
            ResumeEditLock.task_id.in_(task_ids),
        ).delete(synchronize_session=False)
        db.query(ResumeRevision).filter(
            ResumeRevision.user_id == user_id,
            ResumeRevision.task_id.in_(task_ids),
        ).delete(synchronize_session=False)
        db.query(AgentMemoryState).filter(
            AgentMemoryState.user_id == user_id,
            AgentMemoryState.task_id.in_(task_ids),
        ).delete(synchronize_session=False)
        db.query(AgentSkillState).filter(
            AgentSkillState.user_id == user_id,
            AgentSkillState.task_id.in_(task_ids),
        ).delete(synchronize_session=False)
        context_rows = db.query(ConversationContext).filter(
            ConversationContext.user_id == user_id,
            ConversationContext.task_id.in_(task_ids),
        ).all()
        context_session_ids = [row.session_id for row in context_rows]
        conversation_session_ids = task_session_ids + context_session_ids
        if conversation_session_ids:
            db.query(Conversation).filter(
                Conversation.user_id == user_id,
                Conversation.session_id.in_(conversation_session_ids),
            ).delete(synchronize_session=False)
        db.query(ConversationContext).filter(
            ConversationContext.user_id == user_id,
            ConversationContext.task_id.in_(task_ids),
        ).delete(synchronize_session=False)
    db.query(ProjectTask).filter(
        ProjectTask.project_id == project_id,
        ProjectTask.user_id == user_id,
    ).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    return True


def delete_resume_task(db, user_id: int, task_id: str) -> str:
    task = get_resume_task(db, user_id, task_id)
    if not task:
        return "not_found"
    if task.is_base:
        return "base_task"
    db.query(ResumeEditLock).filter(
        ResumeEditLock.user_id == user_id,
        ResumeEditLock.task_id == task_id,
    ).delete(synchronize_session=False)
    db.query(ResumeRevision).filter(
        ResumeRevision.user_id == user_id,
        ResumeRevision.task_id == task_id,
    ).delete(synchronize_session=False)
    db.query(AgentMemoryState).filter(
        AgentMemoryState.user_id == user_id,
        AgentMemoryState.task_id == task_id,
    ).delete(synchronize_session=False)
    db.query(AgentSkillState).filter(
        AgentSkillState.user_id == user_id,
        AgentSkillState.task_id == task_id,
    ).delete(synchronize_session=False)
    context_rows = db.query(ConversationContext).filter(
        ConversationContext.user_id == user_id,
        ConversationContext.task_id == task_id,
    ).all()
    conversation_session_ids = [task.session_id] + [row.session_id for row in context_rows]
    db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id.in_(conversation_session_ids),
    ).delete(synchronize_session=False)
    db.query(ConversationContext).filter(
        ConversationContext.user_id == user_id,
        ConversationContext.task_id == task_id,
    ).delete(synchronize_session=False)
    db.delete(task)
    db.commit()
    return "deleted"


def get_user_photo(db, user_id: int) -> str:
    task = _active_task(db, user_id)
    if task:
        return task.photo or ""
    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    return resume.photo if resume and resume.photo else ""


def get_user_resume(db, user_id: int) -> dict:
    """获取用户简历"""
    task = _active_task(db, user_id)
    if task:
        return normalize_resume_data(task.resume_data or {})
    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    return normalize_resume_data(resume.resume_data or {}) if resume else {}


def get_translation_memory(db, user_id: int, memory_ids: list[str]) -> dict[str, str]:
    """Return cached translations owned by the current user."""
    if not memory_ids:
        return {}
    rows = db.query(TranslationMemory).filter(
        TranslationMemory.user_id == user_id,
        TranslationMemory.id.in_(memory_ids),
    ).all()
    return {row.id: row.translated_text for row in rows}


def save_translation_memory(
    db,
    user_id: int,
    *,
    memory_id: str,
    source_language: str,
    target_language: str,
    context_key: str,
    source_hash: str,
    source_text: str,
    translated_text: str,
) -> None:
    """Upsert one deterministic translation-memory entry."""
    row = db.query(TranslationMemory).filter(
        TranslationMemory.id == memory_id,
        TranslationMemory.user_id == user_id,
    ).first()
    if row is None:
        row = TranslationMemory(id=memory_id, user_id=user_id)
        db.add(row)
    row.source_language = source_language
    row.target_language = target_language
    row.context_key = context_key
    row.source_hash = source_hash
    row.source_text = source_text
    row.translated_text = translated_text
    row.updated_at = datetime.utcnow()


def _translation_scope(db, user_id: int) -> tuple[str, str | None]:
    task = _active_task(db, user_id)
    return (f"task:{task.id}", task.id) if task else (f"legacy-user:{user_id}", None)


def get_resume_translation_state(db, user_id: int):
    scope_id, _ = _translation_scope(db, user_id)
    return db.query(ResumeTranslationState).filter(
        ResumeTranslationState.scope_id == scope_id,
        ResumeTranslationState.user_id == user_id,
    ).first()


def save_resume_translation_state(
    db,
    user_id: int,
    *,
    source_digest: str,
    source_data: dict,
    translated_data: dict,
):
    scope_id, task_id = _translation_scope(db, user_id)
    row = db.query(ResumeTranslationState).filter(
        ResumeTranslationState.scope_id == scope_id,
        ResumeTranslationState.user_id == user_id,
    ).first()
    if row is None:
        row = ResumeTranslationState(scope_id=scope_id, user_id=user_id, task_id=task_id)
        db.add(row)
    row.source_digest = source_digest
    row.source_data = deepcopy(source_data)
    row.translated_data = deepcopy(translated_data)
    row.updated_at = datetime.utcnow()
    db.commit()
    return row


def get_parsing_status(db, user_id: int) -> str:
    """获取简历解析状态"""
    try:
        task = _active_task(db, user_id)
        if task:
            return task.parsing_status or "none"
        resume = db.query(Resume).filter(Resume.user_id == user_id).first()
        return resume.parsing_status if resume else "none"
    except Exception:
        # 如果表结构有问题，返回默认值
        return "none"


def set_parsing_status(db, user_id: int, status: str):
    """设置简历解析状态"""
    task = _active_task(db, user_id)
    if task:
        task.parsing_status = status
        task.updated_at = datetime.utcnow()
        db.commit()
        return
    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    if resume:
        resume.parsing_status = status
    else:
        # 如果简历不存在，先创建
        resume = Resume(user_id=user_id, parsing_status=status)
        db.add(resume)
    db.commit()


def set_source_page_count(db, user_id: int, page_count: int):
    """Store the uploaded source document page count for automatic layout."""
    task = _active_task(db, user_id)
    if not task:
        return
    task.source_page_count = max(1, int(page_count or 1))
    task.updated_at = datetime.utcnow()
    db.commit()


def save_user_resume(db, user_id: int, data: dict, name: str = "默认简历", photo: str = None):
    """保存用户简历
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        data: 简历数据JSON
        name: 简历名称
        photo: 证件照base64编码（可选，如果为None则从data中提取）
    """
    # Keep track of whether the caller explicitly sent the photo field.  An
    # empty value is a deliberate removal from the editor, while an omitted
    # field remains backward-compatible with callers that only update resume
    # text and expect the stored photo to be preserved.
    raw_basics = data.get("basics") if isinstance(data, dict) else None
    photo_field_supplied = (
        (isinstance(raw_basics, dict) and "photo" in raw_basics)
        or (isinstance(data, dict) and "photo" in data)
    )
    photo_argument_supplied = photo is not None
    data = normalize_resume_data(data)
    task = _active_task(db, user_id)
    if task:
        existing_photo = task.photo or ""
        if photo is None:
            photo = data.get("basics", {}).get("photo", "")
        if not photo and existing_photo and not photo_field_supplied and not photo_argument_supplied:
            photo = existing_photo
        if data and "basics" in data:
            data = {**data, "basics": {**data.get("basics", {})}}
            data["basics"].pop("photo", None)
        task.resume_data = data
        task.photo = photo or ""
        if task.is_base:
            project = db.query(ResumeProject).filter(ResumeProject.id == task.project_id).first()
            if project:
                project.base_resume_data = data
                project.photo = photo or ""
                if project.title in {"未命名简历", "未命名简历组"}:
                    project.title = data.get("basics", {}).get("name") or name
                project.updated_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        db.commit()
        return task

    # 先获取现有数据（用于保留原有证件照）
    existing_resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    existing_photo = existing_resume.photo if existing_resume and existing_resume.photo else ""
    
    # 提取并分离证件照
    if photo is None:
        photo = data.get('basics', {}).get('photo', '')
    
    # 如果新数据没有 photo但数据库已有 photo，保留原有证件照
    if not photo and existing_photo and not photo_field_supplied and not photo_argument_supplied:
        photo = existing_photo
    
    # 从 data 中移除 photo 字段
    if data and 'basics' in data:
        data = {**data, 'basics': {**data.get('basics', {})}}
        data['basics'].pop('photo', None)
    
    if existing_resume:
        existing_resume.resume_data = data
        existing_resume.name = name
        existing_resume.photo = photo
    else:
        resume = Resume(user_id=user_id, resume_data=data, name=name, photo=photo)
        db.add(resume)
    db.commit()
    return existing_resume if existing_resume else resume


def get_user_jd(db, user_id: int) -> dict:
    """获取用户JD"""
    task = _active_task(db, user_id)
    if task:
        return task.jd_data or {}
    jd = db.query(JobDescription).filter(JobDescription.user_id == user_id).first()
    return jd.jd_data if jd else {}


def save_user_jd(db, user_id: int, data: dict, company: str = "", position: str = ""):
    """保存用户JD"""
    task = _active_task(db, user_id)
    if task:
        task.jd_data = data
        task.updated_at = datetime.utcnow()
        db.commit()
        return task
    jd = db.query(JobDescription).filter(JobDescription.user_id == user_id).first()
    if jd:
        jd.jd_data = data
        jd.company = company
        jd.position = position
    else:
        jd = JobDescription(user_id=user_id, jd_data=data, company=company, position=position)
        db.add(jd)
    db.commit()
    return jd


def save_conversation(db, user_id: int, session_id: str, messages: list):
    """保存对话历史"""
    task = _active_task(db, user_id)
    context = _context_query(db, user_id, session_id) if task else None
    if task and (not context or context.context_type == "main"):
        task.messages = messages
        task.last_accessed = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        db.commit()
        return task
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
    return conv


def get_conversation(db, user_id: int, session_id: str) -> list:
    """获取对话历史"""
    task = _active_task(db, user_id)
    context = _context_query(db, user_id, session_id) if task else None
    if task and (not context or context.context_type == "main"):
        task.last_accessed = datetime.utcnow()
        db.commit()
        return task.messages or []
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    if conv:
        # 更新最后访问时间
        conv.last_accessed = datetime.utcnow()
        db.commit()
    return conv.messages if conv else []


def check_invite_code(db, code: str) -> bool:
    """检查邀请码是否有效"""
    invite = db.query(InviteCode).filter(InviteCode.code == str(code or "").strip()).first()
    return invite and not invite.is_used


def use_invite_code(db, code: str, *, commit: bool = True):
    """使用邀请码"""
    invite = db.query(InviteCode).filter(InviteCode.code == code).first()
    if invite:
        invite.is_used = True
        if commit:
            db.commit()


def register_user_with_invite(db, email: str, hashed_password: str, invite_code: str):
    """Atomically consume one invite code and create its user."""
    normalized_email = str(email or "").strip().lower()
    normalized_code = str(invite_code or "").strip()
    try:
        invite = (
            db.query(InviteCode)
            .filter(InviteCode.code == normalized_code)
            .with_for_update()
            .first()
        )
        if not invite or invite.is_used:
            raise ValueError("邀请码无效或已使用")
        if get_user_by_email(db, normalized_email):
            raise ValueError("邮箱已注册")
        user = create_user(
            db,
            normalized_email,
            hashed_password,
            normalized_code,
            commit=False,
        )
        invite.is_used = True
        db.commit()
        db.refresh(user)
        return user
    except Exception:
        db.rollback()
        raise


def create_invite_code(db, code: str):
    """创建邀请码"""
    invite = InviteCode(code=code)
    db.add(invite)
    db.commit()
    return invite


def _agent_memory_scope(db, user_id: int, session_id: str) -> tuple[str, str | None]:
    task = _active_task(db, user_id)
    if task:
        normalized_session = str(session_id or "")
        # Keep the legacy main-task scope stable so existing summaries remain
        # readable. Mission sessions are isolated by their own session id.
        if normalized_session in {"", str(task.session_id)}:
            return f"task:{task.id}", task.id
        context = get_context_by_session(db, user_id, task.id, normalized_session)
        if context:
            return f"task:{task.id}:context:{context.session_id}", task.id
        # A caller that has not created a context yet must not fall back to the
        # active task's shared scope. This keeps arbitrary session ids isolated.
        return f"conversation:{user_id}:{normalized_session}", None
    return f"conversation:{user_id}:{session_id}", None


def _split_legacy_memory(context: list) -> tuple[str, list]:
    items = list(context or [])
    if not items:
        return "", []
    first = items[0] if isinstance(items[0], dict) else {}
    first_type = str(first.get("type", "")).lower()
    first_content = str(first.get("content", "") or "")
    if first_type in {"system", "systemmessage"} and not first_content.startswith("系统事件："):
        return first_content, items[1:]
    return "", items


def get_agent_memory_state(db, user_id: int, session_id: str) -> dict:
    """Load layered memory, lazily falling back to the legacy context field."""
    scope_id, task_id = _agent_memory_scope(db, user_id, session_id)
    memory = db.query(AgentMemoryState).filter(
        AgentMemoryState.scope_id == scope_id,
        AgentMemoryState.user_id == user_id,
    ).first()
    if memory:
        return {
            "scope_id": scope_id,
            "task_id": task_id,
            "summary": memory.summary or "",
            "recent_messages": memory.recent_messages or [],
            "version": memory.version or 0,
        }

    task = _active_task(db, user_id)
    context = _context_query(db, user_id, session_id) if task else None
    if task and (not context or context.context_type == "main"):
        legacy_context = task.compressed_context or []
    else:
        conversation = db.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.session_id == session_id,
        ).first()
        legacy_context = conversation.compressed_context if conversation else []
    summary, recent_messages = _split_legacy_memory(legacy_context)
    return {
        "scope_id": scope_id,
        "task_id": task_id,
        "summary": summary,
        "recent_messages": recent_messages,
        "version": 0,
    }


def save_agent_memory_state(
    db,
    user_id: int,
    session_id: str,
    summary: str,
    recent_messages: list,
    expected_version: int,
) -> int:
    """Persist layered memory with optimistic concurrency control."""
    scope_id, task_id = _agent_memory_scope(db, user_id, session_id)
    now = datetime.utcnow()
    memory = db.query(AgentMemoryState).filter(
        AgentMemoryState.scope_id == scope_id,
        AgentMemoryState.user_id == user_id,
    ).first()
    if memory is None:
        if expected_version not in {None, 0}:
            raise MemoryVersionConflict("记忆状态版本已变化，请重新加载后重试")
        memory = AgentMemoryState(
            scope_id=scope_id,
            task_id=task_id,
            user_id=user_id,
            session_id=session_id,
            summary=summary or "",
            recent_messages=recent_messages or [],
            version=1,
            updated_at=now,
        )
        db.add(memory)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise MemoryVersionConflict("记忆状态已由另一请求创建，请重新加载后重试") from exc
        return 1

    updated = db.query(AgentMemoryState).filter(
        AgentMemoryState.scope_id == scope_id,
        AgentMemoryState.user_id == user_id,
        AgentMemoryState.version == int(expected_version or 0),
    ).update({
        AgentMemoryState.summary: summary or "",
        AgentMemoryState.recent_messages: recent_messages or [],
        AgentMemoryState.session_id: session_id,
        AgentMemoryState.version: int(expected_version or 0) + 1,
        AgentMemoryState.updated_at: now,
    }, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise MemoryVersionConflict("记忆状态版本已变化，请重新加载后重试")
    db.commit()
    return int(expected_version or 0) + 1


def get_agent_skill_state(db, user_id: int, session_id: str, skill_name: str) -> dict:
    """Load private Skill state without exposing it through conversation memory."""
    memory_scope, task_id = _agent_memory_scope(db, user_id, session_id)
    scope_id = f"{memory_scope}:skill:{skill_name}"
    row = db.query(AgentSkillState).filter(
        AgentSkillState.scope_id == scope_id,
        AgentSkillState.user_id == user_id,
        AgentSkillState.skill_name == skill_name,
    ).first()
    return {
        "scope_id": scope_id,
        "task_id": task_id,
        "state": deepcopy(row.state_json or {}) if row else {},
        "version": int(row.version or 0) if row else 0,
    }


def save_agent_skill_state(
    db, user_id: int, session_id: str, skill_name: str,
    state: dict, expected_version: int,
) -> int:
    """Persist one Skill's private state with optimistic concurrency control."""
    memory_scope, task_id = _agent_memory_scope(db, user_id, session_id)
    scope_id = f"{memory_scope}:skill:{skill_name}"
    now = datetime.utcnow()
    row = db.query(AgentSkillState).filter(
        AgentSkillState.scope_id == scope_id,
        AgentSkillState.user_id == user_id,
        AgentSkillState.skill_name == skill_name,
    ).first()
    if row is None:
        if expected_version not in {None, 0}:
            raise MemoryVersionConflict("Skill 状态版本已变化，请重新加载后重试")
        db.add(AgentSkillState(
            scope_id=scope_id, task_id=task_id, user_id=user_id,
            session_id=session_id, skill_name=skill_name,
            state_json=deepcopy(state or {}), version=1, updated_at=now,
        ))
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise MemoryVersionConflict("Skill 状态已由另一请求创建，请重新加载后重试") from exc
        return 1
    updated = db.query(AgentSkillState).filter(
        AgentSkillState.scope_id == scope_id,
        AgentSkillState.user_id == user_id,
        AgentSkillState.skill_name == skill_name,
        AgentSkillState.version == int(expected_version or 0),
    ).update({
        AgentSkillState.state_json: deepcopy(state or {}),
        AgentSkillState.session_id: session_id,
        AgentSkillState.version: int(expected_version or 0) + 1,
        AgentSkillState.updated_at: now,
    }, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise MemoryVersionConflict("Skill 状态版本已变化，请重新加载后重试")
    db.commit()
    return int(expected_version or 0) + 1


def save_conversation_context(
    db,
    user_id: int,
    session_id: str,
    compressed_context: list,
    pending_confirmation=_PENDING_CONFIRMATION_UNSET,
):
    """保存压缩后的上下文到数据库"""
    task = _active_task(db, user_id)
    context = _context_query(db, user_id, session_id) if task else None
    if task and (not context or context.context_type == "main"):
        task.compressed_context = compressed_context
        if pending_confirmation is not _PENDING_CONFIRMATION_UNSET:
            task.pending_confirmation = pending_confirmation
        task.last_accessed = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        db.commit()
        return task
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    if conv:
        conv.compressed_context = compressed_context
        if pending_confirmation is not _PENDING_CONFIRMATION_UNSET:
            conv.pending_confirmation = pending_confirmation
        conv.last_accessed = datetime.utcnow()
    else:
        conv = Conversation(
            user_id=user_id,
            session_id=session_id,
            compressed_context=compressed_context,
            pending_confirmation=(
                None
                if pending_confirmation is _PENDING_CONFIRMATION_UNSET
                else pending_confirmation
            ),
            messages=[]  # 初始化为空，由前端通过 /save_conversation 保存
        )
        db.add(conv)
    db.commit()
    return conv


def get_pending_confirmation(db, user_id: int, session_id: str) -> dict:
    """获取待确认状态"""
    task = _active_task(db, user_id)
    context = _context_query(db, user_id, session_id) if task else None
    if task and (not context or context.context_type == "main"):
        return task.pending_confirmation
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    return conv.pending_confirmation if conv else None


def find_task_pending_confirmation(
    db,
    user_id: int,
    task_id: str,
    exclude_session_id: str = "",
) -> tuple[str, dict] | None:
    """Return any pending edit owned by a conversation of one resume task."""
    task = get_resume_task(db, user_id, task_id)
    if not task:
        return None
    if task.session_id != exclude_session_id and isinstance(task.pending_confirmation, dict):
        return task.session_id, task.pending_confirmation
    session_ids = [
        item.session_id
        for item in db.query(ConversationContext).filter(
            ConversationContext.user_id == user_id,
            ConversationContext.task_id == task_id,
            ConversationContext.status == "active",
            ConversationContext.session_id != task.session_id,
        ).all()
        if item.session_id != exclude_session_id
    ]
    if not session_ids:
        return None
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id.in_(session_ids),
        Conversation.pending_confirmation.isnot(None),
    ).order_by(Conversation.updated_at.desc()).first()
    if conv and isinstance(conv.pending_confirmation, dict):
        return conv.session_id, conv.pending_confirmation
    return None


EDIT_LOCK_GENERATING_TIMEOUT_SECONDS = 180


def acquire_resume_edit_lock(
    db,
    user_id: int,
    task_id: str,
    owner_session_id: str,
    request_id: str,
):
    """Atomically acquire a task-wide edit lock, recovering abandoned generation."""
    if not hasattr(db, "query"):
        return {"status": "generating", "request_id": request_id}
    task = get_resume_task(db, user_id, task_id)
    if not task:
        return None
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=EDIT_LOCK_GENERATING_TIMEOUT_SECONDS)
    existing = db.query(ResumeEditLock).filter(ResumeEditLock.task_id == task_id).first()
    if existing:
        same_request = (
            existing.user_id == user_id
            and existing.owner_session_id == owner_session_id
            and existing.request_id == request_id
        )
        stale_generation = existing.status == "generating" and existing.updated_at < cutoff
        if same_request:
            existing.updated_at = now
            db.commit()
            return existing
        if stale_generation:
            db.delete(existing)
            db.commit()
        else:
            return None
    row = ResumeEditLock(
        task_id=task_id,
        user_id=user_id,
        owner_session_id=owner_session_id,
        request_id=request_id,
        status="generating",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(row)
    return row


def mark_resume_edit_awaiting_confirmation(
    db, user_id: int, task_id: str, owner_session_id: str, request_id: str
) -> bool:
    if not hasattr(db, "query"):
        return True
    updated = db.query(ResumeEditLock).filter(
        ResumeEditLock.task_id == task_id,
        ResumeEditLock.user_id == user_id,
        ResumeEditLock.owner_session_id == owner_session_id,
        ResumeEditLock.request_id == request_id,
    ).update({
        ResumeEditLock.status: "awaiting_confirmation",
        ResumeEditLock.updated_at: datetime.utcnow(),
    }, synchronize_session=False)
    db.commit()
    return updated == 1


def release_resume_edit_lock(
    db,
    user_id: int,
    task_id: str,
    *,
    owner_session_id: str = "",
    request_id: str = "",
) -> bool:
    if not hasattr(db, "query"):
        return True
    query = db.query(ResumeEditLock).filter(
        ResumeEditLock.task_id == task_id,
        ResumeEditLock.user_id == user_id,
    )
    if owner_session_id:
        query = query.filter(ResumeEditLock.owner_session_id == owner_session_id)
    if request_id:
        query = query.filter(ResumeEditLock.request_id == request_id)
    deleted = query.delete(synchronize_session=False)
    db.commit()
    return bool(deleted)


def get_resume_edit_state(db, user_id: int, task_id: str) -> dict | None:
    if not hasattr(db, "query"):
        return None
    row = db.query(ResumeEditLock).filter(
        ResumeEditLock.task_id == task_id,
        ResumeEditLock.user_id == user_id,
    ).first()
    if row and row.status == "generating" and row.updated_at < (
        datetime.utcnow() - timedelta(seconds=EDIT_LOCK_GENERATING_TIMEOUT_SECONDS)
    ):
        db.delete(row)
        db.commit()
        row = None
    if row:
        return {
            "status": row.status,
            "owner_session_id": row.owner_session_id,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    legacy = find_task_pending_confirmation(db, user_id, task_id)
    if legacy:
        return {
            "status": "awaiting_confirmation",
            "owner_session_id": legacy[0],
            "updated_at": None,
        }
    return None


def clear_pending_confirmation(db, user_id: int, session_id: str):
    """清除待确认状态"""
    task = _active_task(db, user_id)
    context = _context_query(db, user_id, session_id) if task else None
    if task and (not context or context.context_type == "main"):
        task.pending_confirmation = None
        db.query(ResumeEditLock).filter(
            ResumeEditLock.task_id == task.id,
            ResumeEditLock.user_id == user_id,
            ResumeEditLock.owner_session_id == session_id,
        ).delete(synchronize_session=False)
        task.updated_at = datetime.utcnow()
        db.commit()
        return
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    if conv:
        conv.pending_confirmation = None
        if context:
            db.query(ResumeEditLock).filter(
                ResumeEditLock.task_id == context.task_id,
                ResumeEditLock.user_id == user_id,
                ResumeEditLock.owner_session_id == session_id,
            ).delete(synchronize_session=False)
        db.commit()


def get_conversation_context(db, user_id: int, session_id: str) -> list:
    """获取压缩后的上下文（用于性能优化）"""
    task = _active_task(db, user_id)
    context = _context_query(db, user_id, session_id) if task else None
    if task and (not context or context.context_type == "main"):
        task.last_accessed = datetime.utcnow()
        db.commit()
        return task.compressed_context or []
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    if conv:
        # 更新最后访问时间
        conv.last_accessed = datetime.utcnow()
        db.commit()
        return conv.compressed_context if conv.compressed_context else []
    return []


def cleanup_old_contexts(db, days: int = 7):
    """清理过期上下文（默认7天未访问的）"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    db.query(Conversation).filter(
        Conversation.last_accessed < cutoff
    ).update({"compressed_context": []})
    db.query(AgentMemoryState).filter(
        AgentMemoryState.task_id.is_(None),
        AgentMemoryState.updated_at < cutoff,
    ).delete(synchronize_session=False)
    db.query(AgentSkillState).filter(
        AgentSkillState.task_id.is_(None),
        AgentSkillState.updated_at < cutoff,
    ).delete(synchronize_session=False)
    db.commit()


def delete_conversation_context(db, user_id: int, session_id: str):
    """删除指定会话的上下文"""
    task = _active_task(db, user_id)
    context = _context_query(db, user_id, session_id) if task else None
    if task and (not context or context.context_type == "main"):
        task.compressed_context = []
        task.updated_at = datetime.utcnow()
        db.query(AgentMemoryState).filter(
            AgentMemoryState.scope_id == f"task:{task.id}",
            AgentMemoryState.user_id == user_id,
        ).delete(synchronize_session=False)
        db.query(AgentSkillState).filter(
            AgentSkillState.task_id == task.id,
            AgentSkillState.user_id == user_id,
            AgentSkillState.session_id == session_id,
        ).delete(synchronize_session=False)
        db.commit()
        return
    if context:
        db.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.session_id == context.session_id,
        ).update({
            "messages": [],
            "compressed_context": [],
            "pending_confirmation": None,
        })
        db.query(AgentMemoryState).filter(
            AgentMemoryState.scope_id == f"task:{context.task_id}:context:{context.session_id}",
            AgentMemoryState.user_id == user_id,
        ).delete(synchronize_session=False)
        db.query(AgentSkillState).filter(
            AgentSkillState.task_id == context.task_id,
            AgentSkillState.user_id == user_id,
            AgentSkillState.session_id == context.session_id,
        ).delete(synchronize_session=False)
        db.commit()
        return
    db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).update({"compressed_context": []})
    db.query(AgentMemoryState).filter(
        AgentMemoryState.scope_id == f"conversation:{user_id}:{session_id}",
        AgentMemoryState.user_id == user_id,
    ).delete(synchronize_session=False)
    db.query(AgentSkillState).filter(
        AgentSkillState.user_id == user_id,
        AgentSkillState.session_id == session_id,
    ).delete(synchronize_session=False)
    db.commit()
