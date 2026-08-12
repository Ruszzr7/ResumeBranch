"""
PDF生成器模块
使用WeasyPrint生成矢量PDF，样式与前端简历预览完全一致
"""

import os
import re
from io import BytesIO
from html import escape

from .inline_formatting import format_inline_html
from .pdf_renderer import render_html_with_chromium
from .resume_data import normalize_resume_data
from .resume_labels import LABELS

def format_markdown(text: str) -> str:
    """Render the allowlisted inline-bold protocol as safe HTML."""
    return format_inline_html(text)


_NATIVE_LIST_MARKER_RE = re.compile(r"^\s*(?:[（(]?\d{1,2}[）).、．]|[一二三四五六七八九十]+[、.．])\s*")


def _has_native_list_marker(value: object) -> bool:
    return bool(_NATIVE_LIST_MARKER_RE.match(str(value or "")))


def render_resume_to_html(resume_data: dict, style: dict = None, photo: str = None, lang: str = 'zh', layout_config: dict = None) -> str:
    """将简历数据渲染为HTML

    Args:
        resume_data: 简历数据字典
        style: 样式参数，包括marginTop, marginBottom, marginLeft, marginRight, moduleMargin, lineHeight, fontSize
        photo: 证件照base64编码（可选，如果为None则从resume_data中提取）
        lang: 语言，'zh' 或 'en'
    """
    resume_data = normalize_resume_data(resume_data)
    from .layout_config import normalize_layout_config, resolve_content_block_flow, resolve_layout_tokens
    layout_config = normalize_layout_config(layout_config)
    global_layout = layout_config["global"]

    # 获取语言标签
    labels = LABELS.get(lang, LABELS['zh'])

    # 默认样式
    from .layout import apply_page_mode_defaults
    style = apply_page_mode_defaults(style)
    tokens = resolve_layout_tokens(layout_config, style)
    margin_top = tokens['marginTopMm']
    margin_bottom = tokens['marginBottomMm']
    margin_left = tokens['marginLeftMm']
    margin_right = tokens['marginRightMm']
    line_height = tokens['lineHeight']
    font_size = tokens['fontSizePt']
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
    section_chunks = []

    def commit_section(section_id: str, start: int) -> None:
        chunk = "".join(html_parts[start:])
        del html_parts[start:]
        if chunk:
            section_chunks.append((section_id, len(section_chunks), chunk))

    # 获取证件照（优先使用参数，其次使用resume_data）
    display_photo = photo
    if not display_photo and resume_data.get("basics"):
        display_photo = resume_data["basics"].get("photo", "")

    # 个人信息
    if resume_data.get("basics"):
        chunk_start = len(html_parts)
        basics = resume_data["basics"]
        basics_layout = layout_config["basics"]
        hidden_basics = set(basics_layout["hiddenFields"])
        photo_class = " has-photo" if display_photo and "photo" not in hidden_basics else ""
        html_parts.append(f'<div class="personal-info basics-{basics_layout["preset"]} contact-{basics_layout["contactLayout"]}{photo_class}" style="order:0">')
        
        # 证件照使用绝对定位（不参与居中计算）
        if display_photo and "photo" not in hidden_basics:
            html_parts.append(f'<img src="{escape(display_photo, quote=True)}" class="profile-photo" alt="证件照" />')
        
        # 姓名
        html_parts.append(f'<h1 class="name">{format_markdown(basics.get("name", "姓名未填写"))}</h1>')
        
        # 联系信息
        html_parts.append('<div class="contact-info">')
        contact_values = []
        if basics.get("gender") and "gender" not in hidden_basics:
            contact_values.append(str(basics["gender"]))
        if basics.get("birth_date") and "birth_date" not in hidden_basics:
            contact_values.append(f'{labels["birthDate"]}：{basics["birth_date"]}')
        if basics.get("phone") and "phone" not in hidden_basics:
            contact_values.append(str(basics["phone"]))
        if basics.get("email") and "email" not in hidden_basics:
            contact_values.append(str(basics["email"]))
        if "additional_fields" not in hidden_basics:
            contact_values.extend(
                f'{item.get("label", "")}：{item.get("value", "")}'
                for item in basics.get("additional_fields", [])
                if item.get("label") and item.get("value")
            )
        for index, value in enumerate(contact_values):
            if index:
                html_parts.append('<span class="separator">|</span>')
            html_parts.append(f'<span>{format_markdown(value)}</span>')
        html_parts.append('</div>')  # contact-info
        
        # 目标岗位
        if basics.get("target_position") and "target_position" not in hidden_basics:
            html_parts.append(f'<div class="target-position"><span class="inline-label">{labels["targetPosition"]}：</span>{format_markdown(basics["target_position"])}</div>')
        
        html_parts.append('</div>')  # personal-info
        commit_section("basics", chunk_start)

    # 教育经历
    if resume_data.get("education") and len(resume_data["education"]) > 0 and not hidden("education"):
        chunk_start = len(html_parts)
        education_layout = layout_config["education"]
        hidden_metrics = set(education_layout["hiddenMetrics"])
        html_parts.append(f'<section class="section education-section preset-{education_layout["preset"]}{break_class("education:0")}"{order_style("education")}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{format_markdown(section_title("education", labels["education"]))}</h2>')

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
            html_parts.append(f'<span class="school">{format_markdown(edu.get("school_name", "学校未填写"))}</span>')

            if edu.get("school_tags") and education_layout["schoolTagStyle"] != "hidden":
                html_parts.append('<div class="school-tags">')
                for tag in edu["school_tags"]:
                    html_parts.append(f'<span class="school-tag tag-{education_layout["schoolTagStyle"]}">{format_markdown(tag)}</span>')
                html_parts.append('</div>')

            html_parts.append('</div>')
            html_parts.append('<div class="education-degree-column">')
            degree_major = []
            if edu.get("degree"):
                degree_major.append(edu["degree"])
            if edu.get("major"):
                degree_major.append(edu["major"])
            if degree_major:
                html_parts.append(f'<div class="degree-major">{format_markdown(" · ".join(degree_major))}</div>')
            html_parts.append('</div>')
            if academic_metrics:
                html_parts.append('<div class="education-metrics-column academic-metrics">')
                for metric in academic_metrics:
                    html_parts.append(f'<span>{format_markdown(metric)}</span>')
                html_parts.append('</div>')

            date_range = edu.get("date_range", [])
            date_str = ""
            if len(date_range) > 0:
                date_str = date_range[0]
                if len(date_range) > 1:
                    date_str += f" - {date_range[1]}"
            html_parts.append(f'<div class="graduation-date">{format_markdown(date_str)}</div>')
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
        commit_section("education", chunk_start)

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
        chunk_start = len(html_parts)
        first_index = section_items[0][0]
        html_parts.append(f'<section class="section work-section preset-{work_layout["preset"]}{break_class(f"{section_id}:{first_index}")}"{order_style(section_id)}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{format_markdown(section_title(section_id, fallback_title))}</h2>')

        for item_position, (work_index, work) in enumerate(section_items):
            item_break = break_class(f"{section_id}:{work_index}") if item_position > 0 else ''
            work_classes = (
                "work-item page-break-before"
                if item_break else f'work-item preset-{work_layout["preset"]} date-{work_layout["datePosition"]}'
            )
            html_parts.append(f'<div class="{work_classes}">')
            html_parts.append('<div class="work-header">')
            html_parts.append('<div class="work-main">')
            html_parts.append(f'<div class="company">{format_markdown(work.get("company_name", "公司未填写"))}</div>')

            job_info = []
            if work.get("job_title"):
                job_info.append(work["job_title"])
            if work.get("job_type") and work_layout["showJobType"]:
                job_info.append(f"({work['job_type']})")
            if job_info:
                html_parts.append(f'<div class="position-department">{format_markdown(" ".join(job_info))}</div>')

            html_parts.append('</div>')

            date_range = work.get("date_range", [])
            date_str = ""
            if len(date_range) > 0:
                date_str = date_range[0]
                if len(date_range) > 1:
                    date_str += f" - {date_range[1]}"
            html_parts.append(f'<div class="work-period">{format_markdown(date_str)}</div>')
            html_parts.append('</div>')

            # 工作详情沿用与项目经历一致的语义块，避免标题和已编号内容被重复加圆点。
            for block in work.get("content_blocks") or []:
                flow = resolve_content_block_flow(block)
                block_type = flow["type"]
                label = flow["label"]
                label_class = " is-bold" if flow["labelBold"] else ""
                label_html = f'<span class="project-inline-label{label_class}">{format_markdown(label)}：</span>' if label else ''
                html_parts.append(f'<div class="project-content-block block-{block_type}">')
                if block_type == "paragraph":
                    html_parts.append(f'<p class="project-paragraph">{label_html}{format_markdown(block.get("text", ""))}</p>')
                else:
                    if flow["labelPlacement"] == "separate":
                        html_parts.append(f'<div class="project-block-label{label_class}">{format_markdown(label)}：</div>')
                    list_class = "project-numbered-list" if block_type == "numbered_list" else "list-items"
                    tag = "ol" if block_type == "numbered_list" else "ul"
                    html_parts.append(f'<{tag} class="{list_class}">')
                    for detail in block.get("items") or []:
                        item_class = "" if block_type == "numbered_list" else ' class="list-item"'
                        html_parts.append(f'<li{item_class}>{format_markdown(detail)}</li>')
                    html_parts.append(f'</{tag}>')
                html_parts.append('</div>')

            html_parts.append('</div>')

        html_parts.append('</section>')
        commit_section(section_id, chunk_start)

    # 项目经历
    if resume_data.get("project_experience") and len(resume_data["project_experience"]) > 0 and not hidden("project_experience"):
        chunk_start = len(html_parts)
        project_layout = layout_config["project_experience"]
        html_parts.append(f'<section class="section project-section preset-{project_layout["preset"]}{break_class("project_experience:0")}"{order_style("project_experience")}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{format_markdown(section_title("project_experience", labels["projectExperience"]))}</h2>')

        for project_index, project in enumerate(resume_data["project_experience"]):
            item_break = break_class(f"project_experience:{project_index}") if project_index > 0 else ''
            project_classes = (
                "project-item page-break-before"
                if item_break else f'project-item preset-{project_layout["preset"]} date-{project_layout["datePosition"]}'
            )
            html_parts.append(f'<div class="{project_classes}">')
            html_parts.append('<div class="project-header">')
            html_parts.append(f'<div class="project-name">{format_markdown(project.get("project_name", project.get("name", "项目未填写")))}</div>')

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
                html_parts.append(f'<div class="project-role">{format_markdown(" ".join(role_parts))}</div>')

            html_parts.append('</div>')

            # 项目详情使用语义块：标题不带圆点，职责内部保留编号。
            for block in project.get("content_blocks") or []:
                flow = resolve_content_block_flow(block)
                block_type = flow["type"]
                label = flow["label"]
                label_class = " is-bold" if flow["labelBold"] else ""
                label_html = f'<span class="project-inline-label{label_class}">{format_markdown(label)}：</span>' if label else ''
                html_parts.append(f'<div class="project-content-block block-{block_type}">')
                if block_type == "paragraph":
                    html_parts.append(f'<p class="project-paragraph">{label_html}{format_markdown(block.get("text", ""))}</p>')
                else:
                    if flow["labelPlacement"] == "separate":
                        html_parts.append(f'<div class="project-block-label{label_class}">{format_markdown(label)}：</div>')
                    list_class = "project-numbered-list" if block_type == "numbered_list" else "list-items"
                    tag = "ol" if block_type == "numbered_list" else "ul"
                    html_parts.append(f'<{tag} class="{list_class}">')
                    for detail in block.get("items") or []:
                        item_class = "" if block_type == "numbered_list" else ' class="list-item"'
                        html_parts.append(f'<li{item_class}>{format_markdown(detail)}</li>')
                    html_parts.append(f'</{tag}>')
                html_parts.append('</div>')

            html_parts.append('</div>')

        html_parts.append('</section>')
        commit_section("project_experience", chunk_start)

    custom_sections = resume_data.get("custom_sections") or []
    if custom_sections and not hidden("custom_sections"):
        chunk_start = len(html_parts)
        for custom_index, custom in enumerate(custom_sections):
            if not custom.get("title") or not custom.get("items"):
                continue
            html_parts.append(f'<section class="section custom-section{break_class(f"custom_sections:{custom_index}")}"{order_style("custom_sections")}>')
            html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{format_markdown(custom["title"])}</h2>')
            html_parts.append('<ul class="list-items">')
            for value in custom["items"]:
                html_parts.append(f'<li class="list-item">{format_markdown(value)}</li>')
            html_parts.append('</ul></section>')
        commit_section("custom_sections", chunk_start)

    # 其他信息
    others = resume_data.get("others") or {}
    others_layout = layout_config["others"]
    visible_other_fields = [
        field for field in others_layout["fieldOrder"]
        if field != "skills" and field not in others_layout["hiddenFields"] and others.get(field)
    ]
    if visible_other_fields and not hidden("others"):
        chunk_start = len(html_parts)
        html_parts.append(f'<section class="section others others-{others_layout["preset"]}{break_class("others")}"{order_style("others")}>')
        other_title = "Certificates & Languages" if lang == "en" else "证书与语言"
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{format_markdown(section_title("others", other_title))}</h2>')
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
        commit_section("others", chunk_start)

    def render_plain_list_section(section_id: str, title: str, values: list[str]) -> None:
        if not values or hidden(section_id):
            return
        chunk_start = len(html_parts)
        html_parts.append(f'<section class="section generic-section{break_class(section_id)}"{order_style(section_id)}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{format_markdown(section_title(section_id, title))}</h2>')
        html_parts.append('<ul class="list-items">')
        for value in values:
            marker_class = " native-marker" if _has_native_list_marker(value) else ""
            html_parts.append(f'<li class="list-item{marker_class}">{format_markdown(value)}</li>')
        html_parts.append('</ul></section>')
        commit_section(section_id, chunk_start)

    render_plain_list_section("skills", labels["skills"], others.get("skills") or [])
    render_plain_list_section("research_interests", labels["researchInterests"], resume_data.get("research_interests") or [])
    render_plain_list_section("honors", labels["honors"], resume_data.get("honors") or [])

    # 自我评价
    if resume_data.get("self_evaluation") and len(resume_data["self_evaluation"]) > 0 and not hidden("self_evaluation"):
        chunk_start = len(html_parts)
        self_layout = layout_config["self_evaluation"]
        html_parts.append(f'<section class="section self-evaluation self-{self_layout["preset"]}{break_class("self_evaluation")}"{order_style("self_evaluation")}>')
        html_parts.append(f'<h2 class="section-title title-{global_layout["titleStyle"]}">{format_markdown(section_title("self_evaluation", labels["selfEvaluation"]))}</h2>')
        evaluations = resume_data["self_evaluation"]
        if self_layout["preset"] == "compact":
            evaluations = [" ".join(str(item) for item in evaluations)]
        for eval_item in evaluations:
            html_parts.append(f'<div class="self-eval-item">{format_markdown(eval_item)}</div>')
        html_parts.append('</section>')
        commit_section("self_evaluation", chunk_start)

    def chunk_order(item) -> tuple[int, int]:
        section_id, sequence, _ = item
        if section_id == "basics":
            return (-1, sequence)
        try:
            return (global_layout["sectionOrder"].index(section_id), sequence)
        except ValueError:
            return (999, sequence)

    rendered_content = "".join(item[2] for item in sorted(section_chunks, key=chunk_order))

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
        --body-font-size: {tokens['bodyFontSizePt']:g}pt;
        --meta-font-size: {tokens['metaFontSizePt']:g}pt;
        --entry-title-font-size: {tokens['entryTitleFontSizePt']:g}pt;
        --section-title-font-size: {tokens['sectionTitleFontSizePt']:g}pt;
        --name-font-size: {tokens['nameFontSizePt']:g}pt;
        --label-font-size: {tokens['labelFontSizePt']:g}pt;
        --body-font-weight: {tokens['bodyFontWeight']};
        --meta-font-weight: {tokens['metaFontWeight']};
        --entry-title-font-weight: {tokens['entryTitleFontWeight']};
        --section-title-font-weight: {tokens['sectionTitleFontWeight']};
        --name-font-weight: {tokens['nameFontWeight']};
        --label-font-weight: {tokens['labelFontWeight']};
        --letter-spacing: {tokens['letterSpacingPt']:g}pt;
        --module-margin: {tokens['moduleSpacingPt']:g}pt;
        --header-name-after: {tokens['headerNameAfterPt']:g}pt;
        --section-title-after: {tokens['sectionTitleAfterPt']:g}pt;
        --item-spacing: {tokens['itemSpacingPt']:g}pt;
        --paragraph-spacing: {tokens['paragraphSpacingPt']:g}pt;
        --content-block-spacing: {tokens['contentBlockSpacingPt']:g}pt;
        --content-label-spacing: {tokens['contentLabelSpacingPt']:g}pt;
        --numbered-item-spacing: {tokens['numberedItemSpacingPt']:g}pt;
        --list-text-indent: {tokens['listTextIndentPt']:g}pt;
        --list-marker-gap: {tokens['listMarkerGapPt']:g}pt;
        --line-height: {line_height};
    }}

    body {{
        font-family: {tokens['fontFamilyCss']};
        font-size: 1em;
        font-weight: var(--body-font-weight);
        letter-spacing: var(--letter-spacing);
        font-kerning: none;
        font-variant-ligatures: none;
        font-synthesis: none;
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
        overflow: visible;
        display: block;
    }}

    .personal-info {{
        text-align: center;
        position: relative;
        min-height: 0;
        margin-bottom: 0.35em;
    }}

    .personal-info.basics-left-aligned {{ text-align: left; }}
    .personal-info.has-photo {{ min-height: 2.65cm; }}
    .personal-info.basics-left-aligned .contact-info {{ justify-content: flex-start; }}
    .personal-info.contact-stacked .contact-info {{
        flex-direction: column;
        align-items: center;
        gap: 0.1em;
    }}
    .personal-info.basics-left-aligned.contact-stacked .contact-info {{ align-items: flex-start; }}
    .personal-info.contact-stacked .separator {{ display: none; }}

    .personal-info .name {{
        font-size: var(--name-font-size);
        font-weight: var(--name-font-weight);
        margin: 0 0 var(--header-name-after) 0;
        color: #212529;
    }}

    .contact-info {{
        display: flex;
        justify-content: center;
        gap: 0.5em;
        flex-wrap: wrap;
        font-size: var(--meta-font-size);
        font-weight: var(--meta-font-weight);
        color: #333333;
    }}

    .separator {{
        color: #333333;
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
        font-size: var(--meta-font-size);
        color: #212529;
        font-weight: var(--label-font-weight);
        margin-top: 0.25em;
    }}
    .inline-label {{ font-size: var(--label-font-size); }}

    .section {{
        margin-bottom: var(--module-margin);
    }}

    .section-title {{
        font-size: var(--section-title-font-size);
        font-weight: var(--section-title-font-weight);
        margin: 0 0 0.5em 0;
        color: #212529;
        padding-bottom: 0.25em;
        border-bottom: 1px solid #333333;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}

    .section-title.title-plain {{
        border-bottom: 1px solid #333333;
        padding-bottom: 0.2em;
        text-transform: none;
        letter-spacing: 0;
    }}

    .education-item {{
        margin-bottom: 0.5em;
        page-break-inside: avoid;
        break-inside: avoid;
    }}

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
        break-after: avoid;
        page-break-after: avoid;
    }}

    .work-main {{
        min-width: 0;
        display: flex;
        align-items: baseline;
        gap: 0.32em;
    }}

    .work-main .company,
    .project-header .project-name {{ min-width: 0; }}
    .work-main .position-department {{ flex: 0 1 auto; }}
    .work-main .position-department::before {{ content: "· "; }}

    .work-item.date-right .work-header,
    .project-item.date-right .project-header {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: baseline;
        column-gap: 0.65em;
    }}

    .work-item.date-right .work-period,
    .project-item.date-right .project-role {{
        margin-left: 0;
        text-align: right;
        white-space: nowrap;
    }}

    .school-info {{
        display: flex;
        align-items: baseline;
        gap: 0.5em;
        flex-wrap: wrap;
    }}

    .school {{
        font-size: var(--entry-title-font-size);
        font-weight: var(--entry-title-font-weight);
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
        font-size: var(--label-font-size);
        border-radius: 4px;
        font-weight: var(--meta-font-weight);
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
    .education-item .education-degree-column {{ grid-column: 1; grid-row: 2; }}
    .education-item .education-metrics-column {{ grid-column: 1; grid-row: 3; }}
    .education-item .graduation-date {{ grid-column: 2; grid-row: 1; }}
    .education-item .school-info,
    .education-item .education-degree-column,
    .education-item .education-metrics-column {{
        min-width: 0;
        overflow-wrap: break-word;
        word-break: break-word;
    }}
    .education-item.preset-compact .education-header {{
        display: flex;
        width: 100%;
        flex-wrap: nowrap;
        column-gap: 0.65em;
        align-items: baseline;
    }}
    .education-item.preset-compact .school-info {{ grid-column: 1; grid-row: 1; gap: 0.3em; }}
    .education-item.preset-compact .school-info,
    .education-item.preset-compact .education-degree-column,
    .education-item.preset-compact .education-metrics-column {{ flex: 1 1 0; min-width: 0; }}
    .education-item.preset-compact .graduation-date {{ grid-column: 4; grid-row: 1; }}
    .education-item.preset-three-column .education-header {{
        display: flex;
        width: 100%;
        flex-wrap: nowrap;
        column-gap: 1.1em;
        align-items: baseline;
    }}
    .education-item.preset-three-column .school-info,
    .education-item.preset-three-column .education-degree-column,
    .education-item.preset-three-column .education-metrics-column {{ flex: 1 1 0; min-width: 0; }}
    .education-item.preset-three-column .graduation-date {{ grid-column: 4; grid-row: 1; }}
    .education-item.preset-compact .graduation-date,
    .education-item.preset-three-column .graduation-date {{
        position: static;
        flex: 0 0 36mm;
        width: 36mm;
        min-width: 0;
        margin-right: 0;
        text-align: right;
    }}
    .education-item.preset-compact .academic-metrics,
    .education-item.preset-three-column .academic-metrics {{ margin-top: 0; }}

    .degree-major {{
        font-size: var(--meta-font-size);
        font-weight: var(--meta-font-weight);
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
        font-size: var(--meta-font-size);
        font-weight: var(--meta-font-weight);
        color: #6c757d;
    }}

    .graduation-date,
    .work-period {{
        font-size: var(--meta-font-size);
        color: #95a5a6;
        white-space: nowrap;
        font-weight: var(--meta-font-weight);
        flex: 0 0 auto;
        max-width: none;
    }}

    .theses {{
        margin-top: 0.25em;
    }}

    .thesis-title {{
        font-weight: var(--label-font-weight);
        font-size: var(--body-font-size);
    }}

    .subfield-title {{
        font-size: var(--label-font-size);
        font-weight: var(--label-font-weight);
        color: #6c757d;
        margin-bottom: 0.25em;
        display: block;
    }}

    .company {{
        font-size: var(--entry-title-font-size);
        font-weight: var(--entry-title-font-weight);
        margin: 0 0 0.125em 0;
        color: #212529;
    }}

    .position-department {{
        font-size: var(--meta-font-size);
        font-weight: var(--meta-font-weight);
        color: #6c757d;
    }}

    .project-name {{
        font-size: var(--entry-title-font-size);
        font-weight: var(--entry-title-font-weight);
        margin: 0 0 0.125em 0;
        color: #212529;
    }}

    .project-role {{
        font-size: var(--meta-font-size);
        font-weight: var(--meta-font-weight);
        color: #6c757d;
    }}

    .list-items {{
        list-style: none;
        padding: 0;
        margin: 0;
    }}

    .list-item {{
        position: relative;
        padding-left: var(--list-text-indent);
        margin-bottom: 0.25em;
        font-size: var(--body-font-size);
        line-height: var(--line-height);
        color: #212529;
    }}

    .list-item::before {{
        content: "•";
        position: absolute;
        left: 0;
        width: calc(var(--list-text-indent) - var(--list-marker-gap));
        text-align: center;
        color: #333333;
        font-weight: bold;
    }}

    .list-item.native-marker {{ padding-left: 0; }}
    .list-item.native-marker::before {{ content: none; }}

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
        font-size: var(--body-font-size);
        font-weight: var(--label-font-weight);
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
        font-size: var(--body-font-size);
        line-height: var(--line-height);
        color: #212529;
        word-wrap: break-word;
        overflow-wrap: break-word;
        max-width: 100%;
    }}

    .cert-lang-line {{
        font-size: var(--body-font-size);
        line-height: var(--line-height);
        color: #212529;
        word-wrap: break-word;
        overflow-wrap: break-word;
        max-width: 100%;
    }}

    .project-block-label,
    .project-inline-label,
    .cert-lang-label {{
        font-size: var(--label-font-size);
    }}

    .project-block-label,
    .project-inline-label {{ font-weight: 400; }}
    .project-block-label.is-bold,
    .project-inline-label.is-bold {{ font-weight: var(--label-font-weight); }}

    .cert-lang-label {{
        font-weight: var(--label-font-weight);
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
        font-size: var(--body-font-size);
        color: #212529;
    }}

    b, strong {{
        font-weight: var(--label-font-weight);
    }}

    .self-evaluation {{
        margin-top: 0.5em;
    }}

    .self-eval-item {{
        font-size: var(--body-font-size);
        line-height: var(--line-height);
        color: #212529;
    }}

    .self-bullets .self-eval-item {{
        position: relative;
        padding-left: var(--list-text-indent);
    }}
    .self-bullets .self-eval-item::before {{
        content: "•";
        position: absolute;
        left: 0;
        width: calc(var(--list-text-indent) - var(--list-marker-gap));
        text-align: center;
    }}

    /* 中文简历使用高对比度、紧凑的信息密度。显式指定颜色，避免主题继承。 */
    body, .degree-major, .academic-metrics, .graduation-date, .work-period,
    .position-department, .project-role, .list-item, .generic-list-item,
    .cert-lang-line, .inline-list-item, .self-eval-item {{ color: #111111; }}
    .contact-info, .separator {{ color: #333333; }}
    .section-title {{
        margin-bottom: var(--section-title-after);
        padding-bottom: 0.1em;
        color: #111111;
        font-weight: var(--section-title-font-weight);
    }}
    .education-item, .work-item, .project-item {{ margin-bottom: var(--item-spacing); }}
    .education-header, .work-header, .project-header {{ gap: 0.3em; }}
    .list-item, .generic-list-item {{ margin-bottom: var(--paragraph-spacing); }}
    .list-item, .generic-list-item, .project-paragraph,
    .project-numbered-list > li, .self-eval-item {{
        text-align: justify;
        text-justify: inter-ideograph;
    }}
    .project-content-block {{ margin: 0 0 var(--content-block-spacing); font-size: var(--body-font-size); color: #111111; }}
    .project-paragraph {{ margin: 0; }}
    .project-block-label {{ margin-bottom: var(--content-label-spacing); }}
    .project-numbered-list {{
        list-style: none;
        margin: 0;
        padding: 0;
        counter-reset: project-duty;
    }}
    .project-numbered-list > li {{
        position: relative;
        margin-bottom: var(--numbered-item-spacing);
        padding-left: var(--list-text-indent);
        counter-increment: project-duty;
    }}
    .project-numbered-list > li::before {{
        content: "(" counter(project-duty) ")";
        position: absolute;
        left: 0;
        width: calc(var(--list-text-indent) - var(--list-marker-gap));
        text-align: right;
        white-space: nowrap;
    }}

    .resume-container {{
        overflow: visible;
        max-height: none;
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
        {rendered_content}
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
    from pypdf import PdfReader
    from .layout import enforce_page_limit, normalize_page_mode

    html_content = render_resume_to_html(resume_data, style, photo, lang, layout_config)
    pdf_bytes = render_html_with_chromium(html_content)
    if pdf_bytes is not None:
        page_count = len(PdfReader(BytesIO(pdf_bytes)).pages)
        enforce_page_limit(normalize_page_mode((style or {}).get("pageMode")), page_count)
        return pdf_bytes

    from weasyprint import HTML

    document = HTML(string=html_content, base_url=os.getcwd()).render()
    enforce_page_limit(normalize_page_mode((style or {}).get("pageMode")), len(document.pages))
    return document.write_pdf()
