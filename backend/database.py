"""
数据库模块
SQLAlchemy 模型定义和数据库连接
"""

import os
import uuid
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, JSON, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
from dotenv import load_dotenv

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
    jd_data = Column(JSON, default=dict)
    messages = Column(JSON, default=list)
    compressed_context = Column(JSON, default=list)
    pending_confirmation = Column(JSON, default=None)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkspaceState(Base):
    """Tracks completion of the one-time legacy workspace migration."""
    __tablename__ = "workspace_states"
    user_id = Column(Integer, primary_key=True)
    legacy_migrated = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


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


def _active_task(db):
    task_id = db.info.get("task_id")
    return db.query(ProjectTask).filter(ProjectTask.id == task_id).first() if task_id else None


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


def create_resume_task(
    db,
    user_id: int,
    project_id: str,
    title: str = "新岗位版本",
    copy_base_resume: bool = True,
):
    project = get_resume_project(db, user_id, project_id)
    if not project:
        return None
    task_id = str(uuid.uuid4())
    task = ProjectTask(
        id=task_id,
        project_id=project_id,
        user_id=user_id,
        title=(title or "新岗位版本").strip()[:120],
        is_base=False,
        session_id=task_id,
        resume_data=(project.base_resume_data or {}) if copy_base_resume else {},
        photo=(project.photo or "") if copy_base_resume else "",
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


def delete_resume_project(db, user_id: int, project_id: str) -> bool:
    project = get_resume_project(db, user_id, project_id)
    if not project:
        return False
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
    db.delete(task)
    db.commit()
    return "deleted"


def get_user_photo(db, user_id: int) -> str:
    task = _active_task(db)
    if task:
        return task.photo or ""
    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    return resume.photo if resume and resume.photo else ""


def get_user_resume(db, user_id: int) -> dict:
    """获取用户简历"""
    task = _active_task(db)
    if task:
        return task.resume_data or {}
    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    return resume.resume_data if resume else {}


def get_parsing_status(db, user_id: int) -> str:
    """获取简历解析状态"""
    try:
        task = _active_task(db)
        if task:
            return task.parsing_status or "none"
        resume = db.query(Resume).filter(Resume.user_id == user_id).first()
        return resume.parsing_status if resume else "none"
    except Exception:
        # 如果表结构有问题，返回默认值
        return "none"


def set_parsing_status(db, user_id: int, status: str):
    """设置简历解析状态"""
    task = _active_task(db)
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


def save_user_resume(db, user_id: int, data: dict, name: str = "默认简历", photo: str = None):
    """保存用户简历
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        data: 简历数据JSON
        name: 简历名称
        photo: 证件照base64编码（可选，如果为None则从data中提取）
    """
    print(f"[save_user_resume] 开始保存，用户ID={user_id}")
    print(f"[save_user_resume] 传入 data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
    
    task = _active_task(db)
    if task:
        existing_photo = task.photo or ""
        if photo is None:
            photo = data.get("basics", {}).get("photo", "")
        if not photo and existing_photo:
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
    if not photo and existing_photo:
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
    task = _active_task(db)
    if task:
        return task.jd_data or {}
    jd = db.query(JobDescription).filter(JobDescription.user_id == user_id).first()
    return jd.jd_data if jd else {}


def save_user_jd(db, user_id: int, data: dict, company: str = "", position: str = ""):
    """保存用户JD"""
    task = _active_task(db)
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
    task = _active_task(db)
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
    task = _active_task(db)
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


def save_conversation_context(db, user_id: int, session_id: str, compressed_context: list, pending_confirmation: dict = None):
    """保存压缩后的上下文到数据库"""
    task = _active_task(db)
    if task:
        task.compressed_context = compressed_context
        if pending_confirmation is not None:
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
        if pending_confirmation is not None:
            conv.pending_confirmation = pending_confirmation
        conv.last_accessed = datetime.utcnow()
    else:
        conv = Conversation(
            user_id=user_id,
            session_id=session_id,
            compressed_context=compressed_context,
            pending_confirmation=pending_confirmation,
            messages=[]  # 初始化为空，由前端通过 /save_conversation 保存
        )
        db.add(conv)
    db.commit()
    return conv


def get_pending_confirmation(db, user_id: int, session_id: str) -> dict:
    """获取待确认状态"""
    task = _active_task(db)
    if task:
        return task.pending_confirmation
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    return conv.pending_confirmation if conv else None


def clear_pending_confirmation(db, user_id: int, session_id: str):
    """清除待确认状态"""
    task = _active_task(db)
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
    task = _active_task(db)
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
    db.commit()


def delete_conversation_context(db, user_id: int, session_id: str):
    """删除指定会话的上下文"""
    task = _active_task(db)
    if task:
        task.compressed_context = []
        task.updated_at = datetime.utcnow()
        db.commit()
        return
    db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).update({"compressed_context": []})
    db.commit()
