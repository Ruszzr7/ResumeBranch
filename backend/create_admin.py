#!/usr/bin/env python3
import os
from dotenv import load_dotenv

load_dotenv()

from .auth import get_password_hash
from .database import SessionLocal, create_user, get_user_by_email, init_db

init_db()

db = SessionLocal()
admin_email = os.getenv("ADMIN_EMAIL", "").strip()
admin_password = os.getenv("ADMIN_PASSWORD", "")

if not admin_email or not admin_password:
    db.close()
    raise SystemExit("请先在 .env 中配置 ADMIN_EMAIL 和 ADMIN_PASSWORD")

existing = get_user_by_email(db, admin_email)
if existing:
    if not existing.is_admin:
        existing.is_admin = True
        db.commit()
        print(f"用户 {admin_email} 已升级为管理员，id={existing.id}")
    else:
        print(f"管理员 {admin_email} 已存在，id={existing.id}")
else:
    hashed_pw = get_password_hash(admin_password)
    user = create_user(db, admin_email, hashed_pw, invite_code="admin", is_admin=True)
    print(f"用户 {admin_email} 创建成功，id={user.id}")

db.close()
