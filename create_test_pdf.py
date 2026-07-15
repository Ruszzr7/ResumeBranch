#!/usr/bin/env python3
"""
创建一个简单的测试PDF文件用于测试
"""

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os

def create_test_pdf(filename="data/test_resume.pdf"):
    """创建测试简历PDF"""
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # 设置字体
    c.setFont("Helvetica-Bold", 18)
    c.drawString(200, height - 50, "张三 - 简历")
    
    c.setFont("Helvetica", 12)
    
    # 基本信息
    y = height - 100
    c.drawString(50, y, "基本信息:")
    y -= 20
    c.drawString(70, y, "姓名: 张三")
    y -= 15
    c.drawString(70, y, "性别: 男")
    y -= 15
    c.drawString(70, y, "手机: 13800138000")
    y -= 15
    c.drawString(70, y, "邮箱: zhangsan@example.com")
    y -= 15
    c.drawString(70, y, "期望岗位: 产品经理")
    
    # 教育背景
    y -= 40
    c.drawString(50, y, "教育背景:")
    y -= 20
    c.drawString(70, y, "学校: 清华大学")
    y -= 15
    c.drawString(70, y, "专业: 计算机科学")
    y -= 15
    c.drawString(70, y, "学历: 本科")
    y -= 15
    c.drawString(70, y, "时间: 2018.09 - 2022.06")
    
    # 工作经历
    y -= 40
    c.drawString(50, y, "工作经历:")
    y -= 20
    c.drawString(70, y, "公司: 字节跳动")
    y -= 15
    c.drawString(70, y, "职位: 产品经理")
    y -= 15
    c.drawString(70, y, "时间: 2022.07 - 2024.12")
    y -= 15
    c.drawString(70, y, "工作内容:")
    y -= 15
    c.drawString(85, y, "- 负责抖音海外版产品功能设计")
    y -= 15
    c.drawString(85, y, "- 带领团队完成用户增长30%")
    y -= 15
    c.drawString(85, y, "- 优化产品体验，DAU提升50万")
    
    c.save()
    print(f"✓ 创建测试PDF: {filename}")
    return filename

if __name__ == "__main__":
    create_test_pdf()
