import unittest
from io import BytesIO
from zipfile import ZipFile
from docx import Document

from backend.layout import (
    apply_page_mode_defaults,
    enforce_page_limit,
    normalize_page_break,
    normalize_page_mode,
    normalize_source_page_count,
    page_limit,
)
from backend.docx_generator import generate_docx
from backend.pdf_generator import render_resume_to_html
from backend.layout_config import LAYOUT_TEMPLATES, apply_layout_template, default_layout_config, normalize_layout_config, resolve_layout_tokens


def resume_with_two_jobs():
    return {
        "basics": {"name": "测试", "gender": "", "phone": "", "email": "", "target_position": ""},
        "education": [],
        "work_experience": [
            {"company_name": "甲", "job_title": "开发", "date_range": ["2024", "2025"], "job_type": "", "details": ["内容"]},
            {"company_name": "乙", "job_title": "开发", "date_range": ["2025", "至今"], "job_type": "", "details": ["内容"]},
        ],
        "project_experience": [],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }


class LayoutRuleTests(unittest.TestCase):
    def test_v1_default_layout_migrates_to_compact_high_density_defaults(self):
        layout = normalize_layout_config({
            "version": 1,
            "global": {
                "fontSize": 11, "lineHeight": 1.6, "moduleMargin": 1,
                "marginVertical": 9,
                "sectionOrder": ["education", "project_experience", "others"],
            },
        })
        self.assertEqual(layout["version"], 4)
        self.assertEqual(layout["global"]["fontSize"], 9)
        self.assertEqual(layout["global"]["lineHeight"], 1.28)
        self.assertIn("skills", layout["global"]["sectionOrder"])

    def test_legacy_page_modes_are_normalized_to_automatic(self):
        self.assertEqual(normalize_page_mode("three"), "auto")
        self.assertEqual(normalize_page_mode("one"), "auto")
        self.assertEqual(normalize_page_mode("two"), "auto")
        self.assertEqual(page_limit("one"), 2)
        self.assertEqual(page_limit("two"), 2)
        self.assertEqual(page_limit("auto"), 2)

    def test_layout_keeps_user_spacing_and_normalizes_source_metadata(self):
        style = apply_page_mode_defaults({
            "pageMode": "one", "fontSize": 12, "lineHeight": 1.8,
            "moduleMargin": 1.5, "marginTop": 10, "marginBottom": 10,
            "sourcePageCount": "2", "pageBreakBefore": "work_experience:1",
        })
        self.assertEqual(style["pageMode"], "auto")
        self.assertEqual(style["fontSize"], 12)
        self.assertEqual(style["lineHeight"], 1.8)
        self.assertEqual(style["sourcePageCount"], 2)
        self.assertEqual(style["pageBreakBefore"], "work_experience:1")

    def test_invalid_page_metadata_is_safely_ignored(self):
        self.assertEqual(normalize_source_page_count("bad"), 1)
        self.assertEqual(normalize_page_break("../../bad"), "")
        self.assertEqual(normalize_page_break("education:0"), "education:0")

    def test_three_page_export_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "超出两页"):
            enforce_page_limit("auto", 3)
        enforce_page_limit("one", 2)

    def test_pdf_and_word_apply_the_same_semantic_break_anchor(self):
        style = {"pageBreakBefore": "work_experience:1"}
        html = render_resume_to_html(resume_with_two_jobs(), style)
        self.assertIn('class="work-item page-break-before"', html)

        docx = generate_docx(resume_with_two_jobs(), style)
        with ZipFile(BytesIO(docx)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn('w:type="page"', document_xml)

    def test_pdf_applies_controlled_layout_presets(self):
        data = resume_with_two_jobs()
        data["education"] = [{
            "school_name": "示例大学", "school_tags": ["211"], "degree": "本科",
            "major": "计算机", "date_range": ["2020", "2024"],
            "gpa": "3.8", "gpa_scale": "4.0", "theses": [],
        }]
        layout = default_layout_config()
        layout["basics"]["preset"] = "left-aligned"
        layout["education"]["preset"] = "three-column"
        layout["education"]["schoolTagStyle"] = "text"
        layout["work_experience"]["detailsStyle"] = "paragraph"
        layout["global"]["titleStyle"] = "plain"
        html = render_resume_to_html(data, layout_config=layout)
        self.assertIn("basics-left-aligned", html)
        self.assertIn("preset-three-column", html)
        header_start = html.index('<div class="education-header">')
        header_end = html.index('</div>', html.index('<div class="graduation-date">', header_start))
        self.assertIn('<div class="education-degree-column">', html[header_start:header_end])
        self.assertIn('education-metrics-column academic-metrics', html[header_start:header_end])
        self.assertIn('GPA：3.8/4.0', html[header_start:header_end])
        self.assertIn("tag-text", html)
        self.assertIn("details-paragraph", html)
        self.assertIn("title-plain", html)
        self.assertIn("border-bottom: 1px solid #333333", html)

        with ZipFile(BytesIO(generate_docx(data, layout_config=layout))) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn('w:color="333333"', document_xml)

    def test_all_templates_keep_dates_right_aligned_and_work_heading_on_one_row(self):
        data = resume_with_two_jobs()
        data["work_experience"][0].update({"company_name": "示例科技", "job_title": "机器人算法工程师", "job_type": "实习"})
        data["project_experience"] = [{
            "project_name": "协作臂轨迹跟踪系统",
            "role": "",
            "date_range": ["2026.01", "至今"],
            "details": [],
        }]

        for template_id in LAYOUT_TEMPLATES:
            layout = apply_layout_template({}, template_id)
            tokens = resolve_layout_tokens(layout)
            html = render_resume_to_html(data, layout_config=layout)
            self.assertIn('class="work-item preset-', html, template_id)
            self.assertIn('date-right', html, template_id)
            self.assertIn('.project-item.date-right .project-header', html, template_id)
            self.assertIn('grid-template-columns: minmax(0, 1fr) auto', html, template_id)
            self.assertIn('page-break-inside: avoid', html, template_id)
            work_start = html.index('<div class="work-main">')
            work_end = html.index('</div>', html.index('class="work-period"', work_start))
            work_fragment = html[work_start:work_end]
            self.assertIn('示例科技', work_fragment, template_id)
            self.assertIn('机器人算法工程师', work_fragment, template_id)
            self.assertIn('(实习)', work_fragment, template_id)
            self.assertIn('--meta-font-weight: 400;', html, template_id)
            self.assertIn('--entry-title-font-weight: 700;', html, template_id)
            self.assertIn('font-weight: var(--entry-title-font-weight)', html, template_id)
            self.assertIn('font-weight: var(--meta-font-weight)', html, template_id)

            document = Document(BytesIO(generate_docx(data, layout_config=layout)))
            heading_table = next(
                table for table in document.tables
                if any("示例科技" in cell.text for row in table.rows for cell in row.cells)
            )
            heading_cell, date_cell = heading_table.rows[0].cells
            self.assertIn("示例科技 · 机器人算法工程师 (实习)", heading_cell.text, template_id)
            self.assertEqual(heading_cell.paragraphs[0].runs[0].text, "示例科技", template_id)
            self.assertTrue(heading_cell.paragraphs[0].runs[0].bold, template_id)
            self.assertAlmostEqual(heading_cell.paragraphs[0].runs[0].font.size.pt, tokens["entryTitleFontSizePt"], places=1)
            self.assertEqual(heading_cell.paragraphs[0].runs[1].text, " · 机器人算法工程师 (实习)", template_id)
            self.assertFalse(bool(heading_cell.paragraphs[0].runs[1].bold), template_id)
            self.assertAlmostEqual(heading_cell.paragraphs[0].runs[1].font.size.pt, tokens["metaFontSizePt"], places=1)
            self.assertFalse(bool(date_cell.paragraphs[0].runs[0].bold), template_id)
            self.assertAlmostEqual(date_cell.paragraphs[0].runs[0].font.size.pt, tokens["metaFontSizePt"], places=1)

    def test_empty_self_evaluation_is_hidden_for_every_template(self):
        from backend.layout_config import LAYOUT_TEMPLATES, apply_layout_template

        data = resume_with_two_jobs()
        data["self_evaluation"] = ["", "   "]
        for template_id in LAYOUT_TEMPLATES:
            html = render_resume_to_html(data, layout_config=apply_layout_template({}, template_id))
            self.assertNotIn('<section class="section self-evaluation', html, template_id)

    def test_word_applies_section_order_and_hidden_sections(self):
        data = resume_with_two_jobs()
        data["project_experience"] = [{
            "project_name": "先展示项目", "role": "开发", "date_range": [], "details": []
        }]
        data["self_evaluation"] = ["不应出现"]
        layout = default_layout_config()
        layout["global"]["sectionOrder"] = [
            "project_experience", "work_experience", "education", "others", "self_evaluation"
        ]
        layout["global"]["hiddenSections"] = ["self_evaluation"]
        document = Document(BytesIO(generate_docx(data, layout_config=layout)))
        combined = "\n".join(
            [paragraph.text for paragraph in document.paragraphs]
            + [cell.text for table in document.tables for row in table.rows for cell in row.cells]
        )
        self.assertNotIn("不应出现", combined)
        with ZipFile(BytesIO(generate_docx(data, layout_config=layout))) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        self.assertLess(xml.index("先展示项目"), xml.index("甲"))


    def test_pdf_and_word_render_lossless_import_fields(self):
        data = resume_with_two_jobs()
        data["basics"]["birth_date"] = "2002.06"
        data["research_interests"] = ["协作臂模型预测阻抗控制"]
        data["honors"] = ["研究生二等奖学金"]
        data["custom_sections"] = [{"title": "校园经历", "items": ["学生组织负责人"]}]

        html = render_resume_to_html(data)

        self.assertIn("出生年月：2002.06", html)
        self.assertIn("协作臂模型预测阻抗控制", html)
        self.assertIn("研究生二等奖学金", html)
        self.assertIn("校园经历", html)
        self.assertIn("display: block", html)
        self.assertLess(html.index("协作臂模型预测阻抗控制"), html.index("研究生二等奖学金"))

        document = Document(BytesIO(generate_docx(data)))
        combined = "\n".join(
            [paragraph.text for paragraph in document.paragraphs]
            + [cell.text for table in document.tables for row in table.rows for cell in row.cells]
        )
        for expected in ("2002.06", "协作臂模型预测阻抗控制", "研究生二等奖学金", "校园经历", "学生组织负责人"):
            self.assertIn(expected, combined)

    def test_project_semantic_blocks_have_no_outer_bullets_or_role_placeholder(self):
        data = resume_with_two_jobs()
        data["project_experience"] = [{
            "project_name": "机器人控制",
            "role": "",
            "date_range": ["2025.01", "2025.06"],
            "details": ["项目简介：面向展厅导航", "项目职责：", "（1）训练策略", "（2）验证性能"],
        }]
        data["others"]["skills"] = ["ROS2", "Python"]

        html = render_resume_to_html(data)

        self.assertIn("<strong>项目简介：</strong>面向展厅导航", html)
        self.assertIn('<ol class="project-numbered-list">', html)
        self.assertNotIn("（1）训练策略", html)
        self.assertNotIn(">角色<", html)
        self.assertIn("专业技能", html)
        self.assertLess(html.index("专业技能"), html.index("项目经历"))
        self.assertIn("body, .degree-major", html)

    def test_numbered_skill_keeps_its_number_without_an_outer_bullet(self):
        data = resume_with_two_jobs()
        data["others"]["skills"] = ["1. Python 与 FastAPI", "沟通协作"]

        html = render_resume_to_html(data)

        self.assertIn('<li class="list-item native-marker">1. Python 与 FastAPI</li>', html)
        self.assertIn('<li class="list-item">沟通协作</li>', html)
        self.assertIn('.list-item.native-marker::before { content: none; }', html)

        document = Document(BytesIO(generate_docx(data)))
        numbered = next(paragraph for paragraph in document.paragraphs if "1. Python" in paragraph.text)
        plain = next(paragraph for paragraph in document.paragraphs if "沟通协作" in paragraph.text)
        self.assertNotEqual(numbered.style.name, "List Bullet")
        self.assertEqual(plain.style.name, "List Bullet")
        self.assertGreater(numbered.paragraph_format.left_indent.mm, 0)
        self.assertLess(numbered.paragraph_format.first_line_indent.mm, 0)
        self.assertGreater(plain.paragraph_format.left_indent.mm, 0)
        self.assertLess(plain.paragraph_format.first_line_indent.mm, 0)

    def test_word_numbered_semantic_blocks_use_real_hanging_indent(self):
        data = resume_with_two_jobs()
        data["project_experience"] = [{
            "project_name": "Robot control",
            "date_range": ["2025.01", "2025.06"],
            "content_blocks": [{
                "type": "numbered_list",
                "label": "Responsibilities",
                "items": ["A deliberately long responsibility that wraps onto another visual line in Word."],
            }],
        }]

        document = Document(BytesIO(generate_docx(data)))
        numbered = next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("(1) "))

        self.assertGreater(numbered.paragraph_format.left_indent.mm, 0)
        self.assertLess(numbered.paragraph_format.first_line_indent.mm, 0)

    def test_word_contact_details_use_dark_gray(self):
        data = resume_with_two_jobs()
        data["basics"].update({"birth_date": "2002.06", "phone": "17622312238", "email": "user@example.com"})

        document = Document(BytesIO(generate_docx(data)))
        contact_run = next(
            run
            for table in document.tables
            for row in table.rows
            for cell in row.cells
            for paragraph in cell.paragraphs
            for run in paragraph.runs
            if "user@example.com" in run.text
        )

        self.assertEqual(str(contact_run.font.color.rgb), "333333")

    def test_word_uses_the_same_body_type_scale_as_pdf_preview(self):
        data = resume_with_two_jobs()
        data["others"]["skills"] = ["Python 与 FastAPI"]
        layout = default_layout_config()
        layout["global"]["fontSize"] = 10.5

        document = Document(BytesIO(generate_docx(data, layout_config=layout)))
        body_paragraph = next(paragraph for paragraph in document.paragraphs if "Python" in paragraph.text)

        self.assertAlmostEqual(body_paragraph.runs[-1].font.size.pt, 10.5, places=2)

    def test_word_left_aligned_header_uses_full_row_when_photo_is_absent(self):
        data = resume_with_two_jobs()
        data["basics"].update({
            "birth_date": "2002.06",
            "phone": "17622312238",
            "email": "2776553477@qq.com",
        })
        layout = default_layout_config()
        layout["basics"]["preset"] = "left-aligned"

        with ZipFile(BytesIO(generate_docx(data, layout_config=layout))) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn('<w:gridSpan w:val="3"', document_xml)
        self.assertNotIn("<w:docGrid", document_xml)

    def test_one_line_education_layout_allows_long_columns_to_wrap_in_bounds(self):
        html = render_resume_to_html(resume_with_two_jobs())

        self.assertIn("overflow-wrap: break-word", html)
        self.assertIn("flex: 1 1 0", html)
        self.assertIn("flex: 0 0 36mm", html)
        self.assertIn("margin-right: 2mm", html)
        self.assertIn("position: static", html)
        self.assertNotIn("right: 6mm", html)

    def test_word_one_line_education_has_fixed_width_and_right_safety_padding(self):
        data = resume_with_two_jobs()
        data["education"] = [{
            "school_name": "暨南大学",
            "degree": "硕士",
            "major": "电子信息",
            "date_range": ["2024.09", "2027.06"],
        }]
        layout = default_layout_config()
        layout["education"]["preset"] = "compact"

        with ZipFile(BytesIO(generate_docx(data, layout_config=layout))) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn('<w:tblLayout w:type="fixed"', document_xml)
        self.assertIn('<w:tblW w:type="dxa" w:w="10431"', document_xml)
        self.assertIn('<w:end w:w="80" w:type="dxa"', document_xml)


if __name__ == "__main__":
    unittest.main()
