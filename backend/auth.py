"""
认证模块
JWT Token 创建/验证、密码加密
"""

from datetime import datetime, timedelta
import secrets

from jose import jwt, JWTError
import bcrypt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import os

from .config import LOCAL_USER_EMAIL, is_local_mode
from .database import create_user, get_db, get_resume_task, get_user_by_email

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24小时

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """加密密码"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def ensure_local_user(db: Session):
    """Return the fixed local user, creating it on first use."""
    user = get_user_by_email(db, LOCAL_USER_EMAIL)
    if user:
        return user

    try:
        return create_user(
            db,
            LOCAL_USER_EMAIL,
            get_password_hash(secrets.token_urlsafe(32)),
            invite_code="local-mode",
        )
    except IntegrityError:
        db.rollback()
        user = get_user_by_email(db, LOCAL_USER_EMAIL)
        if user:
            return user
        raise


def create_access_token(data: dict) -> str:
    """创建 JWT Token"""
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 JWT Token"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    x_task_id: str | None = Header(default=None, alias="X-Task-ID"),
):
    """
    获取当前用户（依赖注入）

    Returns:
        User: 当前登录用户
    Raises:
        HTTPException: 认证失败
    """
    if is_local_mode():
        user = ensure_local_user(db)
        if x_task_id:
            task = get_resume_task(db, user.id, x_task_id)
            if not task:
                raise HTTPException(status_code=404, detail="任务不存在")
            db.info["task_id"] = task.id
        return user

    credentials_exception = HTTPException(
        status_code=401,
        detail="认证失败，请重新登录",
        headers={"WWW-Authenticate": "Bearer"}
    )

    if not token:
        raise credentials_exception

    payload = decode_token(token)
    if not payload:
        raise credentials_exception

    email = payload.get("sub")
    if not email:
        raise credentials_exception

    user = get_user_by_email(db, email)
    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")

    if x_task_id:
        task = get_resume_task(db, user.id, x_task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        db.info["task_id"] = task.id

    return user


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    可选获取当前用户（未登录返回 None）
    """
    if is_local_mode():
        return ensure_local_user(db)

    if not token:
        return None

    try:
        return await get_current_user(token=token, db=db, x_task_id=None)
    except HTTPException:
        return None


def require_multi_user_mode() -> None:
    """Disable account-management endpoints while running locally."""
    if is_local_mode():
        raise HTTPException(status_code=404, detail="本地模式未启用账号管理功能")
