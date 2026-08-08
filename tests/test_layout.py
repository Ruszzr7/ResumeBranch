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
from backend.layout_config import default_layout_config, normalize_layout_config


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
        self.assertEqual(layout["version"], 2)
        self.assertEqual(layout["global"]["fontSize"], 10.5)
        self.assertEqual(layout["global"]["lineHeight"], 1.32)
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


if __name__ == "__main__":
    unittest.main()
