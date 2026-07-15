"""
PDF生成器模块
使用WeasyPrint生成矢量PDF，样式与前端简历预览完全一致
"""

import os
import re
from weasyprint import HTML


# 语言字典
LABELS = {
    'zh': {
        'education': '教育经历',
        'workExperience': '工作经历',
        'projectExperience': '项目经历',
        'others': '其他',
        'selfEvaluation': '自我评价',
        'targetPosition': '目标岗位',
        'skills': '技能',
        'certificates': '证书',
        'language': '语言',
        'thesis': '论文',
        'nameNotSet': '姓名未填写',
        'schoolNotSet': '学校未填写',
        'companyNotSet': '公司未填写',
        'projectNotSet': '项目未填写',
    },
    'en': {
        'education': 'Education',
        'workExperience': 'Work Experience',
        'projectExperience': 'Project Experience',
        'others': 'Others',
        'selfEvaluation': 'Self Evaluation',
        'targetPosition': 'Target Position',
        'skills': 'Skills',
        'certificates': 'Certificates',
        'language': 'Language',
        'thesis': 'Thesis',
        'nameNotSet': 'Name Not Set',
        'schoolNotSet': 'School Not Set',
        'companyNotSet': 'Company Not Set',
        'projectNotSet': 'Project Not Set',
    }
}


def format_markdown(text: str) -> str:
    """格式化Markdown语法为HTML"""
    if not text or not isinstance(text, str):
        return text

    # 处理加粗 **text** -> <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # 处理斜体 *text* -> <i>text</i>（但避免处理列表项开头的*）
    text = re.sub(r'(?<!\*)\*(.+?)\*(?!\*)', r'<i>\1</i>', text)
    return text


def render_resume_to_html(resume_data: dict, style: dict = None, photo: str = None, lang: str = 'zh') -> str:
    """将简历数据渲染为HTML

    Args:
        resume_data: 简历数据字典
        style: 样式参数，包括marginTop, marginBottom, marginLeft, marginRight, moduleMargin, lineHeight, fontSize
        photo: 证件照base64编码（可选，如果为None则从resume_data中提取）
        lang: 语言，'zh' 或 'en'
    """
    # 获取语言标签
    labels = LABELS.get(lang, LABELS['zh'])

    # 默认样式
    style = style or {}
    margin_top = style.get('marginTop', 9)  # mm
    margin_bottom = style.get('marginBottom', 9)  # mm
    margin_left = style.get('marginLeft', 9)  # mm
    margin_right = style.get('marginRight', 9)  # mm
    module_margin = style.get('moduleMargin', 1)  # rem单位，与前端一致
    line_height = style.get('lineHeight', 1.6)
    font_size = style.get('fontSize', 11)  # pt单位

    html_parts = []

    # 获取证件照（优先使用参数，其次使用resume_data）
    display_photo = photo
    if not display_photo and resume_data.get("basics"):
        display_photo = resume_data["basics"].get("photo", "")

    # 个人信息
    if resume_data.get("basics"):
        basics = resume_data["basics"]
        html_parts.append('<div class="personal-info">')
        
        # 证件照使用绝对定位（不参与居中计算）
        if display_photo:
            html_parts.append(f'<img src="{display_photo}" class="profile-photo" alt="证件照" />')
        
        # 姓名
        html_parts.append(f'<h1 class="name">{basics.get("name", "姓名未填写")}</h1>')
        
        # 联系信息
        html_parts.append('<div class="contact-info">')
        if basics.get("gender"):
            html_parts.append(f'<span>{basics["gender"]}</span>')
        if basics.get("phone"):
            if basics.get("gender"):
                html_parts.append('<span class="separator">|</span>')
            html_parts.append(f'<span>{basics["phone"]}</span>')
        if basics.get("email"):
            if basics.get("gender") or basics.get("phone"):
                html_parts.append('<span class="separator">|</span>')
            html_parts.append(f'<span>{basics["email"]}</span>')
        html_parts.append('</div>')  # contact-info
        
        # 目标岗位
        if basics.get("target_position"):
            html_parts.append(f'<div class="target-position">{labels["targetPosition"]}：{basics["target_position"]}</div>')
        
        html_parts.append('</div>')  # personal-info

    # 教育经历
    if resume_data.get("education") and len(resume_data["education"]) > 0:
        html_parts.append('<section class="section">')
        html_parts.append(f'<h2 class="section-title">{labels["education"]}</h2>')

        for edu in resume_data["education"]:
            html_parts.append('<div class="education-item">')
            html_parts.append('<div class="education-header">')
            html_parts.append('<div class="school-info">')
            html_parts.append(f'<span class="school">{edu.get("school_name", "学校未填写")}</span>')

            if edu.get("school_tags"):
                html_parts.append('<div class="school-tags">')
                for tag in edu["school_tags"]:
                    html_parts.append(f'<span class="school-tag">{tag}</span>')
                html_parts.append('</div>')

            degree_major = []
            if edu.get("degree"):
                degree_major.append(edu["degree"])
            if edu.get("major"):
                degree_major.append(edu["major"])
            if degree_major:
                html_parts.append(f'<span class="degree-major">{" ".join(degree_major)}</span>')

            html_parts.append('</div>')

            date_range = edu.get("date_range", [])
            date_str = ""
            if len(date_range) > 0:
                date_str = date_range[0]
                if len(date_range) > 1:
                    date_str += f" - {date_range[1]}"
            html_parts.append(f'<div class="graduation-date">{date_str}</div>')
            html_parts.append('</div>')

            # 论文
            if edu.get("theses") and len(edu["theses"]) > 0:
                html_parts.append('<div class="theses">')
                html_parts.append(f'<h4 class="subfield-title">{labels["thesis"]}</h4>')
                for thesis in edu["theses"]:
                    if isinstance(thesis, dict):
                        html_parts.append('<div class="thesis-item">')
                        if thesis.get("title"):
                            html_parts.append(f'<div class="thesis-title">{format_markdown(thesis["title"])}</div>')
                        if thesis.get("details") and isinstance(thesis["details"], list):
                            html_parts.append('<ul class="list-items">')
                            for detail in thesis["details"]:
                                html_parts.append(f'<li class="list-item">{format_markdown(detail)}</li>')
                            html_parts.append('</ul>')
                        html_parts.append('</div>')
                html_parts.append('</div>')

            html_parts.append('</div>')

        html_parts.append('</section>')

    # 工作经历
    if resume_data.get("work_experience") and len(resume_data["work_experience"]) > 0:
        html_parts.append('<section class="section">')
        html_parts.append(f'<h2 class="section-title">{labels["workExperience"]}</h2>')

        for work in resume_data["work_experience"]:
            html_parts.append('<div class="work-item">')
            html_parts.append('<div class="work-header">')
            html_parts.append('<div class="work-main">')
            html_parts.append(f'<div class="company">{work.get("company_name", "公司未填写")}</div>')

            job_info = []
            if work.get("job_title"):
                job_info.append(work["job_title"])
            if work.get("job_type"):
                job_info.append(f"({work['job_type']})")
            if job_info:
                html_parts.append(f'<div class="position-department">{" ".join(job_info)}</div>')

            html_parts.append('</div>')

            date_range = work.get("date_range", [])
            date_str = ""
            if len(date_range) > 0:
                date_str = date_range[0]
                if len(date_range) > 1:
                    date_str += f" - {date_range[1]}"
            html_parts.append(f'<div class="work-period">{date_str}</div>')
            html_parts.append('</div>')

            # 工作详情
            if work.get("details") and isinstance(work["details"], list):
                html_parts.append('<ul class="list-items">')
                for detail in work["details"]:
                    detail_clean = detail.lstrip("• ").strip()
                    html_parts.append(f'<li class="list-item">{format_markdown(detail_clean)}</li>')
                html_parts.append('</ul>')

            html_parts.append('</div>')

        html_parts.append('</section>')

    # 项目经历
    if resume_data.get("project_experience") and len(resume_data["project_experience"]) > 0:
        html_parts.append('<section class="section">')
        html_parts.append(f'<h2 class="section-title">{labels["projectExperience"]}</h2>')

        for project in resume_data["project_experience"]:
            html_parts.append('<div class="project-item">')
            html_parts.append('<div class="project-header">')
            html_parts.append(f'<div class="project-name">{project.get("project_name", project.get("name", "项目未填写"))}</div>')

            role_parts = []
            if project.get("role"):
                role_parts.append(project["role"])
            date_range = project.get("date_range", [])
            if len(date_range) > 0:
                role_parts.append("|")
                role_parts.append(date_range[0])
                if len(date_range) > 1:
                    role_parts.append(f"- {date_range[1]}")
            elif project.get("start_date"):
                role_parts.append("|")
                role_parts.append(project["start_date"])
                if project.get("end_date"):
                    role_parts.append(f"- {project['end_date']}")

            if role_parts:
                html_parts.append(f'<div class="project-role">{" ".join(role_parts)}</div>')

            html_parts.append('</div>')

            # 项目详情
            if project.get("details") and isinstance(project["details"], list):
                html_parts.append('<ul class="list-items">')
                for detail in project["details"]:
                    html_parts.append(f'<li class="list-item">{format_markdown(detail)}</li>')
                html_parts.append('</ul>')

            html_parts.append('</div>')

        html_parts.append('</section>')

    # 其他信息
    if resume_data.get("others"):
        others = resume_data["others"]
        has_others = any([
            others.get("skills"),
            others.get("certificates"),
            others.get("languages")
        ])

        if has_others:
            html_parts.append('<section class="section others">')
            html_parts.append(f'<h2 class="section-title">{labels["others"]}</h2>')

            if others.get("skills") and len(others["skills"]) > 0:
                html_parts.append('<div class="others-item cert-lang-line">')
                html_parts.append(f'<span class="cert-lang-label">{labels["skills"]}：</span>')
                for idx, skill in enumerate(others["skills"]):
                    html_parts.append(f'<span class="inline-list-item">{format_markdown(skill)}</span>')
                    if idx < len(others["skills"]) - 1:
                        html_parts.append('<span class="cert-lang-separator"> | </span>')
                html_parts.append('</div>')

            if others.get("certificates") and len(others["certificates"]) > 0:
                html_parts.append('<div class="others-item cert-lang-line">')
                html_parts.append(f'<span class="cert-lang-label">{labels["certificates"]}：</span>')
                for idx, cert in enumerate(others["certificates"]):
                    html_parts.append(f'<span class="inline-list-item">{format_markdown(cert)}</span>')
                    if idx < len(others["certificates"]) - 1:
                        html_parts.append('<span class="cert-lang-separator"> | </span>')
                html_parts.append('</div>')

            if others.get("languages") and len(others["languages"]) > 0:
                html_parts.append('<div class="others-item cert-lang-line">')
                html_parts.append(f'<span class="cert-lang-label">{labels["language"]}：</span>')
                for idx, lang in enumerate(others["languages"]):
                    html_parts.append(f'<span class="inline-list-item">{format_markdown(lang)}</span>')
                    if idx < len(others["languages"]) - 1:
                        html_parts.append('<span class="cert-lang-separator"> | </span>')
                html_parts.append('</div>')

            html_parts.append('</section>')

    # 自我评价
    if resume_data.get("self_evaluation") and len(resume_data["self_evaluation"]) > 0:
        html_parts.append('<section class="section self-evaluation">')
        html_parts.append(f'<h2 class="section-title">{labels["selfEvaluation"]}</h2>')
        for eval_item in resume_data["self_evaluation"]:
            html_parts.append(f'<div class="self-eval-item">{format_markdown(eval_item)}</div>')
        html_parts.append('</section>')

    # 动态生成CSS
    dynamic_css = f"""
    @page {{
        size: A4;
        margin: {margin_top}mm {margin_right}mm {margin_bottom}mm {margin_left}mm;
    }}

    * {{
        box-sizing: border-box;
    }}

    html {{
        font-size: {font_size}pt;
        --module-margin: {module_margin}rem;
        --line-height: {line_height};
    }}

    body {{
        font-family: 'Hiragino Sans GB', 'Noto Sans SC', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
        font-size: 1em;
        line-height: var(--line-height);
        color: #212529;
        margin: 0;
        padding: 0;
        background-color: white;
        orphans: 3;
        widows: 3;
    }}

    .resume-container {{
        width: 100%;
        max-width: 100%;
        overflow: hidden;
    }}

    .personal-info {{
        text-align: center;
        position: relative;
        min-height: 2.8cm;
    }}

    .personal-info .name {{
        font-size: 1.5em;
        font-weight: 700;
        margin: 0 0 0.25em 0;
        color: #212529;
    }}

    .contact-info {{
        display: flex;
        justify-content: center;
        gap: 0.5em;
        flex-wrap: wrap;
        font-size: 0.8em;
        color: #6c757d;
    }}

    .separator {{
        color: #6c757d;
    }}

    .profile-photo {{
        width: 2.1cm;
        height: 2.6cm;
        object-fit: cover;
        border: 1px solid #ddd;
        border-radius: 2px;
        position: absolute;
        top: 0;
        right: 0;
    }}

    .target-position {{
        font-size: 0.8em;
        color: #212529;
        font-weight: 600;
        margin-top: 0.25em;
    }}

    .section {{
        margin-bottom: var(--module-margin);
    }}

    .section-title {{
        font-size: 1.1em;
        font-weight: 600;
        margin: 0 0 0.5em 0;
        color: #212529;
        padding-bottom: 0.25em;
        border-bottom: 2px solid #333333;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}

    .education-item,
    .work-item,
    .project-item {{
        margin-bottom: 0.5em;
    }}

    .thesis-item {{
        page-break-inside: avoid;
        break-inside: avoid;
        -webkit-column-break-inside: avoid;
    }}

    .education-header,
    .work-header,
    .project-header {{
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 0.5em;
    }}

    .school-info {{
        display: flex;
        align-items: baseline;
        gap: 0.5em;
        flex-wrap: wrap;
    }}

    .school {{
        font-size: 1em;
        font-weight: 600;
        color: #212529;
    }}

    .school-tags {{
        display: inline-flex;
        gap: 0.375em;
        flex-wrap: nowrap;
        white-space: nowrap;
    }}

    .school-tag {{
        display: inline-block;
        padding: 0.125em 0.5em;
        background-color: #333333;
        color: white;
        font-size: 0.75em;
        border-radius: 4px;
        font-weight: 500;
    }}

    .degree-major {{
        font-size: 0.8em;
        font-weight: 500;
        color: #6c757d;
    }}

    .graduation-date,
    .work-period {{
        font-size: 0.8em;
        color: #95a5a6;
        white-space: nowrap;
        font-weight: 500;
    }}

    .theses {{
        margin-top: 0.25em;
    }}

    .thesis-title {{
        font-weight: 600;
        font-size: 0.85em;
    }}

    .subfield-title {{
        font-size: 0.825em;
        font-weight: 600;
        color: #6c757d;
        margin-bottom: 0.25em;
        display: block;
    }}

    .company {{
        font-size: 1em;
        font-weight: 600;
        margin: 0 0 0.125em 0;
        color: #212529;
    }}

    .position-department {{
        font-size: 0.8em;
        font-weight: 500;
        color: #6c757d;
    }}

    .project-name {{
        font-size: 1em;
        font-weight: 600;
        margin: 0 0 0.125em 0;
        color: #212529;
    }}

    .project-role {{
        font-size: 0.8em;
        font-weight: 500;
        color: #6c757d;
    }}

    .list-items {{
        list-style: none;
        padding: 0;
        margin: 0;
    }}

    .list-item {{
        position: relative;
        padding-left: 1.25em;
        margin-bottom: 0.25em;
        font-size: 0.8em;
        line-height: var(--line-height);
        color: #212529;
    }}

    .list-item::before {{
        content: "•";
        position: absolute;
        left: 0;
        color: #333333;
        font-weight: bold;
    }}

    .others {{
        margin-top: 0.5em;
    }}

    .others-item {{
        margin-bottom: 0.5em;
    }}

    .others-title {{
        font-size: 0.9em;
        font-weight: 600;
        margin: 0 0 0.25em 0;
        color: #212529;
    }}

    .skills-list {{
        display: flex;
        flex-direction: row;
        flex-wrap: wrap;
        gap: 0.5em;
    }}

    .skill-item {{
        font-size: 0.8em;
        line-height: var(--line-height);
        color: #212529;
        word-wrap: break-word;
        overflow-wrap: break-word;
        max-width: 100%;
    }}

    .cert-lang-line {{
        font-size: 0.8em;
        line-height: var(--line-height);
        color: #212529;
        word-wrap: break-word;
        overflow-wrap: break-word;
        max-width: 100%;
    }}

    .cert-lang-label {{
        font-weight: 600;
        margin-right: 0.25em;
    }}

    .cert-lang-separator {{
        color: #333333;
        margin: 0 0.25em;
    }}

    .inline-list {{
        display: inline-flex;
        flex-wrap: wrap;
        gap: 0;
    }}

    .inline-list-item {{
        display: inline;
        font-size: 0.8em;
        color: #212529;
    }}

    b {{
        font-weight: 600;
    }}

    .self-evaluation {{
        margin-top: 0.5em;
    }}

    .self-eval-item {{
        font-size: 0.8em;
        line-height: var(--line-height);
        color: #212529;
    }}

    .resume-container {{
        overflow: hidden;
        max-height: 100%;
    }}
    """

    # 组装完整HTML
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>简历</title>
    <style>
        {dynamic_css}
    </style>
</head>
<body>
    <div class="resume-container">
        {"".join(html_parts)}
    </div>
</body>
</html>
"""

    return full_html


def generate_pdf(resume_data: dict, style: dict = None, photo: str = None, lang: str = 'zh') -> bytes:
    """
    根据简历数据生成PDF

    Args:
        resume_data: 简历数据字典
        style: 样式参数（可选）
        photo: 证件照base64编码（可选）
        lang: 语言，'zh' 或 'en'（可选）

    Returns:
        PDF文件的二进制数据
    """
    html_content = render_resume_to_html(resume_data, style, photo, lang)
    pdf = HTML(string=html_content, base_url=os.getcwd()).write_pdf()
    return pdf
