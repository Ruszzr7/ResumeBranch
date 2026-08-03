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
    paragraph = document.add_paragraph(style="List Bullet")
    _paragraph_spacing(paragraph, after=1.5, line=1.12)
    paragraph.paragraph_format.left_indent = Mm(4.5)
    paragraph.paragraph_format.first_line_indent = Mm(-3)
    _add_markdown_runs(paragraph, str(text).lstrip("• "), font_size)


def generate_docx(resume_data: dict, style: dict | None = None, photo: str | None = None, lang: str = "zh") -> bytes:
    """Return a fully editable DOCX using the same content and layout controls as PDF export."""
    data = normalize_resume_data(resume_data)
    labels = LABELS.get(lang, LABELS["zh"])
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
