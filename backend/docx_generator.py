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

DEFAULT_FONT_SPEC = {
    "latinFont": "Arial",
    "eastAsiaFont": "Microsoft YaHei",
}


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


def _set_fixed_table_widths(table, widths_mm: tuple[float, ...]) -> None:
    """Keep Word from stretching a compact table back to the page edge."""
    table.autofit = False
    table_properties = table._tbl.tblPr

    layout = table_properties.first_child_found_in("w:tblLayout")
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        table_properties.append(layout)
    layout.set(qn("w:type"), "fixed")

    table_width = table_properties.first_child_found_in("w:tblW")
    if table_width is None:
        table_width = OxmlElement("w:tblW")
        table_properties.append(table_width)
    table_width.set(qn("w:type"), "dxa")
    table_width.set(qn("w:w"), str(round(sum(widths_mm) * 1440 / 25.4)))

    table_indent = table_properties.first_child_found_in("w:tblInd")
    if table_indent is None:
        table_indent = OxmlElement("w:tblInd")
        table_properties.append(table_indent)
    table_indent.set(qn("w:type"), "dxa")
    table_indent.set(qn("w:w"), "0")

    for column, width in zip(table.columns, widths_mm):
        column.width = Mm(width)
    for row in table.rows:
        for cell, width in zip(row.cells, widths_mm):
            cell.width = Mm(width)


def _disable_document_grid(section) -> None:
    """Prevent Word's East Asian document grid from inflating compact lines."""
    section_properties = section._sectPr
    document_grid = section_properties.find(qn("w:docGrid"))
    if document_grid is not None:
        section_properties.remove(document_grid)


def _set_font(run, size: float, bold: bool = False, color: str = "212529", fonts: dict | None = None) -> None:
    font_spec = fonts or DEFAULT_FONT_SPEC
    latin_font = font_spec["latinFont"]
    east_asia_font = font_spec["eastAsiaFont"]
    run.font.name = latin_font
    r_fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for script in ("ascii", "hAnsi", "cs"):
        r_fonts.set(qn(f"w:{script}"), latin_font)
    r_fonts.set(qn("w:eastAsia"), east_asia_font)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def _add_markdown_runs(paragraph, text: object, size: float, color: str = "212529", fonts: dict | None = None) -> None:
    value = str(text or "").strip()
    parts = re.split(r"(\*\*.*?\*\*)", value)
    for part in parts:
        if not part:
            continue
        bold = part.startswith("**") and part.endswith("**")
        content = part[2:-2] if bold else part
        _set_font(paragraph.add_run(content), size, bold=bold, color=color, fonts=fonts)


def _paragraph_spacing(paragraph, *, before=0, after=0, line=1.15) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line


def _two_column_line(
    document,
    left: str,
    right: str,
    font_size: float,
    *,
    bold_left=True,
    right_font_size: float | None = None,
    right_color: str = "4B5563",
    fonts: dict | None = None,
    left_runs: list[tuple[str, float, bool]] | None = None,
) -> None:
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
    if left_runs:
        for text, run_size, run_bold in left_runs:
            if text:
                _set_font(left_p.add_run(text), run_size, bold=run_bold, fonts=fonts)
    else:
        _set_font(left_p.add_run(left), font_size, bold=bold_left, fonts=fonts)
    right_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_font(right_p.add_run(right), right_font_size or font_size, color=right_color, fonts=fonts)


def _date_range(item: dict) -> str:
    values = item.get("date_range") or []
    if isinstance(values, list) and values:
        return " - ".join(str(value) for value in values[:2] if value)
    return " - ".join(value for value in (item.get("start_date", ""), item.get("end_date", "")) if value)


def _set_hanging_indent(paragraph, *, left: float = 5.5, hanging: float = 5.5) -> None:
    """Keep wrapped list lines aligned with the text instead of the marker."""
    paragraph.paragraph_format.left_indent = Mm(left)
    paragraph.paragraph_format.first_line_indent = Mm(-hanging)


def _bullet(
    document,
    text: object,
    font_size: float,
    *,
    exact_line_height: float | None = None,
    after: float = 1.5,
    fonts: dict | None = None,
) -> None:
    value = str(text)
    line_spacing = Pt(exact_line_height) if exact_line_height is not None else 1.12
    if re.match(r"^\s*(?:[（(]?\d{1,2}[）).、．]|[一二三四五六七八九十]+[、.．])\s*", value):
        paragraph = document.add_paragraph()
        _paragraph_spacing(paragraph, after=after, line=line_spacing)
        _set_hanging_indent(paragraph)
        _add_markdown_runs(paragraph, value, font_size, fonts=fonts)
        return
    paragraph = document.add_paragraph(style="List Bullet")
    _paragraph_spacing(paragraph, after=after, line=line_spacing)
    _set_hanging_indent(paragraph, left=4.5, hanging=3)
    _add_markdown_runs(paragraph, value.lstrip("• "), font_size, fonts=fonts)


def generate_docx(
    resume_data: dict,
    style: dict | None = None,
    photo: str | None = None,
    lang: str = "zh",
    layout_config: dict | None = None,
) -> bytes:
    """Return an editable DOCX that follows the controlled layout configuration."""
    from .layout import apply_page_mode_defaults
    from .layout_config import normalize_layout_config, resolve_layout_tokens

    data = normalize_resume_data(resume_data)
    labels = LABELS.get(lang, LABELS["zh"])
    colon = "：" if lang == "zh" else ": "
    layout = normalize_layout_config(layout_config)
    global_layout = layout["global"]
    style = apply_page_mode_defaults(style)
    tokens = resolve_layout_tokens(layout, style)
    font_spec = {
        "latinFont": tokens["latinFont"],
        "eastAsiaFont": tokens["eastAsiaFont"],
    }
    # Word stores font sizes in half-point units. The shared layout resolver
    # already defines a compact semantic scale, so each export role uses the
    # same physical size as the browser and PDF renderers.
    body_font_size = round(tokens["bodyFontSizePt"] * 2) / 2
    meta_font_size = round(tokens["metaFontSizePt"] * 2) / 2
    entry_title_font_size = round(tokens["entryTitleFontSizePt"] * 2) / 2
    section_title_font_size = round(tokens["sectionTitleFontSizePt"] * 2) / 2
    name_font_size = round(tokens["nameFontSizePt"] * 2) / 2
    body_bold = tokens["bodyFontWeight"] >= 600
    meta_bold = tokens["metaFontWeight"] >= 600
    entry_title_bold = tokens["entryTitleFontWeight"] >= 600
    section_title_bold = tokens["sectionTitleFontWeight"] >= 600
    name_bold = tokens["nameFontWeight"] >= 600
    label_bold = tokens["labelFontWeight"] >= 600

    def entry_heading_runs(primary: str, secondary: str = "") -> list[tuple[str, float, bool]]:
        """Map one entry heading to the shared title/meta typography roles."""
        return [
            (primary, entry_title_font_size, entry_title_bold),
            (f" · {secondary}" if primary and secondary else secondary, meta_font_size, meta_bold),
        ]

    body_line_height = body_font_size * tokens["lineHeight"]
    module_spacing = tokens["moduleSpacingPt"]
    page_break_before = style.get("pageBreakBefore", "")
    hidden_sections = set(global_layout["hiddenSections"])

    document = Document()
    section = document.sections[0]
    section.start_type = WD_SECTION.NEW_PAGE
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = Mm(tokens["marginTopMm"])
    section.bottom_margin = Mm(tokens["marginBottomMm"])
    section.left_margin = Mm(tokens["marginLeftMm"])
    section.right_margin = Mm(tokens["marginRightMm"])
    _disable_document_grid(section)

    normal = document.styles["Normal"]
    normal.font.name = font_spec["latinFont"]
    normal_fonts = normal._element.get_or_add_rPr().get_or_add_rFonts()
    for script in ("ascii", "hAnsi", "cs"):
        normal_fonts.set(qn(f"w:{script}"), font_spec["latinFont"])
    normal_fonts.set(qn("w:eastAsia"), font_spec["eastAsiaFont"])
    normal.font.size = Pt(body_font_size)
    normal.font.bold = body_bold
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = Pt(body_line_height)
    normal.paragraph_format.widow_control = False

    def title(section_id: str, fallback: str) -> None:
        text = global_layout.get("titleOverrides", {}).get(section_id, {}).get(lang, fallback)
        paragraph = document.add_paragraph()
        _paragraph_spacing(paragraph, before=module_spacing, after=tokens["sectionTitleAfterPt"], line=1)
        _set_font(paragraph.add_run(text), section_title_font_size, bold=section_title_bold, fonts=font_spec)
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
                _paragraph_spacing(paragraph, after=tokens["paragraphSpacingPt"], line=Pt(body_line_height))
                _add_markdown_runs(paragraph, detail, body_font_size, fonts=font_spec)
            else:
                _bullet(document, detail, body_font_size, exact_line_height=body_line_height, after=tokens["paragraphSpacingPt"], fonts=font_spec)

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
    if basics_layout["preset"] == "left-aligned":
        # A left-aligned heading must not be placed in the 25 mm spacer cell.
        # Use the full available row when there is no photo, otherwise reserve
        # only the right-hand photo column.
        content_cell = header.cell(0, 0).merge(header.cell(0, 1))
        if not show_photo:
            content_cell = content_cell.merge(header.cell(0, 2))
    else:
        content_cell = header.cell(0, 1) if show_photo else header.cell(0, 0).merge(header.cell(0, 2))
    alignment = WD_ALIGN_PARAGRAPH.LEFT if basics_layout["preset"] == "left-aligned" else WD_ALIGN_PARAGRAPH.CENTER
    name_p = content_cell.paragraphs[0]
    name_p.alignment = alignment
    _paragraph_spacing(name_p, after=tokens["headerNameAfterPt"], line=1)
    _set_font(name_p.add_run(basics.get("name") or labels["nameNotSet"]), name_font_size, bold=name_bold, fonts=font_spec)
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
                _set_font(p.add_run(value), meta_font_size, color="333333", fonts=font_spec)
        else:
            p = content_cell.add_paragraph()
            p.alignment = alignment
            _set_font(p.add_run(" | ".join(contact_values)), meta_font_size, color="333333", fonts=font_spec)
    if basics.get("target_position") and "target_position" not in hidden_basics:
        p = content_cell.add_paragraph()
        p.alignment = alignment
        _set_font(p.add_run(f'{labels["targetPosition"]}{colon}{basics["target_position"]}'), meta_font_size, bold=label_bold, fonts=font_spec)
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
                education_widths = (44.0, 45.0, 53.0, 42.0)
                _set_fixed_table_widths(table, education_widths)
                for cell_index, cell in enumerate(table.rows[0].cells):
                    _set_cell_borderless(cell)
                    _set_cell_margins(cell, end=80 if cell_index == 3 else 0)
                values = [school, degree, " · ".join(metrics), date]
                cell_sizes = (entry_title_font_size, meta_font_size, meta_font_size, meta_font_size)
                for cell_index, (cell, value, cell_size) in enumerate(zip(table.rows[0].cells, values, cell_sizes)):
                    p = cell.paragraphs[0]
                    _paragraph_spacing(p, after=0, line=Pt(body_line_height))
                    if cell_index == 0:
                        _set_font(p.add_run(school), entry_title_font_size, bold=entry_title_bold, fonts=font_spec)
                        if tag_text:
                            _set_font(p.add_run(f" · {tag_text}"), meta_font_size, bold=meta_bold, fonts=font_spec)
                    else:
                        _set_font(p.add_run(value), cell_size, bold=meta_bold, fonts=font_spec)
                table.cell(0, 3).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            else:
                _two_column_line(
                    document, school, date, entry_title_font_size,
                    right_font_size=meta_font_size, right_color="111111", fonts=font_spec,
                    left_runs=entry_heading_runs(school, tag_text),
                )
                if degree:
                    p = document.add_paragraph()
                    _paragraph_spacing(p, after=0, line=Pt(body_line_height))
                    _set_font(p.add_run(degree), meta_font_size, fonts=font_spec)
                if metrics:
                    p = document.add_paragraph()
                    _paragraph_spacing(p, after=0, line=Pt(body_line_height))
                    _set_font(p.add_run(" | ".join(metrics)), meta_font_size, color="111111", fonts=font_spec)
            if cfg["thesisDisplay"] != "hidden":
                for thesis in item.get("theses") or []:
                    if not isinstance(thesis, dict):
                        continue
                    if thesis.get("title"):
                        p = document.add_paragraph()
                        _set_font(p.add_run(f'{labels["thesis"]}{colon}{thesis["title"]}'), body_font_size, bold=label_bold, fonts=font_spec)
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
            company = item.get("company_name", "")
            position_parts = [item.get("job_title", "")]
            if cfg["showJobType"] and item.get("job_type"):
                position_parts.append(f'({item["job_type"]})')
            position = " ".join(v for v in position_parts if v)
            _two_column_line(
                document, company, _date_range(item), entry_title_font_size,
                right_font_size=meta_font_size, right_color="111111", fonts=font_spec,
                left_runs=entry_heading_runs(company, position),
            )
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
                _paragraph_spacing(paragraph, after=tokens["contentBlockSpacingPt"], line=Pt(body_line_height))
                if label:
                    _set_font(paragraph.add_run(f"{label}{colon}"), body_font_size, bold=label_bold, fonts=font_spec)
                _add_markdown_runs(paragraph, block.get("text", ""), body_font_size, fonts=font_spec)
                continue
            if label:
                paragraph = document.add_paragraph()
                _paragraph_spacing(paragraph, after=tokens["contentLabelSpacingPt"], line=Pt(body_line_height))
                _set_font(paragraph.add_run(f"{label}{colon}"), body_font_size, bold=label_bold, fonts=font_spec)
            for detail_index, detail in enumerate(block.get("items") or [], 1):
                if block_type == "numbered_list":
                    paragraph = document.add_paragraph()
                    _paragraph_spacing(paragraph, after=tokens["numberedItemSpacingPt"], line=Pt(body_line_height))
                    _set_hanging_indent(paragraph)
                    _set_font(paragraph.add_run(f"({detail_index}) "), body_font_size, fonts=font_spec)
                    _add_markdown_runs(paragraph, detail, body_font_size, fonts=font_spec)
                else:
                    _bullet(document, detail, body_font_size, exact_line_height=body_line_height, after=tokens["paragraphSpacingPt"], fonts=font_spec)

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
            project_name = item.get("project_name") or item.get("name") or labels["projectNotSet"]
            role = item.get("role") if cfg["showRole"] else ""
            date = _date_range(item) if cfg["showDate"] else ""
            _two_column_line(
                document, project_name, date, entry_title_font_size,
                right_font_size=meta_font_size, right_color="111111", fonts=font_spec,
                left_runs=entry_heading_runs(project_name, role if cfg["preset"] == "compact" else ""),
            )
            if cfg["preset"] != "compact" and role:
                p = document.add_paragraph()
                _paragraph_spacing(p, after=0, line=Pt(body_line_height))
                _set_font(p.add_run(role), meta_font_size, fonts=font_spec)
            add_content_blocks(item)

    def render_skills() -> None:
        skills = (data.get("others") or {}).get("skills") or []
        if not skills or "skills" in hidden_sections:
            return
        title("skills", labels["skills"])
        for value in skills:
            _bullet(document, value, body_font_size, exact_line_height=body_line_height, after=tokens["paragraphSpacingPt"], fonts=font_spec)

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
            _set_font(p.add_run(f'{field_labels[key]}{colon}'), body_font_size, bold=label_bold, fonts=font_spec)
            content = separator.join(str(value) for value in values[key])
            if cfg["preset"] == "tags":
                content = "  ".join(f"[{value}]" for value in values[key])
            _add_markdown_runs(p, content, body_font_size, fonts=font_spec)

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
                _bullet(document, value, body_font_size, exact_line_height=body_line_height, after=tokens["paragraphSpacingPt"], fonts=font_spec)
            else:
                p = document.add_paragraph()
                _add_markdown_runs(p, value, body_font_size, fonts=font_spec)

    def render_plain_section(section_id: str, fallback: str, values: list) -> None:
        if not values or section_id in hidden_sections:
            return
        maybe_break(section_id)
        title(section_id, fallback)
        for value in values:
            _bullet(document, value, body_font_size, exact_line_height=body_line_height, after=tokens["paragraphSpacingPt"], fonts=font_spec)

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
                _bullet(document, value, body_font_size, exact_line_height=body_line_height, after=tokens["paragraphSpacingPt"], fonts=font_spec)

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
