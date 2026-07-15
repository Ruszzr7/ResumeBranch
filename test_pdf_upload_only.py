#!/usr/bin/env python3
"""
测试PDF上传功能
"""

import requests
import base64
import json

API_BASE = "http://localhost:8000"

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

def test_pdf_upload(token):
    """测试PDF上传"""
    print("\n=== 测试PDF上传 ===")
    
    # 读取PDF文件
    pdf_path = "data/test_resume.pdf"
    with open(pdf_path, "rb") as f:
        pdf_content = f.read()
        base64_pdf = base64.b64encode(pdf_content).decode("utf-8")
    
    # 发送请求
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "image": f"data:application/pdf;base64,{base64_pdf}"
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
        print("✓ PDF上传测试通过")
        return True
    else:
        print("✗ PDF上传测试失败")
        return False

def main():
    print("=" * 50)
    print("PDF上传功能测试")
    print("=" * 50)
    
    # 获取token
    token = get_token()
    if not token:
        return
    
    # 测试PDF上传
    test_pdf_upload(token)
    
    print("\n" + "=" * 50)
    print("PDF测试完成")
    print("=" * 50)

if __name__ == "__main__":
    main()
