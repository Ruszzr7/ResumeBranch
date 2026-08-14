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


_NATIVE_LIST_MARKER_RE = re.compile(
    r"^\s*([（(]?\d{1,2}[）).、．]|[一二三四五六七八九十]+[、.．])\s*(.*)$",
    re.DOTALL,
)


def _split_native_list_marker(value: object) -> tuple[str, str] | None:
    match = _NATIVE_LIST_MARKER_RE.match(str(value or ""))
    return (match.group(1), match.group(2)) if match else None


def _module_list_content(value: object) -> str:
    parts = _split_native_list_marker(value)
    return parts[1] if parts else str(value or "")


def _is_fully_bold(value: object) -> bool:
    return bool(re.fullmatch(r"\*\*[^*][\s\S]*\*\*", _module_list_content(value).strip()))


def render_resume_to_html(resume_data: dict, style: dict = None, photo: str = None, lang: str = 'zh', layout_config: dict = None) -> str:
    """将简历数据渲染为HTML

    Args:
        resume_data: 简历数据字典
        style: 样式参数，包括marginTop, marginBottom, marginLeft, marginRight, moduleMargin, lineHeight, fontSize
        photo: 证件照base64编码（可选，如果为None则从resume_data中提取）
        lang: 语言，'zh' 或 'en'
    """
    resume_data = normalize_resume_data(resume_data)
    from .layout_config import (
        format_compact_academic_metric,
        normalize_layout_config,
        resolve_content_block_flow,
        resolve_education_column_widths,
        resolve_layout_tokens,
        resolve_module_layout,
    )
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

    education_items = resume_data.get("education") or []
    education_hidden_metrics = set(layout_config["education"]["hiddenMetrics"])

    def compact_education_metric(item: dict) -> str:
        return format_compact_academic_metric(
            item,
            education_hidden_metrics,
            average_score_label=labels["averageScore"],
        )

    compact_education_metrics = [compact_education_metric(item) for item in education_items]
    education_column_widths = resolve_education_column_widths(
        tokens,
        schools=[str(item.get("school_name") or labels["schoolNotSet"]) for item in education_items],
        dates=[" - ".join(str(value) for value in (item.get("date_range") or [])[:2] if value) for item in education_items],
        degree_majors=[
            " · ".join(
                value for value in (item.get("degree", ""), item.get("major", "")) if value
            )
            for item in education_items
        ],
        compact_metrics=compact_education_metrics,
    )

    def break_class(key: str) -> str:
        return ' page-break-before' if page_break_before == key else ''

    def hidden(section: str) -> bool:
        return section in global_layout["hiddenSections"]

    def order_style(section: str) -> str:
        try:
            order = global_layout["sectionOrder"].index(section) + 1
        except ValueError:
            order = 99
        module_tokens = tokens["modules"].get(section, tokens["modules"]["custom_sections"])
        return (
            f' style="order:{order};'
            f'--item-spacing:{module_tokens["itemSpacingPt"]:g}pt;'
            f'--paragraph-spacing:{module_tokens["paragraphSpacingPt"]:g}pt;'
            f'--content-block-spacing:{module_tokens["contentBlockSpacingPt"]:g}pt;'
            f'--module-indent:{module_tokens["indentPt"]:g}pt"'
        )

    def section_title(section: str, fallback: str) -> str:
        return global_layout.get("titleOverrides", {}).get(section, {}).get(lang, fallback)

    def merged_into_education(section: str) -> bool:
        return bool(resume_data.get("education")) and global_layout.get("sectionPlacements", {}).get(section) == "education"

    def title_markup(section: str, text: str) -> str:
        module = resolve_module_layout(layout_config, section)
        return (
            f'<h2 class="section-title title-{module["resolvedTitleStyle"]}" '
            f'style="text-align:{module["resolvedTitleAlignment"]}">'
            f'{format_markdown(text)}</h2>'
        )

    def component_rows_markup(module_id: str, values: dict[str, str], excluded: set[str] | None = None) -> str:
        module = resolve_module_layout(layout_config, module_id)
        hidden_components = set(module["hiddenComponents"]) | set(excluded or set())
        parts = ['<div class="module-component-rows">']
        for row in module["componentRows"]:
            active_cells = []
            for cell in row["cells"]:
                components = [item for item in cell["components"] if item not in hidden_components and values.get(item)]
                if components:
                    active_cells.append((cell, components))
            if not active_cells:
                continue
            is_compact_education_header = (
                module_id == "education"
                and module["preset"] == "compact"
                and len(active_cells) == 3
                and "school" in active_cells[0][1]
                and any(item in active_cells[1][1] for item in ("degree", "major", "metrics"))
                and "date" in active_cells[2][1]
            )
            columns = (
                "var(--education-compact-side-column) var(--education-middle-column) var(--education-compact-side-column)"
                if is_compact_education_header
                else " ".join("max-content" if cell["width"] == "content" else "minmax(0, 1fr)" for cell, _ in active_cells)
            )
            spacing = tokens["modules"][module_id]["rowSpacingPt"]
            parts.append(f'<div class="module-component-row" style="grid-template-columns:{columns};margin-bottom:{spacing:g}pt">')
            for cell, components in active_cells:
                justify = "flex-end" if cell["alignment"] == "right" else ("center" if cell["alignment"] == "center" else "flex-start")
                parts.append(
                    f'<div class="module-component-cell flow-{cell["flow"]}" '
                    f'style="text-align:{cell["alignment"]};justify-content:{justify}">'
                )
                for component in components:
                    parts.append(f'<span class="module-component component-{component}">{values[component]}</span>')
                parts.append('</div>')
            parts.append('</div>')
        parts.append('</div>')
        return "".join(parts)

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
        html_parts.append(f'<div class="personal-info basics-{basics_layout["preset"]} contact-{basics_layout["contactLayout"]}" style="order:0">')
        personal_meta = " | ".join(filter(None, [
            str(basics.get("gender", "")) if "gender" not in hidden_basics else "",
            f'{labels["birthDate"]}：{basics["birth_date"]}' if basics.get("birth_date") and "birth_date" not in hidden_basics else "",
        ]))
        contact = " | ".join(filter(None, [
            str(basics.get("phone", "")) if "phone" not in hidden_basics else "",
            str(basics.get("email", "")) if "email" not in hidden_basics else "",
        ]))
        additional = " | ".join(
            f'{item.get("label", "")}：{item.get("value", "")}'
            for item in basics.get("additional_fields", [])
            if item.get("label") and item.get("value") and "additional_fields" not in hidden_basics
        )
        html_parts.append(component_rows_markup("basics", {
            "name": format_markdown(basics.get("name", labels["nameNotSet"])),
            "target_position": format_markdown(f'{labels["targetPosition"]}：{basics["target_position"]}') if basics.get("target_position") and "target_position" not in hidden_basics else "",
            "personal_meta": format_markdown(personal_meta),
            "contact": format_markdown(contact),
            "additional_fields": format_markdown(additional),
            "photo": f'<img src="{escape(display_photo, quote=True)}" class="profile-photo component-photo" alt="证件照" />' if display_photo and "photo" not in hidden_basics else "",
        }))
        html_parts.append('</div>')  # personal-info
        commit_section("basics", chunk_start)

    # 教育经历
    if resume_data.get("education") and len(resume_data["education"]) > 0 and not hidden("education"):
        chunk_start = len(html_parts)
        education_layout = layout_config["education"]
        education_module = resolve_module_layout(layout_config, "education")
        hidden_metrics = set(education_layout["hiddenMetrics"])
        html_parts.append(f'<section class="section education-section preset-{education_layout["preset"]}{break_class("education:0")}"{order_style("education")}>')
        html_parts.append(title_markup("education", section_title("education", labels["education"])))

        for edu_index, edu in enumerate(resume_data["education"]):
            item_break = break_class(f"education:{edu_index}") if edu_index > 0 else ''
            html_parts.append(f'<div class="education-item preset-{education_layout["preset"]}{item_break}">')
            academic_metrics = []
            compact_metric = compact_education_metrics[edu_index]
            if edu.get("gpa") and "gpa" not in hidden_metrics:
                gpa_value = str(edu["gpa"])
                if edu.get("gpa_scale"):
                    gpa_value += f'/{edu["gpa_scale"]}'
                academic_metrics.append(f'{labels["gpa"]}：{gpa_value}')
            if edu.get("ranking") and "ranking" not in hidden_metrics:
                academic_metrics.append(f'{labels["ranking"]}：{edu["ranking"]}')
            if edu.get("average_score") and "average_score" not in hidden_metrics:
                academic_metrics.append(f'{labels["averageScore"]}：{edu["average_score"]}')

            date_range = edu.get("date_range", [])
            date_str = ""
            if len(date_range) > 0:
                date_str = date_range[0]
                if len(date_range) > 1:
                    date_str += f" - {date_range[1]}"
            component_values = {
                "school": format_markdown(edu.get("school_name", labels["schoolNotSet"])),
                "school_tags": " · ".join(format_markdown(tag) for tag in (edu.get("school_tags") or [])) if education_layout["schoolTagStyle"] != "hidden" else "",
                "degree": format_markdown(edu.get("degree", "")),
                "major": format_markdown(edu.get("major", "")),
                "metrics": format_markdown(
                    compact_education_metric(edu)
                    if education_layout["preset"] == "compact"
                    else " · ".join(academic_metrics)
                ),
                "date": format_markdown(date_str),
            }
            hidden_components = set(education_module["hiddenComponents"]) | {"theses"}
            html_parts.append('<div class="module-component-rows">')
            for row in education_module["componentRows"]:
                cells = []
                for cell in row["cells"]:
                    components = [item for item in cell["components"] if item not in hidden_components and component_values.get(item)]
                    if components:
                        cells.append((cell, components))
                if not cells:
                    continue
                is_compact_header = (
                    education_layout["preset"] == "compact"
                    and len(cells) == 3
                    and "school" in cells[0][1]
                    and any(component in cells[1][1] for component in ("degree", "major", "metrics"))
                    and "date" in cells[2][1]
                )
                columns = (
                    "var(--education-compact-side-column) var(--education-middle-column) var(--education-compact-side-column)"
                    if is_compact_header
                    else " ".join("max-content" if cell["width"] == "content" else "minmax(0, 1fr)" for cell, _ in cells)
                )
                row_spacing = tokens["modules"]["education"]["rowSpacingPt"]
                html_parts.append(f'<div class="module-component-row" style="grid-template-columns:{columns};margin-bottom:{row_spacing:g}pt">')
                for cell, components in cells:
                    justify = "flex-end" if cell["alignment"] == "right" else ("center" if cell["alignment"] == "center" else "flex-start")
                    html_parts.append(
                        f'<div class="module-component-cell flow-{cell["flow"]}" '
                        f'style="text-align:{cell["alignment"]};justify-content:{justify}">'
                    )
                    for component in components:
                        html_parts.append(f'<span class="module-component component-{component}">{component_values[component]}</span>')
                    html_parts.append('</div>')
                html_parts.append('</div>')
            html_parts.append('</div>')

            # 论文
            if edu.get("theses") and len(edu["theses"]) > 0 and education_layout["thesisDisplay"] != "hidden" and "theses" not in education_module["hiddenComponents"]:
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

        merged_sections = [
            ("research_interests", labels["researchInterests"], resume_data.get("research_interests") or []),
            ("honors", labels["honors"], resume_data.get("honors") or []),
            ("publications", "Publications" if lang == "en" else "论文", resume_data.get("publications") or []),
        ]
        other_values = resume_data.get("others") or {}
        other_layout = layout_config["others"]
        other_hidden = set(other_layout["hiddenFields"]) | set(other_layout["hiddenComponents"])
        other_labels = {"certificates": labels["certificates"], "languages": labels["language"]}
        other_separator = " · " if other_layout["separator"] == "dot" else " | "
        merged_other_values = [
            f'{other_labels[field]}：{other_separator.join(str(value) for value in other_values[field])}'
            for field in other_layout["fieldOrder"]
            if field in other_labels and field not in other_hidden and other_values.get(field)
        ]
        merged_sections.append(("others", "Certificates & Languages" if lang == "en" else "证书与语言", merged_other_values))
        merged_sections.sort(key=lambda item: global_layout["sectionOrder"].index(item[0]))
        for section_id, fallback, values in merged_sections:
            if not merged_into_education(section_id) or hidden(section_id) or not values:
                continue
            html_parts.append(f'<h4 class="subfield-title education-merged-title">{format_markdown(section_title(section_id, fallback))}</h4>')
            list_style = layout_config.get(section_id, {}).get("listStyle", "bullet")
            html_parts.append(f'<ul class="list-items module-list list-style-{list_style}">')
            for value in values:
                marker_class = " marker-bold" if _is_fully_bold(value) else ""
                html_parts.append(f'<li class="list-item{marker_class}">{format_markdown(_module_list_content(value))}</li>')
            html_parts.append('</ul>')

        html_parts.append('</section>')
        commit_section("education", chunk_start)

    # 工作/实习经历（拆分时仍共用同一视觉预设）
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
        work_layout = layout_config[section_id]
        chunk_start = len(html_parts)
        first_index = section_items[0][0]
        html_parts.append(f'<section class="section work-section preset-{work_layout["preset"]}{break_class(f"{section_id}:{first_index}")}"{order_style(section_id)}>')
        html_parts.append(title_markup(section_id, section_title(section_id, fallback_title)))

        for item_position, (work_index, work) in enumerate(section_items):
            item_break = break_class(f"{section_id}:{work_index}") if item_position > 0 else ''
            work_classes = (
                f'work-item preset-{work_layout["preset"]} '
                f'date-{work_layout["datePosition"]}{item_break}'
            )
            html_parts.append(f'<div class="{work_classes}">')
            date_range = work.get("date_range", [])
            date_str = ""
            if len(date_range) > 0:
                date_str = date_range[0]
                if len(date_range) > 1:
                    date_str += f" - {date_range[1]}"
            html_parts.append(component_rows_markup(section_id, {
                "organization": format_markdown(work.get("company_name", labels["companyNotSet"])),
                "position": format_markdown(work.get("job_title", "")),
                "job_type": format_markdown(f'({work["job_type"]})') if work.get("job_type") and work_layout["showJobType"] else "",
                "date": format_markdown(date_str),
            }, {"content"}))

            # 工作详情沿用与项目经历一致的语义块，避免标题和已编号内容被重复加圆点。
            for block in work.get("content_blocks") or []:
                flow = resolve_content_block_flow(block)
                if not flow["visible"]:
                    continue
                block_type = flow["type"]
                label = flow["label"]
                label_class = " is-bold" if flow["labelBold"] else ""
                label_html = f'<span class="project-inline-label{label_class}">{format_markdown(label)}：</span>' if label else ''
                semantic_class = " has-semantic-label" if flow["labelMarker"] == "bullet" else ""
                html_parts.append(f'<div class="project-content-block block-{block_type}{semantic_class}">')
                if block_type == "paragraph":
                    html_parts.append(f'<p class="project-paragraph">{label_html}{format_markdown(block.get("text", ""))}</p>')
                else:
                    if flow["labelPlacement"] == "separate":
                        html_parts.append(f'<div class="project-block-label{label_class}">{format_markdown(label)}：</div>')
                    list_class = "project-numbered-list" if block_type == "numbered_list" else "list-items"
                    tag = "ol" if block_type == "numbered_list" else "ul"
                    html_parts.append(f'<{tag} class="{list_class}">')
                    for detail in block.get("items") or []:
                        item_class = (' class="marker-bold"' if _is_fully_bold(detail) else "") if block_type == "numbered_list" else ' class="list-item"'
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
        html_parts.append(title_markup("project_experience", section_title("project_experience", labels["projectExperience"])))

        for project_index, project in enumerate(resume_data["project_experience"]):
            item_break = break_class(f"project_experience:{project_index}") if project_index > 0 else ''
            project_classes = (
                f'project-item preset-{project_layout["preset"]} '
                f'date-{project_layout["datePosition"]}{item_break}'
            )
            html_parts.append(f'<div class="{project_classes}">')
            role_value = project.get("role", "") if project_layout["showRole"] else ""
            date_range = project.get("date_range", [])
            date_value = ""
            if len(date_range) > 0 and project_layout["showDate"]:
                date_value = date_range[0]
                if len(date_range) > 1:
                    date_value += f" - {date_range[1]}"
            elif project.get("start_date") and project_layout["showDate"]:
                date_value = project["start_date"]
                if project.get("end_date"):
                    date_value += f" - {project['end_date']}"
            html_parts.append(component_rows_markup("project_experience", {
                "project_name": format_markdown(project.get("project_name") or project.get("name") or labels["projectNotSet"]),
                "role": format_markdown(role_value),
                "date": format_markdown(date_value),
            }, {"content"}))

            # 项目详情使用语义块：标题不带圆点，职责内部保留编号。
            for block in project.get("content_blocks") or []:
                flow = resolve_content_block_flow(block)
                if not flow["visible"]:
                    continue
                block_type = flow["type"]
                label = flow["label"]
                label_class = " is-bold" if flow["labelBold"] else ""
                label_html = f'<span class="project-inline-label{label_class}">{format_markdown(label)}：</span>' if label else ''
                semantic_class = " has-semantic-label" if flow["labelMarker"] == "bullet" else ""
                html_parts.append(f'<div class="project-content-block block-{block_type}{semantic_class}">')
                if block_type == "paragraph":
                    html_parts.append(f'<p class="project-paragraph">{label_html}{format_markdown(block.get("text", ""))}</p>')
                else:
                    if flow["labelPlacement"] == "separate":
                        html_parts.append(f'<div class="project-block-label{label_class}">{format_markdown(label)}：</div>')
                    list_class = "project-numbered-list" if block_type == "numbered_list" else "list-items"
                    tag = "ol" if block_type == "numbered_list" else "ul"
                    html_parts.append(f'<{tag} class="{list_class}">')
                    for detail in block.get("items") or []:
                        item_class = (' class="marker-bold"' if _is_fully_bold(detail) else "") if block_type == "numbered_list" else ' class="list-item"'
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
            html_parts.append(title_markup("custom_sections", custom["title"]))
            html_parts.append(f'<ul class="list-items module-list list-style-{layout_config["custom_sections"]["listStyle"]}">')
            for value in custom["items"]:
                html_parts.append(f'<li class="list-item">{format_markdown(value)}</li>')
            html_parts.append('</ul></section>')
        commit_section("custom_sections", chunk_start)

    # 其他信息
    others = resume_data.get("others") or {}
    others_layout = layout_config["others"]
    hidden_other_fields = set(others_layout["hiddenFields"]) | set(others_layout["hiddenComponents"])
    visible_other_fields = [
        field for field in others_layout["fieldOrder"]
        if field != "skills" and field not in hidden_other_fields and others.get(field)
    ]
    if visible_other_fields and not hidden("others") and not merged_into_education("others"):
        chunk_start = len(html_parts)
        html_parts.append(f'<section class="section others others-{others_layout["preset"]}{break_class("others")}"{order_style("others")}>')
        other_title = "Certificates & Languages" if lang == "en" else "证书与语言"
        html_parts.append(title_markup("others", section_title("others", other_title)))
        field_labels = {"skills": labels["skills"], "certificates": labels["certificates"], "languages": labels["language"]}
        separator = " · " if others_layout["separator"] == "dot" else " | "
        values = {
            field: format_markdown(f'{field_labels[field]}：{separator.join(str(value) for value in others[field])}')
            for field in visible_other_fields
        }
        html_parts.append(component_rows_markup("others", values))
        html_parts.append('</section>')
        commit_section("others", chunk_start)

    def render_plain_list_section(section_id: str, title: str, values: list[str]) -> None:
        if not values or hidden(section_id) or merged_into_education(section_id):
            return
        chunk_start = len(html_parts)
        html_parts.append(f'<section class="section generic-section{break_class(section_id)}"{order_style(section_id)}>')
        html_parts.append(title_markup(section_id, section_title(section_id, title)))
        list_style = layout_config[section_id]["listStyle"]
        html_parts.append(f'<ul class="list-items module-list list-style-{list_style}">')
        for value in values:
            marker_class = " marker-bold" if _is_fully_bold(value) else ""
            section_item_class = " skill-list-item" if section_id == "skills" else ""
            item_html = format_markdown(_module_list_content(value))
            html_parts.append(f'<li class="list-item{section_item_class}{marker_class}">{item_html}</li>')
        html_parts.append('</ul></section>')
        commit_section(section_id, chunk_start)

    render_plain_list_section("skills", labels["skills"], others.get("skills") or [])
    render_plain_list_section("research_interests", labels["researchInterests"], resume_data.get("research_interests") or [])
    render_plain_list_section("honors", labels["honors"], resume_data.get("honors") or [])
    render_plain_list_section("publications", "Publications" if lang == "en" else "论文", resume_data.get("publications") or [])

    # 自我评价
    if resume_data.get("self_evaluation") and len(resume_data["self_evaluation"]) > 0 and not hidden("self_evaluation"):
        chunk_start = len(html_parts)
        self_layout = layout_config["self_evaluation"]
        html_parts.append(f'<section class="section self-evaluation self-{self_layout["preset"]}{break_class("self_evaluation")}"{order_style("self_evaluation")}>')
        html_parts.append(title_markup("self_evaluation", section_title("self_evaluation", labels["selfEvaluation"])))
        evaluations = resume_data["self_evaluation"]
        if self_layout["preset"] == "compact":
            evaluations = [" ".join(str(item) for item in evaluations)]
        list_style = self_layout["listStyle"]
        html_parts.append(f'<div class="module-list list-style-{list_style}">')
        for eval_item in evaluations:
            html_parts.append(f'<div class="self-eval-item list-item">{format_markdown(eval_item)}</div>')
        html_parts.append('</div>')
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
        --manual-title-font-weight: {400 if int(resume_data.get('formatting_version') or 0) >= 1 else tokens['entryTitleFontWeight']};
        --manual-name-font-weight: {400 if int(resume_data.get('formatting_version') or 0) >= 1 else tokens['nameFontWeight']};
        --section-title-font-weight: {tokens['sectionTitleFontWeight']};
        --name-font-weight: {tokens['nameFontWeight']};
        --label-font-weight: {tokens['labelFontWeight']};
        --letter-spacing: {tokens['letterSpacingPt']:g}pt;
        --module-margin: {tokens['moduleSpacingPt']:g}pt;
        --header-name-after: {tokens['headerNameAfterPt']:g}pt;
        --section-title-after: {tokens['sectionTitleAfterPt']:g}pt;
        --section-title-border-gap: {tokens['sectionTitleBorderGapPt']:g}pt;
        --item-spacing: {tokens['itemSpacingPt']:g}pt;
        --paragraph-spacing: {tokens['paragraphSpacingPt']:g}pt;
        --content-block-spacing: {tokens['contentBlockSpacingPt']:g}pt;
        --content-label-spacing: {tokens['contentLabelSpacingPt']:g}pt;
        --numbered-item-spacing: {tokens['numberedItemSpacingPt']:g}pt;
        --list-text-indent: {tokens['listTextIndentPt']:g}pt;
        --module-indent: 0pt;
        --list-marker-gap: {tokens['listMarkerGapPt']:g}pt;
        --education-side-column: {tokens['educationSideColumnMm']:g}mm;
        --education-compact-side-column: {education_column_widths['sideMm']:g}mm;
        --education-middle-column: {education_column_widths['middleMm']:g}mm;
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
        width: {tokens['photoWidthMm']:g}mm;
        height: {tokens['photoHeightMm']:g}mm;
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
        margin-bottom: 0;
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
        font-weight: var(--manual-title-font-weight);
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
    .education-item .education-middle-column {{ grid-column: 1; grid-row: 2; }}
    .education-item .graduation-date {{ grid-column: 2; grid-row: 1; }}
    .education-item .school-info,
    .education-item .education-middle-column,
    .education-item .education-degree-column,
    .education-item .education-metrics-column {{
        min-width: 0;
        overflow-wrap: break-word;
        word-break: break-word;
    }}
    .education-item.preset-compact .education-header {{
        display: grid;
        width: 100%;
        grid-template-columns: var(--education-compact-side-column) var(--education-middle-column) var(--education-compact-side-column);
        column-gap: 0;
        align-items: baseline;
    }}
    .module-component-rows {{ display: grid; width: 100%; }}
    .module-component-row {{ display: grid; width: 100%; align-items: baseline; gap: 0.3em; }}
    .module-component-cell {{ display: flex; min-width: 0; flex-wrap: wrap; gap: 0.3em; overflow-wrap: anywhere; }}
    .module-component-cell.flow-stacked {{ flex-direction: column; }}
    .module-component-cell.flow-inline .module-component + .module-component::before {{ content: ' · '; white-space: pre; }}
    .module-component-cell.flow-inline .component-position + .component-job_type::before {{ content: ' '; }}
    .module-component.component-school {{ font-size: var(--entry-title-font-size); font-weight: var(--manual-title-font-weight); }}
    .module-component.component-organization,
    .module-component.component-project_name {{ font-size: var(--entry-title-font-size); font-weight: var(--manual-title-font-weight); }}
    .module-component.component-name {{ font-size: var(--name-font-size); font-weight: var(--manual-name-font-weight); }}
    .module-component.component-target_position,
    .module-component.component-personal_meta,
    .module-component.component-contact,
    .module-component.component-additional_fields {{ font-size: var(--meta-font-size); font-weight: var(--meta-font-weight); color: #333333; }}
    .module-component.component-target_position {{ font-weight: var(--manual-title-font-weight); }}
    .component-photo {{ position: static; flex: none; width: {tokens['photoWidthMm']:g}mm; height: {tokens['photoHeightMm']:g}mm; object-fit: cover; }}
    .module-component.component-school_tags,
    .module-component.component-degree,
    .module-component.component-major,
    .module-component.component-metrics,
    .module-component.component-date,
    .module-component.component-position,
    .module-component.component-job_type {{ font-size: var(--label-font-size); font-weight: var(--label-font-weight); }}
    .module-component.component-role {{ font-size: var(--meta-font-size); font-weight: var(--meta-font-weight); }}
    .education-item.preset-three-column .education-header {{
        display: grid;
        width: 100%;
        grid-template-columns: var(--education-side-column) minmax(0, 1fr) var(--education-side-column);
        column-gap: 0;
        align-items: baseline;
    }}
    .education-item.preset-compact .school-info,
    .education-item.preset-three-column .school-info,
    .education-item.preset-compact .education-middle-column,
    .education-item.preset-three-column .education-middle-column,
    .education-item.preset-compact .education-degree-column,
    .education-item.preset-three-column .education-degree-column,
    .education-item.preset-compact .education-metrics-column,
    .education-item.preset-three-column .education-metrics-column {{ min-width: 0; }}
    .education-item.preset-compact .school-info,
    .education-item.preset-three-column .school-info {{ grid-column: 1; grid-row: 1; gap: 0.3em; }}
    .education-item.preset-compact .education-middle-column,
    .education-item.preset-three-column .education-middle-column {{
        grid-column: 2;
        grid-row: 1;
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        column-gap: var(--education-metric-gap);
        row-gap: 0;
        text-align: left;
    }}
    .education-item.preset-compact .graduation-date,
    .education-item.preset-three-column .graduation-date {{
        grid-column: 3;
        grid-row: 1;
        position: static;
        width: auto;
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
        font-size: var(--body-font-size);
        font-weight: var(--label-font-weight);
        color: #6c757d;
        margin-bottom: 0.25em;
        display: block;
    }}
    .education-merged-title {{
        margin: var(--item-spacing) 0 var(--paragraph-spacing);
        color: #111111;
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
        font-weight: 400;
    }}
    .list-item.marker-bold::before {{ font-weight: var(--label-font-weight); }}

    .module-list.list-style-paragraph > .list-item {{ padding-left: var(--module-indent); }}
    .module-list > .list-item {{ margin-bottom: var(--item-spacing); }}
    .module-list.list-style-paragraph > .list-item::before {{ content: none; }}
    .module-list.list-style-bullet > .list-item {{ padding-left: calc(var(--module-indent) + 1.1em); }}
    .module-list.list-style-bullet > .list-item::before {{ left: var(--module-indent); width: 0.9em; }}
    .module-list.list-style-numbered {{ counter-reset: module-list-item; }}
    .module-list.list-style-numbered > .list-item {{
        padding-left: calc(var(--module-indent) + 2em);
        counter-increment: module-list-item;
    }}
    .module-list.list-style-numbered > .list-item::before {{
        content: "(" counter(module-list-item) ")";
        left: var(--module-indent);
        width: 1.75em;
        text-align: right;
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
        font-size: var(--body-font-size);
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
        margin-top: var(--module-margin);
        margin-bottom: var(--section-title-after);
        padding-bottom: var(--section-title-border-gap);
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
    .project-content-block.has-semantic-label > .project-numbered-list,
    .project-content-block.has-semantic-label > .list-items {{
        margin-left: calc(var(--module-indent) + var(--list-text-indent));
    }}
    .project-content-block:not(.has-semantic-label) > .project-numbered-list,
    .project-content-block:not(.has-semantic-label) > .list-items {{ margin-left: var(--module-indent); }}
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
        font-weight: 400;
    }}
    .project-numbered-list > li.marker-bold::before {{ font-weight: var(--label-font-weight); }}
    .project-content-block.has-semantic-label > .project-paragraph,
    .project-content-block.has-semantic-label > .project-block-label {{
        position: relative;
        padding-left: calc(var(--module-indent) + var(--list-text-indent));
    }}
    .project-content-block.has-semantic-label > .project-paragraph::before,
    .project-content-block.has-semantic-label > .project-block-label::before {{
        content: "•";
        position: absolute;
        left: var(--module-indent);
        width: calc(var(--list-text-indent) - var(--list-marker-gap));
        text-align: center;
        font-weight: 700;
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
