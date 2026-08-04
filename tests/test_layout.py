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
from backend.layout_config import default_layout_config


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


if __name__ == "__main__":
    unittest.main()
