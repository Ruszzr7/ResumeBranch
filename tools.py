"""
工具函数模块
数据访问层 - 提供数据库操作函数
"""

import os
import json
from sqlalchemy.orm import Session
from database import get_db, save_user_resume, get_user_resume, save_user_jd, get_user_jd


def list_directory(path: str) -> str:
    """列出目录中的文件和子目录"""
    try:
        items = os.listdir(path)
        return f"目录 {path} 中的内容：\n" + "\n".join(items)
    except Exception as e:
        return f"列出目录失败：{str(e)}"


def read_file(file_path: str) -> str:
    """
    读取文件内容（已废弃，不再使用）

    注意：在多用户环境下，文件操作被数据库操作替代。
    此函数保留用于向后兼容，但实际应使用 load_resume_from_db。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"文件 {path} 的内容：\n{content}"
    except Exception as e:
        return f"读取文件失败：{str(e)}"


def write_file(file_path: str, content: str) -> str:
    """
    写入文件内容（已废弃，不再使用）

    注意：在多用户环境下，文件操作被数据库操作替代。
    此函数保留用于向后兼容，但实际应使用 save_user_resume。
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"文件 {file_path} 已成功写入"
    except Exception as e:
        return f"写入文件失败：{str(e)}"


# =============================================================================
# 数据库操作函数（新增）
# =============================================================================

def update_resume(data: dict, user_id: int = None, db: Session = None) -> str:
    """
    更新用户简历到 SQLite

    Args:
        data: 简历数据字典
        user_id: 用户ID（可选，如果不提供则从 db 获取）
        db: 数据库会话（可选，如果不提供则创建新的）

    Returns:
        str: 操作结果消息
    """
    if db is None:
        db_gen = get_db()
        db = next(db_gen)

    try:
        # 如果没有提供 user_id，从 resume_agent 模块获取全局用户ID
        import resume_agent
        if user_id is None:
            if resume_agent.current_user_id:
                user_id = resume_agent.current_user_id
            else:
                return "错误：无法确定用户身份，请先登录"

        # 确保 user_id 是有效的整数
        if user_id is None:
            return "错误：无法确定用户身份，请先登录"

        save_user_resume(db, user_id, data)
        db.commit()  # 显式提交事务
        return "简历已成功保存到数据库"
    except Exception as e:
        db.rollback()  # 回滚事务
        return f"保存失败：{str(e)}"
    finally:
        if db:
            db.close()


def load_resume(user_id: int = None, db: Session = None) -> dict:
    """
    从 SQLite 加载用户简历

    Args:
        user_id: 用户ID（可选）
        db: 数据库会话（可选）

    Returns:
        dict: 简历数据，如果不存在返回空字典
    """
    if db is None:
        db_gen = get_db()
        db = next(db_gen)

    try:
        # 如果没有提供 user_id，从 resume_agent 模块获取全局用户ID
        import resume_agent
        if user_id is None:
            if resume_agent.current_user_id:
                user_id = resume_agent.current_user_id
            else:
                return {}

        return get_user_resume(db, user_id)
    except Exception as e:
        return {"error": f"加载失败：{str(e)}"}
    finally:
        if db:
            db.close()


def save_jd(data: dict, user_id: int = None, db: Session = None) -> str:
    """
    保存用户 JD 数据到 SQLite

    Args:
        data: JD 数据字典
        user_id: 用户ID（可选）
        db: 数据库会话（可选）

    Returns:
        str: 操作结果消息
    """
    if db is None:
        db_gen = get_db()
        db = next(db_gen)

    try:
        import resume_agent
        if user_id is None:
            if resume_agent.current_user_id:
                user_id = resume_agent.current_user_id
            else:
                return "错误：无法确定用户身份"

        company = data.get('company', '')
        position = data.get('position', '')
        save_user_jd(db, user_id, data, company, position)
        return "JD 数据已成功保存"
    except Exception as e:
        return f"保存失败：{str(e)}"
    finally:
        if db:
            db.close()


def load_jd(user_id: int = None, db: Session = None) -> dict:
    """
    从 SQLite 加载用户 JD 数据

    Args:
        user_id: 用户ID（可选）
        db: 数据库会话（可选）

    Returns:
        dict: JD 数据，如果不存在返回空字典
    """
    if db is None:
        db_gen = get_db()
        db = next(db_gen)

    try:
        import resume_agent
        if user_id is None:
            if resume_agent.current_user_id:
                user_id = resume_agent.current_user_id
            else:
                return {}

        return get_user_jd(db, user_id)
    except Exception as e:
        return {"error": f"加载失败：{str(e)}"}
    finally:
        if db:
            db.close()
