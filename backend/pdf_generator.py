"""
PDF生成器模块
使用WeasyPrint生成矢量PDF，样式与前端简历预览完全一致
"""

import os
import re

from .resume_data import normalize_resume_data
from .resume_labels import LABELS

def format_markdown(text: str) -> str:
    """格式化Markdown语法为HTML"""
    if not text or not isinstance(text, str):
        return text

    # 处理加粗 **text** -> <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # 处理斜体 *text* -> <i>text</i>（但避免处理列表项开头的*）
    text = re.sub(r'(?<!\*)\*(.+?)\*(?!\*)', r'<i>\1</i>', text)
    return text


def render_resume_to_html(resume_data: dict, style: dict = None, photo: str = None, lang: str = 'zh', layout_config: dict = None) -> str:
    """将简历数据渲染为HTML

    Args:
        resume_data: 简历数据字典
        style: 样式参数，包括marginTop, marginBottom, marginLeft, marginRight, moduleMargin, lineHeight, fontSize
        photo: 证件照base64编码（可选，如果为None则从resume_data中提取）
        lang: 语言，'zh' 或 'en'
    """
    resume_data = normalize_resume_data(resume_data)
    from .layout_config import normalize_layout_config
    layout_config = normalize_layout_config(layout_config)
    global_layout = layout_config["global"]

    # 获取语言标签
    labels = LABELS.get(lang, LABELS['zh'])

    # 默认样式
    from .layout import apply_page_mode_defaults
    style = apply_page_mode_defaults(style)
    margin_top = style.get('marginTop', global_layout['marginVertical'])
    margin_bottom = style.get('marginBottom', global_layout['marginVertical'])
    margin_left = style.get('marginLeft', global_layout['marginHorizontal'])
    margin_right = style.get('marginRight', global_layout['marginHorizontal'])
    module_margin = style.get('moduleMargin', global_layout['moduleMargin'])
    line_height = style.get('lineHeight', global_layout['lineHeight'])
    font_size = style.get('fontSize', global_layout['fontSize'])
    page_break_before = style.get('pageBreakBefore', '')

    def break_class(key: str) -> str:
        return ' page-break-before' if page_break_before == key else ''

    def hidden(section: str) -> bool:
        return section in global_layout["hiddenSections"]

    def order_style(section: str) -> str:
        try:
            order = global_layout["sectionOrder"].index(section) + 1
        except ValueError:
            order = 99
        return f' style="order:{order}"'

    def section_title(section: str, fallback: str) -> str:
        return global_layout.get("titleOverrides", {}).get(section, {}).get(lang, fallback)

    html_parts = []

    # 获取证件照（优先使用参数，其次使用resume_data）
    display_photo = photo
    if not display_photo and resume_data.get("basics"):
        display_photo = resume_data["basics"].get("photo", "")

    # 个人信息
    if resume_data.get("basics"):
        basics = resume_data["basics"]
        basics_layout = layout_config["basics"]
        hidden_basics = set(basics_layout["hiddenFields"])
        html_parts.append(f'<div class="personal-info basics-{basics_layout["preset"]} contact-{basics_layout["contactLayout"]}" style="order:0">')
        
        # 证件照使用绝对定位（不参与居中计算）
        if display_photo and "photo" not in hidden_basics:
            html_parts.append(f'<img src="{display_photo}" class="profile-photo" alt="证件照" />')
        
        # 姓名
        html_parts.append(f'<h1 class="name">{basics.get("name", "姓名未填写")}</h1>')
        
        # 联系信息
        html_parts.append('<div class="contact-info">')
        if basics.get("gender") and "gender" not in hidden_basics:
            html_parts.append(f'<span>{basics["gender"]}</span>')
        if basics.get("phone") and "phone" not in hidden_basics:
            if basics.get("gender") and "gender" not in hidden_basics:
                html_parts.append('<span class="separator">|</span>')
            html_parts.append(f'<span>{basics["phone"]}</span>')
        if basics.get("email") and "email" not in hidden_basics:
            if ((basics.get("gender") and "gender" not in hidden_basics) or (basics.get("phone") and "phone" not in hidden_basics)):
                html_parts.append('<span class="separator">|</span>')
            html_parts.append(f'<span>{basics["email"]}</span>')
        html_parts.append('</div>')  # contact-info
        
        # 目标岗位
        if basics.get("target_position") and "target_position" not in hidden_basics:
            html_parts.append(f'<div class="target-position">{labels["targetPosition"]}：{basics["target_position"]}</div>')
        
        html_parts.append('</div>')  # personal-info

    # 教育经历
    if resume_data.get("education") and len(resume_data["education"]) > 0 and not hidden("education"):
        education_layout = layout_config["education"]
        hidden_metrics = set(education_layout["hiddenMetrics"])
        html_parts.append(f'<section class="section education-section preset-{education_layout["preset"]}{break_class("education:0")}"{order_style("education")}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{section_title("education", labels["education"])}</h2>')

        for edu_index, edu in enumerate(resume_data["education"]):
            item_break = break_class(f"education:{edu_index}") if edu_index > 0 else ''
            html_parts.append(f'<div class="education-item preset-{education_layout["preset"]}{item_break}">')
            academic_metrics = []
            if edu.get("gpa") and "gpa" not in hidden_metrics:
                gpa_value = str(edu["gpa"])
                if edu.get("gpa_scale"):
                    gpa_value += f'/{edu["gpa_scale"]}'
                academic_metrics.append(f'{labels["gpa"]}：{gpa_value}')
            if edu.get("ranking") and "ranking" not in hidden_metrics:
                academic_metrics.append(f'{labels["ranking"]}：{edu["ranking"]}')
            if edu.get("average_score") and "average_score" not in hidden_metrics:
                academic_metrics.append(f'{labels["averageScore"]}：{edu["average_score"]}')

            html_parts.append('<div class="education-header">')
            html_parts.append('<div class="school-info">')
            html_parts.append(f'<span class="school">{edu.get("school_name", "学校未填写")}</span>')

            if edu.get("school_tags") and education_layout["schoolTagStyle"] != "hidden":
                html_parts.append('<div class="school-tags">')
                for tag in edu["school_tags"]:
                    html_parts.append(f'<span class="school-tag tag-{education_layout["schoolTagStyle"]}">{tag}</span>')
                html_parts.append('</div>')

            html_parts.append('</div>')
            html_parts.append('<div class="education-info-column">')
            degree_major = []
            if edu.get("degree"):
                degree_major.append(edu["degree"])
            if edu.get("major"):
                degree_major.append(edu["major"])
            if degree_major:
                html_parts.append(f'<div class="degree-major">{" ".join(degree_major)}</div>')
            if academic_metrics:
                html_parts.append('<div class="academic-metrics">')
                for metric in academic_metrics:
                    html_parts.append(f'<span>{format_markdown(metric)}</span>')
                html_parts.append('</div>')
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
            if edu.get("theses") and len(edu["theses"]) > 0 and education_layout["thesisDisplay"] != "hidden":
                html_parts.append('<div class="theses">')
                html_parts.append(f'<h4 class="subfield-title">{labels["thesis"]}</h4>')
                for thesis in edu["theses"]:
                    if isinstance(thesis, dict):
                        html_parts.append('<div class="thesis-item">')
                        if thesis.get("title"):
                            html_parts.append(f'<div class="thesis-title">{format_markdown(thesis["title"])}</div>')
                        if thesis.get("details") and isinstance(thesis["details"], list) and education_layout["thesisDisplay"] == "expanded":
                            html_parts.append('<ul class="list-items">')
                            for detail in thesis["details"]:
                                html_parts.append(f'<li class="list-item">{format_markdown(detail)}</li>')
                            html_parts.append('</ul>')
                        html_parts.append('</div>')
                html_parts.append('</div>')

            html_parts.append('</div>')

        html_parts.append('</section>')

    # 工作/实习经历（拆分时仍共用同一视觉预设）
    work_layout = layout_config["work_experience"]
    work_items = list(enumerate(resume_data.get("work_experience") or []))
    if global_layout["splitWorkExperience"]:
        work_sections = [
            ("work_experience", labels["workExperience"], [(i, item) for i, item in work_items if not re.search(r"实习|intern", str(item.get("job_type", "")), re.I)]),
            ("internship_experience", "Internship Experience" if lang == "en" else "实习经历", [(i, item) for i, item in work_items if re.search(r"实习|intern", str(item.get("job_type", "")), re.I)]),
        ]
    else:
        work_sections = [("work_experience", labels["workExperience"], work_items)]

    for section_id, fallback_title, section_items in work_sections:
        if not section_items or hidden(section_id):
            continue
        first_index = section_items[0][0]
        html_parts.append(f'<section class="section work-section preset-{work_layout["preset"]}{break_class(f"{section_id}:{first_index}")}"{order_style(section_id)}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{section_title(section_id, fallback_title)}</h2>')

        for item_position, (work_index, work) in enumerate(section_items):
            item_break = break_class(f"{section_id}:{work_index}") if item_position > 0 else ''
            work_classes = (
                "work-item page-break-before"
                if item_break else f'work-item preset-{work_layout["preset"]} date-{work_layout["datePosition"]}'
            )
            html_parts.append(f'<div class="{work_classes}">')
            html_parts.append('<div class="work-header">')
            html_parts.append('<div class="work-main">')
            html_parts.append(f'<div class="company">{work.get("company_name", "公司未填写")}</div>')

            job_info = []
            if work.get("job_title"):
                job_info.append(work["job_title"])
            if work.get("job_type") and work_layout["showJobType"]:
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
                html_parts.append(f'<ul class="list-items details-{work_layout["detailsStyle"]}">')
                for detail in work["details"]:
                    detail_clean = detail.lstrip("• ").strip()
                    html_parts.append(f'<li class="list-item">{format_markdown(detail_clean)}</li>')
                html_parts.append('</ul>')

            html_parts.append('</div>')

        html_parts.append('</section>')

    # 项目经历
    if resume_data.get("project_experience") and len(resume_data["project_experience"]) > 0 and not hidden("project_experience"):
        project_layout = layout_config["project_experience"]
        html_parts.append(f'<section class="section project-section preset-{project_layout["preset"]}{break_class("project_experience:0")}"{order_style("project_experience")}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{section_title("project_experience", labels["projectExperience"])}</h2>')

        for project_index, project in enumerate(resume_data["project_experience"]):
            item_break = break_class(f"project_experience:{project_index}") if project_index > 0 else ''
            project_classes = (
                "project-item page-break-before"
                if item_break else f'project-item preset-{project_layout["preset"]} date-{project_layout["datePosition"]}'
            )
            html_parts.append(f'<div class="{project_classes}">')
            html_parts.append('<div class="project-header">')
            html_parts.append(f'<div class="project-name">{project.get("project_name", project.get("name", "项目未填写"))}</div>')

            role_parts = []
            if project.get("role") and project_layout["showRole"]:
                role_parts.append(project["role"])
            date_range = project.get("date_range", [])
            if len(date_range) > 0 and project_layout["showDate"]:
                if role_parts:
                    role_parts.append("|")
                role_parts.append(date_range[0])
                if len(date_range) > 1:
                    role_parts.append(f"- {date_range[1]}")
            elif project.get("start_date") and project_layout["showDate"]:
                if role_parts:
                    role_parts.append("|")
                role_parts.append(project["start_date"])
                if project.get("end_date"):
                    role_parts.append(f"- {project['end_date']}")

            if role_parts:
                html_parts.append(f'<div class="project-role">{" ".join(role_parts)}</div>')

            html_parts.append('</div>')

            # 项目详情
            if project.get("details") and isinstance(project["details"], list):
                html_parts.append(f'<ul class="list-items details-{project_layout["detailsStyle"]}">')
                for detail in project["details"]:
                    html_parts.append(f'<li class="list-item">{format_markdown(detail)}</li>')
                html_parts.append('</ul>')

            html_parts.append('</div>')

        html_parts.append('</section>')

    # 其他信息
    others = resume_data.get("others") or {}
    others_layout = layout_config["others"]
    visible_other_fields = [
        field for field in others_layout["fieldOrder"]
        if field not in others_layout["hiddenFields"] and others.get(field)
    ]
    if visible_other_fields and not hidden("others"):
        html_parts.append(f'<section class="section others others-{others_layout["preset"]}{break_class("others")}"{order_style("others")}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{section_title("others", labels["others"])}</h2>')
        field_labels = {"skills": labels["skills"], "certificates": labels["certificates"], "languages": labels["language"]}
        separator = " · " if others_layout["separator"] == "dot" else " | "
        for field in visible_other_fields:
            html_parts.append('<div class="others-item cert-lang-line">')
            html_parts.append(f'<span class="cert-lang-label">{field_labels[field]}：</span>')
            for idx, value in enumerate(others[field]):
                html_parts.append(f'<span class="inline-list-item">{format_markdown(value)}</span>')
                if others_layout["preset"] != "tags" and idx < len(others[field]) - 1:
                    html_parts.append(f'<span class="cert-lang-separator">{separator}</span>')
            html_parts.append('</div>')
        html_parts.append('</section>')

    # 自我评价
    if resume_data.get("self_evaluation") and len(resume_data["self_evaluation"]) > 0 and not hidden("self_evaluation"):
        self_layout = layout_config["self_evaluation"]
        html_parts.append(f'<section class="section self-evaluation self-{self_layout["preset"]}{break_class("self_evaluation")}"{order_style("self_evaluation")}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{section_title("self_evaluation", labels["selfEvaluation"])}</h2>')
        evaluations = resume_data["self_evaluation"]
        if self_layout["preset"] == "compact":
            evaluations = [" ".join(str(item) for item in evaluations)]
        for eval_item in evaluations:
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
        display: flex;
        flex-direction: column;
    }}

    .personal-info {{
        text-align: center;
        position: relative;
        min-height: 2.8cm;
    }}

    .personal-info.basics-left-aligned {{ text-align: left; }}
    .personal-info.basics-left-aligned .contact-info {{ justify-content: flex-start; }}
    .personal-info.contact-stacked .contact-info {{
        flex-direction: column;
        align-items: center;
        gap: 0.1em;
    }}
    .personal-info.basics-left-aligned.contact-stacked .contact-info {{ align-items: flex-start; }}
    .personal-info.contact-stacked .separator {{ display: none; }}

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

    .section-title.title-plain {{
        border-bottom: 0;
        padding-bottom: 0;
        text-transform: none;
        letter-spacing: 0;
    }}

    .education-item,
    .work-item,
    .project-item {{
        margin-bottom: 0.5em;
        page-break-inside: avoid;
        break-inside: avoid;
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

    .school-tag.tag-outline {{
        background: transparent;
        color: #333333;
        border: 1px solid #333333;
    }}

    .school-tag.tag-text {{
        background: transparent;
        color: #333333;
        padding-left: 0;
        padding-right: 0;
        border-radius: 0;
    }}

    .education-item .education-header {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 0.15em 0.8em;
        align-items: start;
    }}
    .education-item .school-info {{ grid-column: 1; grid-row: 1; }}
    .education-item .education-info-column {{ grid-column: 1; grid-row: 2; }}
    .education-item .graduation-date {{ grid-column: 2; grid-row: 1; }}
    .education-item.preset-compact .education-header {{
        grid-template-columns: auto minmax(0, 1fr) auto;
        gap: 0.25em;
    }}
    .education-item.preset-compact .school-info {{ grid-column: 1; grid-row: 1; gap: 0.3em; }}
    .education-item.preset-compact .education-info-column {{ grid-column: 2; grid-row: 1; }}
    .education-item.preset-compact .graduation-date {{ grid-column: 3; grid-row: 1; }}
    .education-item.preset-three-column .education-header {{
        grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr) auto;
        align-items: start;
    }}
    .education-item.preset-three-column .education-info-column {{ grid-column: 2; grid-row: 1; }}
    .education-item.preset-three-column .graduation-date {{ grid-column: 3; }}
    .education-info-column .academic-metrics {{ margin-top: 0.15em; }}

    .degree-major {{
        font-size: 0.8em;
        font-weight: 500;
        color: #6c757d;
    }}

    .page-break-before {{
        break-before: page;
        page-break-before: always;
    }}

    .academic-metrics {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.25em 1em;
        margin-top: 0.125em;
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

    .details-paragraph .list-item {{ padding-left: 0; }}
    .details-paragraph .list-item::before {{ content: none; }}
    .work-item.preset-compact .work-header,
    .project-item.preset-compact .project-header {{ gap: 0.25em; }}
    .work-item.preset-compact,
    .project-item.preset-compact {{ margin-bottom: 0.3em; }}
    .work-item.date-inline .work-header,
    .project-item.date-inline .project-header {{ justify-content: flex-start; }}
    .work-item.date-inline .work-period,
    .project-item.date-inline .project-role {{ margin-left: 0.55em; }}

    .others {{
        margin-top: 0.5em;
    }}

    .others-item {{
        margin-bottom: 0.5em;
    }}

    .others-tags .inline-list-item {{
        display: inline-block;
        padding: 0.1em 0.45em;
        margin: 0 0.25em 0.2em 0;
        border: 1px solid #adb5bd;
        border-radius: 3px;
    }}
    .others-tags .cert-lang-separator {{ display: none; }}
    .others-stacked .others-item {{
        display: flex;
        flex-direction: column;
        gap: 0.1em;
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

    .self-bullets .self-eval-item {{
        position: relative;
        padding-left: 1.25em;
    }}
    .self-bullets .self-eval-item::before {{
        content: "•";
        position: absolute;
        left: 0;
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


def generate_pdf(resume_data: dict, style: dict = None, photo: str = None, lang: str = 'zh', layout_config: dict = None) -> bytes:
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
    from weasyprint import HTML
    from .layout import enforce_page_limit, normalize_page_mode

    html_content = render_resume_to_html(resume_data, style, photo, lang, layout_config)
    document = HTML(string=html_content, base_url=os.getcwd()).render()
    enforce_page_limit(normalize_page_mode((style or {}).get("pageMode")), len(document.pages))
    return document.write_pdf()
