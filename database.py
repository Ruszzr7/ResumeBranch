"""
数据库模块
SQLAlchemy 模型定义和数据库连接
"""

import os
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


def get_user_resume(db, user_id: int) -> dict:
    """获取用户简历"""
    resume = db.query(Resume).filter(Resume.user_id == user_id).first()
    return resume.resume_data if resume else {}


def get_parsing_status(db, user_id: int) -> str:
    """获取简历解析状态"""
    try:
        resume = db.query(Resume).filter(Resume.user_id == user_id).first()
        return resume.parsing_status if resume else "none"
    except Exception:
        # 如果表结构有问题，返回默认值
        return "none"


def set_parsing_status(db, user_id: int, status: str):
    """设置简历解析状态"""
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
    jd = db.query(JobDescription).filter(JobDescription.user_id == user_id).first()
    return jd.jd_data if jd else {}


def save_user_jd(db, user_id: int, data: dict, company: str = "", position: str = ""):
    """保存用户JD"""
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
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    return conv.pending_confirmation if conv else None


def clear_pending_confirmation(db, user_id: int, session_id: str):
    """清除待确认状态"""
    conv = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).first()
    if conv:
        conv.pending_confirmation = None
        db.commit()


def get_conversation_context(db, user_id: int, session_id: str) -> list:
    """获取压缩后的上下文（用于性能优化）"""
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
    db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id
    ).update({"compressed_context": []})
    db.commit()
