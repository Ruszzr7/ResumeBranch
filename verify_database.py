#!/usr/bin/env python3
"""
验证数据库中的简历数据
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, get_db, get_user_resume

def verify_database():
    """验证数据库中的数据"""
    print("=" * 50)
    print("数据库验证")
    print("=" * 50)
    
    init_db()
    db = next(get_db())
    
    try:
        # 获取测试用户的简历
        user_id = 3  # test@example.com 的用户ID
        resume_data = get_user_resume(db, user_id)
        
        print(f"\n用户ID: {user_id}")
        print(f"简历数据: {resume_data}")
        
        if resume_data and isinstance(resume_data, dict):
            print("\n✓ 数据库验证通过")
            print(f"  - 基本信息: {resume_data.get('basics', {})}")
            print(f"  - 教育经历: {len(resume_data.get('education', []))} 条")
            print(f"  - 工作经历: {len(resume_data.get('work_experience', []))} 条")
            return True
        else:
            print("✗ 未找到简历数据")
            return False
    finally:
        db.close()

if __name__ == "__main__":
    verify_database()
