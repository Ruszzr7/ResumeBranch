"""Create an editable Word version of a structured resume."""

from __future__ import annotations

import base64
import re
from io import BytesIO

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from .resume_labels import LABELS
from .resume_data import normalize_resume_data


def _set_cell_borderless(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "nil")


def _set_cell_margins(cell, top=0, start=0, bottom=0, end=0) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _set_font(run, size: float, bold: bool = False, color: str = "212529") -> None:
    run.font.name = "Arial"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def _add_markdown_runs(paragraph, text: object, size: float, color: str = "212529") -> None:
    value = str(text or "").strip()
    parts = re.split(r"(\*\*.*?\*\*)", value)
    for part in parts:
        if not part:
            continue
        bold = part.startswith("**") and part.endswith("**")
        content = part[2:-2] if bold else part
        _set_font(paragraph.add_run(content), size, bold=bold, color=color)


def _paragraph_spacing(paragraph, *, before=0, after=0, line=1.15) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line


def _section_title(document, text: str, font_size: float, module_spacing: float) -> None:
    paragraph = document.add_paragraph()
    _paragraph_spacing(paragraph, before=max(2, module_spacing * 2.5), after=3, line=1)
    _set_font(paragraph.add_run(text), font_size * 1.1, bold=True)
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "3")
    bottom.set(qn("w:color"), "333333")
    borders.append(bottom)
    p_pr.append(borders)


def _two_column_line(document, left: str, right: str, font_size: float, *, bold_left=True) -> None:
    table = document.add_table(rows=1, cols=2)
    table.autofit = False
    table.columns[0].width = Mm(145)
    table.columns[1].width = Mm(40)
    for cell in table.rows[0].cells:
        _set_cell_borderless(cell)
        _set_cell_margins(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    left_p, right_p = table.cell(0, 0).paragraphs[0], table.cell(0, 1).paragraphs[0]
    _paragraph_spacing(left_p, after=0, line=1.05)
    _paragraph_spacing(right_p, after=0, line=1.05)
    _set_font(left_p.add_run(left), font_size, bold=bold_left)
    right_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_font(right_p.add_run(right), font_size, color="4B5563")


def _date_range(item: dict) -> str:
    values = item.get("date_range") or []
    if isinstance(values, list) and values:
        return " - ".join(str(value) for value in values[:2] if value)
    return " - ".join(value for value in (item.get("start_date", ""), item.get("end_date", "")) if value)


def _bullet(document, text: object, font_size: float) -> None:
    value = str(text)
    if re.match(r"^\s*(?:[（(]?\d{1,2}[）).、．]|[一二三四五六七八九十]+[、.．])\s*", value):
        paragraph = document.add_paragraph()
        _paragraph_spacing(paragraph, after=1.5, line=1.12)
        _add_markdown_runs(paragraph, value, font_size)
        return
    paragraph = document.add_paragraph(style="List Bullet")
    _paragraph_spacing(paragraph, after=1.5, line=1.12)
    paragraph.paragraph_format.left_indent = Mm(4.5)
    paragraph.paragraph_format.first_line_indent = Mm(-3)
    _add_markdown_runs(paragraph, value.lstrip("• "), font_size)


def _generate_docx_legacy(resume_data: dict, style: dict | None = None, photo: str | None = None, lang: str = "zh") -> bytes:
    """Return a fully editable DOCX using the same content and layout controls as PDF export."""
    data = normalize_resume_data(resume_data)
    labels = LABELS.get(lang, LABELS["zh"])
    colon = "：" if lang == "zh" else ": "
    from .layout import apply_page_mode_defaults
    style = apply_page_mode_defaults(style)
    font_size = float(style.get("fontSize", 11))
    module_spacing = float(style.get("moduleMargin", 1))
    page_break_before = style.get("pageBreakBefore", "")

    document = Document()

    def maybe_page_break(key: str) -> None:
        if page_break_before == key:
            document.add_page_break()

    section = document.sections[0]
    section.start_type = WD_SECTION.NEW_PAGE
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(float(style.get("marginTop", 9)))
    section.bottom_margin = Mm(float(style.get("marginBottom", 9)))
    section.left_margin = Mm(float(style.get("marginLeft", 9)))
    section.right_margin = Mm(float(style.get("marginRight", 9)))
    section.header_distance = Mm(5)
    section.footer_distance = Mm(5)

    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(font_size)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = float(style.get("lineHeight", 1.6))

    basics = data.get("basics") or {}
    header = document.add_table(rows=1, cols=3)
    header.autofit = False
    header.columns[0].width, header.columns[1].width, header.columns[2].width = Mm(25), Mm(135), Mm(25)
    for cell in header.rows[0].cells:
        _set_cell_borderless(cell)
        _set_cell_margins(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    center = header.cell(0, 1)
    name_p = center.paragraphs[0]
    name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _paragraph_spacing(name_p, after=2, line=1)
    _set_font(name_p.add_run(basics.get("name") or labels["nameNotSet"]), font_size * 1.5, bold=True)
    contact = " | ".join(str(basics.get(key)) for key in ("gender", "phone", "email") if basics.get(key))
    if contact:
        p = center.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _paragraph_spacing(p, after=1, line=1)
        _set_font(p.add_run(contact), font_size * 0.82, color="6B7280")
    if basics.get("target_position"):
        p = center.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _paragraph_spacing(p, line=1)
        _set_font(p.add_run(f'{labels["targetPosition"]}：{basics["target_position"]}'), font_size * 0.85, bold=True)

    display_photo = photo or basics.get("photo")
    if display_photo:
        try:
            encoded = display_photo.split(",", 1)[-1]
            image_stream = BytesIO(base64.b64decode(encoded))
            p = header.cell(0, 2).paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p.add_run().add_picture(image_stream, width=Mm(21), height=Mm(26))
        except (ValueError, TypeError):
            pass

    education = data.get("education") or []
    if education:
        maybe_page_break("education:0")
        _section_title(document, labels["education"], font_size, module_spacing)
        for item_index, item in enumerate(education):
            if item_index > 0:
                maybe_page_break(f"education:{item_index}")
            title = " · ".join(value for value in (item.get("school_name", ""), item.get("degree", ""), item.get("major", "")) if value)
            _two_column_line(document, title or labels["schoolNotSet"], _date_range(item), font_size)
            metrics = []
            if item.get("gpa"):
                value = str(item["gpa"])
                if item.get("gpa_scale"):
                    value += f'/{item["gpa_scale"]}'
                metrics.append(f'{labels["gpa"]}：{value}')
            if item.get("ranking"):
                metrics.append(f'{labels["ranking"]}：{item["ranking"]}')
            if item.get("average_score"):
                metrics.append(f'{labels["averageScore"]}：{item["average_score"]}')
            tags = item.get("school_tags") or []
            if tags:
                metrics.append(" · ".join(str(tag) for tag in tags))
            if metrics:
                p = document.add_paragraph()
                _paragraph_spacing(p, after=1, line=1.1)
                _set_font(p.add_run(" | ".join(metrics)), font_size * 0.9, color="4B5563")
            for thesis in item.get("theses") or []:
                if not isinstance(thesis, dict):
                    continue
                if thesis.get("title"):
                    p = document.add_paragraph()
                    _paragraph_spacing(p, after=1, line=1.1)
                    _set_font(p.add_run(f'{labels["thesis"]}：{thesis["title"]}'), font_size * 0.92, bold=True)
                for detail in thesis.get("details") or []:
                    _bullet(document, detail, font_size * 0.92)

    work = data.get("work_experience") or []
    if work:
        maybe_page_break("work_experience:0")
        _section_title(document, labels["workExperience"], font_size, module_spacing)
        for item_index, item in enumerate(work):
            if item_index > 0:
                maybe_page_break(f"work_experience:{item_index}")
            left = " · ".join(value for value in (item.get("company_name", ""), item.get("job_title", ""), item.get("job_type", "")) if value)
            _two_column_line(document, left or labels["companyNotSet"], _date_range(item), font_size)
            for detail in item.get("details") or []:
                _bullet(document, detail, font_size)

    projects = data.get("project_experience") or []
    if projects:
        maybe_page_break("project_experience:0")
        _section_title(document, labels["projectExperience"], font_size, module_spacing)
        for item_index, item in enumerate(projects):
            if item_index > 0:
                maybe_page_break(f"project_experience:{item_index}")
            name = item.get("project_name") or item.get("name") or labels["projectNotSet"]
            role = item.get("role", "")
            left = f"{name} · {role}" if role else name
            _two_column_line(document, left, _date_range(item), font_size)
            for detail in item.get("details") or []:
                _bullet(document, detail, font_size)

    others = data.get("others") or {}
    if any(others.get(key) for key in ("skills", "certificates", "languages")):
        maybe_page_break("others")
        _section_title(document, labels["others"], font_size, module_spacing)
        for key, label in (("skills", labels["skills"]), ("certificates", labels["certificates"]), ("languages", labels["language"])):
            values = others.get(key) or []
            if values:
                p = document.add_paragraph()
                _paragraph_spacing(p, after=1.5, line=1.12)
                _set_font(p.add_run(f"{label}："), font_size, bold=True)
                _add_markdown_runs(p, " | ".join(str(value) for value in values), font_size)

    evaluations = data.get("self_evaluation") or []
    if evaluations:
        maybe_page_break("self_evaluation")
        _section_title(document, labels["selfEvaluation"], font_size, module_spacing)
        for value in evaluations:
            p = document.add_paragraph()
            _paragraph_spacing(p, after=1.5, line=1.15)
            _add_markdown_runs(p, value, font_size)

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def generate_docx(
    resume_data: dict,
    style: dict | None = None,
    photo: str | None = None,
    lang: str = "zh",
    layout_config: dict | None = None,
) -> bytes:
    """Return an editable DOCX that follows the controlled layout configuration."""
    from .layout import apply_page_mode_defaults
    from .layout_config import normalize_layout_config

    data = normalize_resume_data(resume_data)
    labels = LABELS.get(lang, LABELS["zh"])
    colon = "：" if lang == "zh" else ": "
    layout = normalize_layout_config(layout_config)
    global_layout = layout["global"]
    style = apply_page_mode_defaults(style)
    font_size = float(style.get("fontSize", global_layout["fontSize"]))
    module_spacing = float(style.get("moduleMargin", global_layout["moduleMargin"]))
    page_break_before = style.get("pageBreakBefore", "")
    hidden_sections = set(global_layout["hiddenSections"])

    document = Document()
    section = document.sections[0]
    section.start_type = WD_SECTION.NEW_PAGE
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = Mm(float(style.get("marginTop", global_layout["marginVertical"])))
    section.bottom_margin = Mm(float(style.get("marginBottom", global_layout["marginVertical"])))
    section.left_margin = Mm(float(style.get("marginLeft", global_layout["marginHorizontal"])))
    section.right_margin = Mm(float(style.get("marginRight", global_layout["marginHorizontal"])))

    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(font_size)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = float(style.get("lineHeight", global_layout["lineHeight"]))

    def title(section_id: str, fallback: str) -> None:
        text = global_layout.get("titleOverrides", {}).get(section_id, {}).get(lang, fallback)
        paragraph = document.add_paragraph()
        _paragraph_spacing(paragraph, before=max(2, module_spacing * 2.5), after=3, line=1)
        _set_font(paragraph.add_run(text), font_size * 1.1, bold=True)
        p_pr = paragraph._p.get_or_add_pPr()
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for key, value in (("val", "single"), ("sz", "6"), ("space", "3"), ("color", "333333")):
            bottom.set(qn(f"w:{key}"), value)
        borders.append(bottom)
        p_pr.append(borders)

    def maybe_break(key: str) -> None:
        if page_break_before == key:
            document.add_page_break()

    def add_details(details, details_style: str) -> None:
        for detail in details or []:
            if details_style == "paragraph":
                paragraph = document.add_paragraph()
                _paragraph_spacing(paragraph, after=1.5, line=1.12)
                _add_markdown_runs(paragraph, detail, font_size)
            else:
                _bullet(document, detail, font_size)

    basics = data.get("basics") or {}
    basics_layout = layout["basics"]
    hidden_basics = set(basics_layout["hiddenFields"])
    show_photo = (photo or basics.get("photo")) and "photo" not in hidden_basics
    header = document.add_table(rows=1, cols=3)
    header.autofit = False
    header.columns[0].width, header.columns[1].width, header.columns[2].width = Mm(25), Mm(135), Mm(25)
    for cell in header.rows[0].cells:
        _set_cell_borderless(cell)
        _set_cell_margins(cell)
    content_cell = header.cell(0, 0) if basics_layout["preset"] == "left-aligned" else header.cell(0, 1)
    alignment = WD_ALIGN_PARAGRAPH.LEFT if basics_layout["preset"] == "left-aligned" else WD_ALIGN_PARAGRAPH.CENTER
    name_p = content_cell.paragraphs[0]
    name_p.alignment = alignment
    _paragraph_spacing(name_p, after=2, line=1)
    _set_font(name_p.add_run(basics.get("name") or labels["nameNotSet"]), font_size * 1.5, bold=True)
    contact_values = [str(basics.get(key)) for key in ("gender",) if basics.get(key) and key not in hidden_basics]
    if basics.get("birth_date") and "birth_date" not in hidden_basics:
        contact_values.append(f'{labels["birthDate"]}{colon}{basics["birth_date"]}')
    contact_values.extend(str(basics.get(key)) for key in ("phone", "email") if basics.get(key) and key not in hidden_basics)
    if "additional_fields" not in hidden_basics:
        contact_values.extend(
            f'{item.get("label")}{colon}{item.get("value")}'
            for item in basics.get("additional_fields", [])
            if item.get("label") and item.get("value")
        )
    if contact_values:
        if basics_layout["contactLayout"] == "stacked":
            for value in contact_values:
                p = content_cell.add_paragraph()
                p.alignment = alignment
                _set_font(p.add_run(value), font_size * 0.82, color="6B7280")
        else:
            p = content_cell.add_paragraph()
            p.alignment = alignment
            _set_font(p.add_run(" | ".join(contact_values)), font_size * 0.82, color="6B7280")
    if basics.get("target_position") and "target_position" not in hidden_basics:
        p = content_cell.add_paragraph()
        p.alignment = alignment
        _set_font(p.add_run(f'{labels["targetPosition"]}{colon}{basics["target_position"]}'), font_size * 0.85, bold=True)
    if show_photo:
        try:
            encoded = (photo or basics.get("photo")).split(",", 1)[-1]
            p = header.cell(0, 2).paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p.add_run().add_picture(BytesIO(base64.b64decode(encoded)), width=Mm(21), height=Mm(26))
        except (ValueError, TypeError):
            pass

    def render_education() -> None:
        items = data.get("education") or []
        if not items or "education" in hidden_sections:
            return
        cfg = layout["education"]
        hidden_metrics = set(cfg["hiddenMetrics"])
        maybe_break("education:0")
        title("education", labels["education"])
        for index, item in enumerate(items):
            if index:
                maybe_break(f"education:{index}")
            school = item.get("school_name") or labels["schoolNotSet"]
            tags = item.get("school_tags") or []
            tag_text = " ".join(f"[{tag}]" if cfg["schoolTagStyle"] == "outline" else str(tag) for tag in tags)
            if cfg["schoolTagStyle"] == "hidden":
                tag_text = ""
            degree = " · ".join(value for value in (item.get("degree", ""), item.get("major", "")) if value)
            date = _date_range(item)
            metrics = []
            if item.get("gpa") and "gpa" not in hidden_metrics:
                value = str(item["gpa"]) + (f'/{item["gpa_scale"]}' if item.get("gpa_scale") else "")
                metrics.append(f'{labels["gpa"]}{colon}{value}')
            if item.get("ranking") and "ranking" not in hidden_metrics:
                metrics.append(f'{labels["ranking"]}{colon}{item["ranking"]}')
            if item.get("average_score") and "average_score" not in hidden_metrics:
                metrics.append(f'{labels["averageScore"]}{colon}{item["average_score"]}')
            if cfg["preset"] in {"three-column", "compact"}:
                table = document.add_table(rows=1, cols=4)
                table.autofit = False
                for column, width in zip(table.columns, (Mm(47), Mm(47), Mm(55), Mm(36))):
                    column.width = width
                for cell in table.rows[0].cells:
                    _set_cell_borderless(cell)
                    _set_cell_margins(cell)
                values = [" ".join(v for v in (school, tag_text) if v), degree, " · ".join(metrics), date]
                for cell, value in zip(table.rows[0].cells, values):
                    p = cell.paragraphs[0]
                    _set_font(p.add_run(value), font_size, bold=cell is table.cell(0, 0))
                table.cell(0, 3).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            else:
                left = " · ".join(v for v in (school, tag_text, degree) if v)
                _two_column_line(document, left, date, font_size)
                if metrics:
                    p = document.add_paragraph()
                    _set_font(p.add_run(" | ".join(metrics)), font_size * 0.9, color="4B5563")
            if cfg["thesisDisplay"] != "hidden":
                for thesis in item.get("theses") or []:
                    if not isinstance(thesis, dict):
                        continue
                    if thesis.get("title"):
                        p = document.add_paragraph()
                        _set_font(p.add_run(f'{labels["thesis"]}{colon}{thesis["title"]}'), font_size * 0.92, bold=True)
                    if cfg["thesisDisplay"] == "expanded":
                        add_details(thesis.get("details"), "bullets")

    def work_groups():
        items = list(data.get("work_experience") or [])
        if not global_layout["splitWorkExperience"]:
            return [("work_experience", labels["workExperience"], items)]
        regular = [item for item in items if not re.search(r"实习|intern", str(item.get("job_type", "")), re.I)]
        interns = [item for item in items if re.search(r"实习|intern", str(item.get("job_type", "")), re.I)]
        return [("work_experience", labels["workExperience"], regular), ("internship_experience", "Internship Experience" if lang == "en" else "实习经历", interns)]

    def render_work(section_id: str, fallback: str, items: list) -> None:
        if not items or section_id in hidden_sections:
            return
        cfg = layout["work_experience"]
        maybe_break(f"{section_id}:0")
        title(section_id, fallback)
        for index, item in enumerate(items):
            if index:
                maybe_break(f"{section_id}:{index}")
            pieces = [item.get("company_name", ""), item.get("job_title", "")]
            if cfg["showJobType"]:
                pieces.append(item.get("job_type", ""))
            _two_column_line(document, " · ".join(v for v in pieces if v), _date_range(item), font_size)
            add_content_blocks(item)

    def add_content_blocks(item: dict) -> None:
        blocks = item.get("content_blocks") or []
        if not blocks:
            add_details(item.get("details"), "bullets")
            return
        for block in blocks:
            block_type = block.get("type", "paragraph")
            label = str(block.get("label") or "").strip()
            if block_type == "paragraph":
                paragraph = document.add_paragraph()
                _paragraph_spacing(paragraph, after=1, line=1.08)
                if label:
                    _set_font(paragraph.add_run(f"{label}{colon}"), font_size, bold=True)
                _add_markdown_runs(paragraph, block.get("text", ""), font_size)
                continue
            if label:
                paragraph = document.add_paragraph()
                _paragraph_spacing(paragraph, after=0.5, line=1.05)
                _set_font(paragraph.add_run(f"{label}{colon}"), font_size, bold=True)
            for detail_index, detail in enumerate(block.get("items") or [], 1):
                if block_type == "numbered_list":
                    paragraph = document.add_paragraph()
                    _paragraph_spacing(paragraph, after=0.5, line=1.08)
                    _set_font(paragraph.add_run(f"({detail_index}) "), font_size)
                    _add_markdown_runs(paragraph, detail, font_size)
                else:
                    _bullet(document, detail, font_size)

    def render_projects() -> None:
        items = data.get("project_experience") or []
        if not items or "project_experience" in hidden_sections:
            return
        cfg = layout["project_experience"]
        maybe_break("project_experience:0")
        title("project_experience", labels["projectExperience"])
        for index, item in enumerate(items):
            if index:
                maybe_break(f"project_experience:{index}")
            values = [item.get("project_name") or item.get("name") or labels["projectNotSet"]]
            if cfg["showRole"] and item.get("role"):
                values.append(item["role"])
            _two_column_line(document, " · ".join(values), _date_range(item) if cfg["showDate"] else "", font_size)
            add_content_blocks(item)

    def render_skills() -> None:
        skills = (data.get("others") or {}).get("skills") or []
        if not skills or "skills" in hidden_sections:
            return
        title("skills", labels["skills"])
        for value in skills:
            _bullet(document, value, font_size)

    def render_others() -> None:
        values = data.get("others") or {}
        cfg = layout["others"]
        fields = [key for key in cfg["fieldOrder"] if key != "skills" and key not in cfg["hiddenFields"] and values.get(key)]
        if not fields or "others" in hidden_sections:
            return
        maybe_break("others")
        title("others", "Certificates & Languages" if lang == "en" else "证书与语言")
        field_labels = {"skills": labels["skills"], "certificates": labels["certificates"], "languages": labels["language"]}
        separator = " · " if cfg["separator"] == "dot" else " | "
        for key in fields:
            p = document.add_paragraph()
            _set_font(p.add_run(f'{field_labels[key]}{colon}'), font_size, bold=True)
            content = separator.join(str(value) for value in values[key])
            if cfg["preset"] == "tags":
                content = "  ".join(f"[{value}]" for value in values[key])
            _add_markdown_runs(p, content, font_size)

    def render_self() -> None:
        values = data.get("self_evaluation") or []
        if not values or "self_evaluation" in hidden_sections:
            return
        cfg = layout["self_evaluation"]
        maybe_break("self_evaluation")
        title("self_evaluation", labels["selfEvaluation"])
        if cfg["preset"] == "compact":
            values = [" ".join(str(value) for value in values)]
        for value in values:
            if cfg["preset"] == "bullets":
                _bullet(document, value, font_size)
            else:
                p = document.add_paragraph()
                _add_markdown_runs(p, value, font_size)

    def render_plain_section(section_id: str, fallback: str, values: list) -> None:
        if not values or section_id in hidden_sections:
            return
        maybe_break(section_id)
        title(section_id, fallback)
        for value in values:
            _bullet(document, value, font_size)

    def render_research() -> None:
        render_plain_section("research_interests", labels["researchInterests"], data.get("research_interests") or [])

    def render_honors() -> None:
        render_plain_section("honors", labels["honors"], data.get("honors") or [])

    def render_custom_sections() -> None:
        if "custom_sections" in hidden_sections:
            return
        for index, custom in enumerate(data.get("custom_sections") or []):
            if not custom.get("title") or not custom.get("items"):
                continue
            maybe_break(f"custom_sections:{index}")
            title("custom_sections", custom["title"])
            for value in custom["items"]:
                _bullet(document, value, font_size)

    renderers = {
        "education": render_education,
        "skills": render_skills,
        "research_interests": render_research,
        "honors": render_honors,
        "project_experience": render_projects,
        "custom_sections": render_custom_sections,
        "others": render_others,
        "self_evaluation": render_self,
    }
    work_by_id = {section_id: (fallback, items) for section_id, fallback, items in work_groups()}
    for section_id in global_layout["sectionOrder"]:
        if section_id in work_by_id:
            fallback, items = work_by_id[section_id]
            render_work(section_id, fallback, items)
        elif section_id in renderers:
            renderers[section_id]()

    output = BytesIO()
    document.save(output)
    return output.getvalue()
