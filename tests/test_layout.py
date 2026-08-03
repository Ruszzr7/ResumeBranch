import unittest
from io import BytesIO
from zipfile import ZipFile

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


if __name__ == "__main__":
    unittest.main()
