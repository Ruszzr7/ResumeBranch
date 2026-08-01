import unittest
from io import BytesIO

from docx import Document

from backend.docx_generator import generate_docx
from backend.llm_providers import public_registry, temperature_supported, validate_profile


class DocxGeneratorTests(unittest.TestCase):
    def test_generates_editable_resume_with_academic_metrics(self):
        content = generate_docx({
            "basics": {"name": "测试用户", "target_position": "产品经理"},
            "education": [{
                "school_name": "示例大学",
                "degree": "本科",
                "major": "计算机科学",
                "gpa": "3.72",
                "gpa_scale": "4.0",
                "ranking": "前 10%",
            }],
            "work_experience": [],
            "project_experience": [],
            "others": {},
            "self_evaluation": [],
        })

        document = Document(BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        table_text = "\n".join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
        combined = text + "\n" + table_text
        self.assertIn("测试用户", combined)
        self.assertIn("示例大学", combined)
        self.assertIn("GPA：3.72/4.0", combined)
        self.assertAlmostEqual(document.sections[0].page_width.mm, 210.0, places=1)


class ProviderRulesTests(unittest.TestCase):
    def test_public_provider_registry_does_not_publish_stale_models_or_urls(self):
        for provider in public_registry():
            self.assertNotIn("models", provider)
            self.assertNotIn("default_model", provider)
            self.assertNotIn("base_url", provider)

    def test_model_specific_temperature_rules(self):
        self.assertFalse(temperature_supported("kimi_coding", "k3"))
        self.assertFalse(temperature_supported("openai", "gpt-5.2"))
        self.assertTrue(temperature_supported("openai", "gpt-4.1"))
        self.assertFalse(temperature_supported("deepseek", "deepseek-reasoner"))

    def test_glm_rejects_zero_temperature(self):
        with self.assertRaisesRegex(ValueError, "temperature"):
            validate_profile("glm", "glm-5.2", "https://open.bigmodel.cn/api/paas/v4/", 0.0)


if __name__ == "__main__":
    unittest.main()
