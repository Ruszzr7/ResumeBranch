#!/usr/bin/env python3
"""
测试PDF上传和解析功能
"""

import requests
import base64
import json
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import init_db, get_db, create_user, get_user_by_email
from auth import get_password_hash
from sqlalchemy.orm import Session

API_BASE = "http://localhost:8000"

def create_test_user():
    """创建测试用户"""
    init_db()
    db = next(get_db())
    try:
        # 检查是否已存在测试用户
        user = get_user_by_email(db, "test@example.com")
        if user:
            print("✓ 测试用户已存在")
            return user
        
        # 检查并创建邀请码
        from database import check_invite_code, create_invite_code, use_invite_code
        invite_code = "TESTCODE1"
        if not check_invite_code(db, invite_code):
            create_invite_code(db, invite_code)
            print(f"✓ 创建邀请码: {invite_code}")
        
        # 使用邀请码
        use_invite_code(db, invite_code)
        
        # 创建新用户（使用现有的create_user函数）
        from database import create_user
        user = create_user(db, "test@example.com", get_password_hash("testpassword123"), invite_code)
        print(f"✓ 创建测试用户成功: ID={user.id}")
        return user
    finally:
        db.close()

def get_token():
    """获取认证token"""
    response = requests.post(
        f"{API_BASE}/auth/login",
        data={
            "username": "test@example.com",
            "password": "testpassword123"
        }
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"✗ 获取token失败: {response.text}")
        return None

def test_image_upload(token):
    """测试图片上传"""
    print("\n=== 测试1: 图片上传 ===")
    
    # 使用现有的测试图片
    image_path = "img/2.png"
    if not os.path.exists(image_path):
        print(f"✗ 测试图片不存在: {image_path}")
        return False
    
    # 读取图片并转换为base64
    with open(image_path, "rb") as f:
        image_content = f.read()
        base64_image = base64.b64encode(image_content).decode("utf-8")
        mime_type = "image/png"
    
    # 发送请求
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "image": f"data:{mime_type};base64,{base64_image}"
    }
    
    response = requests.post(
        f"{API_BASE}/api/resume/parse_and_save",
        json=payload,
        headers=headers,
        timeout=120
    )
    
    result = response.json()
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
    
    if response.status_code == 200 and result.get("success"):
        print("✓ 图片上传测试通过")
        return True
    else:
        print("✗ 图片上传测试失败")
        return False

def test_health():
    """健康检查"""
    print("\n=== 健康检查 ===")
    response = requests.post(f"{API_BASE}/health")
    print(f"状态: {response.status_code}")
    print(f"响应: {response.json()}")
    return response.status_code == 200

def main():
    print("=" * 50)
    print("PDF/图片上传功能测试")
    print("=" * 50)
    
    # 1. 健康检查
    if not test_health():
        print("✗ 后端服务未运行")
        return
    
    # 2. 创建测试用户
    user = create_test_user()
    
    # 3. 获取token
    token = get_token()
    if not token:
        return
    
    # 4. 测试图片上传
    test_image_upload(token)
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)

if __name__ == "__main__":
    main()
