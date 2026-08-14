"""
数据库模块
SQLAlchemy 模型定义和数据库连接
"""

import os
import uuid
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, JSON, Text, inspect, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
from dotenv import load_dotenv

from .resume_data import normalize_resume_data
from .layout_config import default_layout_config, normalize_layout_config

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/deepagents.db")

database_backend = make_url(DATABASE_URL).get_backend_name()
engine_options = {}

if database_backend == "sqlite":
    engine_options["connect_args"] = {"check_same_thread": False}
elif database_backend == "mysql":
    # Detect stale pooled connections and recycle them before MySQL's idle timeout.
    engine_options.update(pool_pre_ping=True, pool_recycle=3600)

engine = create_engine(DATABASE_URL, **engine_options)
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


class ResumeProject(Base):
    """A canonical resume shared as the source for JD-specific tasks."""
    __tablename__ = "resume_projects"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(120), nullable=False, default="未命名简历")
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
    title = Column(String(120), nullable=False, default="基础简历")
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


class AgentMemoryState(Base):
    """Layered conversation memory stored separately from canonical resume data."""
    __tablename__ = "agent_memory_states"
    scope_id = Column(String(100), primary_key=True)
    task_id = Column(String(36), nullable=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String(36), nullable=False)
    summary = Column(large_text_type, default="")
    recent_messages = Column(JSON, default=list)
    interview_memory = Column(JSON, default=dict)
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
    migrate_agent_memory_interview_fields()
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


def migrate_agent_memory_interview_fields():
    """Add structured, source-traceable interview memory to existing databases."""
    inspector = inspect(engine)
    if "agent_memory_states" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("agent_memory_states")}
    if "interview_memory" not in columns:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE agent_memory_states ADD COLUMN interview_memory JSON"
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
                print(f"[Migration] 跳过 legacy resume {resume.id}: {exc}")
                continue
            if normalized != (resume.resume_data or {}):
                resume.resume_data = normalized
                changed += 1

        for project in db.query(ResumeProject).all():
            try:
                normalized = normalize_resume_data(project.base_resume_data or {})
            except (TypeError, ValueError) as exc:
                print(f"[Migration] 跳过 resume project {project.id}: {exc}")
                continue
            if normalized != (project.base_resume_data or {}):
                project.base_resume_data = normalized
                changed += 1

        for task in db.query(ProjectTask).all():
            try:
                normalized = normalize_resume_data(task.resume_data or {})
            except (TypeError, ValueError) as exc:
                print(f"[Migration] 跳过 resume task {task.id}: {exc}")
                continue
            if normalized != (task.resume_data or {}):
                task.resume_data = normalized
                changed += 1

        if changed:
            db.commit()
            print(f"[Migration] 已规范化 {changed} 份简历的教育成绩字段")
    except Exception as exc:
        db.rollback()
        # A normalization issue should not prevent the application from starting.
        print(f"[Migration] 教育成绩字段迁移跳过: {exc}")
    finally:
        db.close()


# =============================================================================
# 数据访问函数
# =============================================================================

def get_user_by_email(db, email: str):
    """根据邮箱获取用户"""
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db, user_id: int):
    """根据ID获取用户"""
    return db.query(User).filter(User.id == user_id).first()


def create_user(db, email: str, hashed_password: str, invite_code: str):
    """创建用户"""
    user = User(email=email, hashed_password=hashed_password, invite_code=invite_code)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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
                title="基础简历",
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
        title="基础简历",
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


def create_resume_project(db, user_id: int, title: str = "未命名简历"):
    project_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    project = ResumeProject(
        id=project_id,
        user_id=user_id,
        title=(title or "未命名简历").strip()[:120],
    )
    task = ProjectTask(
        id=task_id,
        project_id=project_id,
        user_id=user_id,
        title="基础简历",
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
    if resume_digest(current_data) != resume_digest(revision.after_data or {}):
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
    task_ids = [row[0] for row in db.query(ProjectTask.id).filter(
        ProjectTask.project_id == project_id,
        ProjectTask.user_id == user_id,
    ).all()]
    if task_ids:
        db.query(ResumeRevision).filter(
            ResumeRevision.user_id == user_id,
            ResumeRevision.task_id.in_(task_ids),
        ).delete(synchronize_session=False)
        db.query(AgentMemoryState).filter(
            AgentMemoryState.user_id == user_id,
            AgentMemoryState.task_id.in_(task_ids),
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
    db.query(ResumeRevision).filter(
        ResumeRevision.user_id == user_id,
        ResumeRevision.task_id == task_id,
    ).delete(synchronize_session=False)
    db.query(AgentMemoryState).filter(
        AgentMemoryState.user_id == user_id,
        AgentMemoryState.task_id == task_id,
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
    print(f"[save_user_resume] 开始保存，用户ID={user_id}")
    print(f"[save_user_resume] 传入 data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
    
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
                if project.title == "未命名简历":
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
        print(f"[save_user_resume] 现有数据存在，basics.name: {existing_resume.resume_data.get('basics', {}).get('name', 'N/A')}")
        print(f"[save_user_resume] 新数据 basics.name: {data.get('basics', {}).get('name', 'N/A')}")
        existing_resume.resume_data = data
        existing_resume.name = name
        existing_resume.photo = photo
    else:
        print(f"[save_user_resume] 创建新简历")
        resume = Resume(user_id=user_id, resume_data=data, name=name, photo=photo)
        db.add(resume)
    db.commit()
    print(f"[save_user_resume] 保存完成")
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
    if task:
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
    if task:
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
    invite = db.query(InviteCode).filter(InviteCode.code == code).first()
    return invite and not invite.is_used


def use_invite_code(db, code: str):
    """使用邀请码"""
    invite = db.query(InviteCode).filter(InviteCode.code == code).first()
    if invite:
        invite.is_used = True
        db.commit()


def create_invite_code(db, code: str):
    """创建邀请码"""
    invite = InviteCode(code=code)
    db.add(invite)
    db.commit()
    return invite


def _agent_memory_scope(db, user_id: int, session_id: str) -> tuple[str, str | None]:
    task = _active_task(db, user_id)
    if task:
        return f"task:{task.id}", task.id
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
            "interview_memory": memory.interview_memory or {},
            "version": memory.version or 0,
        }

    task = _active_task(db, user_id)
    if task:
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
        "interview_memory": {},
        "version": 0,
    }


def save_agent_memory_state(
    db,
    user_id: int,
    session_id: str,
    summary: str,
    recent_messages: list,
    expected_version: int,
    interview_memory: dict | None = None,
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
            interview_memory=interview_memory or {},
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
        AgentMemoryState.interview_memory: interview_memory or {},
        AgentMemoryState.session_id: session_id,
        AgentMemoryState.version: int(expected_version or 0) + 1,
        AgentMemoryState.updated_at: now,
    }, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise MemoryVersionConflict("记忆状态版本已变化，请重新加载后重试")
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
    if task:
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
    if task:
        return task.pending_confirmation
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    return conv.pending_confirmation if conv else None


def clear_pending_confirmation(db, user_id: int, session_id: str):
    """清除待确认状态"""
    task = _active_task(db, user_id)
    if task:
        task.pending_confirmation = None
        task.updated_at = datetime.utcnow()
        db.commit()
        return
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    if conv:
        conv.pending_confirmation = None
        db.commit()


def get_conversation_context(db, user_id: int, session_id: str) -> list:
    """获取压缩后的上下文（用于性能优化）"""
    task = _active_task(db, user_id)
    if task:
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
    db.commit()


def delete_conversation_context(db, user_id: int, session_id: str):
    """删除指定会话的上下文"""
    task = _active_task(db, user_id)
    if task:
        task.compressed_context = []
        task.updated_at = datetime.utcnow()
        db.query(AgentMemoryState).filter(
            AgentMemoryState.scope_id == f"task:{task.id}",
            AgentMemoryState.user_id == user_id,
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
    db.commit()
