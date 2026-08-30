import unittest

from backend.import_contract import assess_import_quality, finalize_import_resume
from backend.resume_agent import normalize_and_validate_resume


class ImportContractTests(unittest.TestCase):
    def test_quality_requires_identity_and_minimum_content(self):
        weak = assess_import_quality({"basics": {"name": "张三"}})
        self.assertFalse(weak.accepted)
        self.assertIn("缺少足够", weak.warning)

        strong = assess_import_quality({
            "basics": {"name": "张三", "phone": "13800138000", "email": "a@example.com"},
            "education": [{"school_name": "测试大学", "major": "计算机"}],
            "others": {"skills": ["Python", "FastAPI"]},
            "self_evaluation": ["有后端开发经验"],
        })
        self.assertTrue(strong.accepted)
        self.assertIn("education", strong.structured_sections)

    def test_finalize_import_applies_fixed_typography_and_preserves_custom_sections(self):
        result, quality = finalize_import_resume({
            "basics": {"name": "张三", "phone": "13800138000", "email": "a@example.com"},
            "education": [{
                "school_name": "测试大学", "major": "计算机", "degree": "本科",
                "date_range": ["2020.09", "2024.06"],
            }],
            "custom_sections": [{
                "title": "荣誉、论文与语言", "items": ["一等奖学金", "论文题目", "CET-6"],
            }],
        }, normalize_and_validate_resume)

        self.assertTrue(quality.accepted)
        self.assertEqual(result["formatting_version"], 4)
        self.assertEqual(result["basics"]["name"], "**张三**")
        self.assertEqual(result["education"][0]["school_name"], "**测试大学**")
        self.assertEqual(result["custom_sections"][0]["title"], "**荣誉、论文与语言**")
        self.assertEqual(result["custom_sections"][0]["items"], ["一等奖学金", "论文题目", "CET-6"])

    def test_finalize_import_applies_fixed_weights_preserves_inline_bold_and_removes_duplicate_work_type(self):
        result, quality = finalize_import_resume({
            "basics": {
                "name": "**李靖华**",
                "target_position": "软件工程师",
                "gender": "**男**",
                "phone": "13800138000",
                "email": "a@example.com",
            },
            "education": [{
                "school_name": "中山大学",
                "degree": "**硕士**",
                "major": "**电子信息**",
                "date_range": ["**2024.09**", "2027.06"],
            }],
            "work_experience": [{
                "company_name": "广东图灵智新技术有限公司",
                "job_title": "宇树 G1 导览项目 (实习)",
                "job_type": "实习",
                "date_range": ["2024.09", "2025.02"],
                "content_blocks": [{
                    "type": "paragraph",
                    "semantic_role": "introduction",
                    "label": "项目简介",
                    "label_bold": False,
                    "text": "项目背景 **与目标**",
                }, {
                    "type": "numbered_list",
                    "semantic_role": "responsibilities",
                    "label": "项目职责",
                    "label_bold": False,
                    "items": ["**完成设计** 与验证", "**完成联调**"],
                }],
            }],
            "research_interests": ["**机器人控制** 与规划"],
            "honors": ["**一等奖学金**"],
            "publications": ["论文标题"],
            "others": {"skills": ["**Python** 与 Vue"], "certificates": [], "languages": []},
            "self_evaluation": ["**沟通能力强**"],
        }, normalize_and_validate_resume)

        self.assertTrue(quality.accepted)
        self.assertEqual(result["basics"]["target_position"], "**软件工程师**")
        self.assertEqual(result["basics"]["gender"], "男")
        self.assertEqual(result["education"][0]["degree"], "硕士")
        self.assertEqual(result["education"][0]["date_range"], ["2024.09", "2027.06"])
        work = result["work_experience"][0]
        self.assertEqual(work["company_name"], "**广东图灵智新技术有限公司**")
        self.assertEqual(work["job_title"], "**宇树 G1 导览项目**")
        self.assertEqual(work["job_type"], "实习")
        self.assertEqual(
            [block["label"] for block in work["content_blocks"]],
            ["工作简介", "工作职责"],
        )
        self.assertTrue(work["content_blocks"][0]["label_bold"])
        self.assertEqual(work["content_blocks"][0]["text"], "项目背景 **与目标**")
        self.assertEqual(work["content_blocks"][1]["items"], ["**完成设计** 与验证", "**完成联调**"])
        self.assertEqual(result["research_interests"], ["**机器人控制** 与规划"])
        self.assertEqual(result["others"]["skills"], ["**Python** 与 Vue"])

    def test_finalize_import_restores_default_labels_for_semantic_content_blocks(self):
        result, quality = finalize_import_resume({
            "basics": {"name": "张三", "phone": "13800138000", "email": "a@example.com"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [{
                    "type": "paragraph", "semantic_role": "introduction", "label": "", "text": "背景",
                }, {
                    "type": "bullet_list", "semantic_role": "responsibilities", "label": "", "items": ["完成设计"],
                }],
            }],
        }, normalize_and_validate_resume)

        self.assertTrue(quality.accepted)
        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual([block["label"] for block in blocks], ["项目简介", "项目职责"])
        self.assertEqual(blocks[1]["type"], "numbered_list")
        self.assertTrue(all(block["label_bold"] for block in blocks))

    def test_finalize_import_restores_contextual_work_labels(self):
        result, quality = finalize_import_resume({
            "basics": {"name": "张三", "phone": "13800138000", "email": "a@example.com"},
            "work_experience": [{
                "company_name": "示例公司",
                "content_blocks": [{
                    "type": "paragraph", "semantic_role": "introduction", "label": "", "text": "背景",
                }, {
                    "type": "bullet_list", "semantic_role": "responsibilities", "label": "", "items": ["完成设计"],
                }],
            }],
        }, normalize_and_validate_resume)

        self.assertTrue(quality.accepted)
        blocks = result["work_experience"][0]["content_blocks"]
        self.assertEqual([block["label"] for block in blocks], ["工作简介", "工作职责"])
        self.assertEqual(blocks[1]["type"], "numbered_list")

    def test_finalize_import_distinguishes_project_tech_stack_from_top_level_skills(self):
        result, quality = finalize_import_resume({
            "basics": {"name": "张三", "phone": "13800138000", "email": "a@example.com"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {"type": "paragraph", "semantic_role": "tech_stack", "label": "", "text": "Python、FastAPI"},
                ],
            }],
            "others": {"skills": ["Docker"]},
        }, normalize_and_validate_resume)

        self.assertTrue(quality.accepted)
        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual([block["semantic_role"] for block in blocks], ["tech_stack", "introduction"])
        self.assertEqual(blocks[0]["label"], "技术栈")
        self.assertTrue(blocks[0]["label_bold"])
        self.assertEqual(result["others"]["skills"], ["Docker"])

    def test_finalize_import_preserves_responsibility_paragraphs(self):
        result, quality = finalize_import_resume({
            "basics": {"name": "张三", "phone": "13800138000", "email": "a@example.com"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [{
                    "type": "paragraph", "semantic_role": "responsibilities", "label": "项目职责",
                    "text": "完成设计与验证", "items": [],
                }],
            }],
        }, normalize_and_validate_resume)

        self.assertTrue(quality.accepted)
        block = result["project_experience"][0]["content_blocks"][0]
        self.assertEqual(block["type"], "paragraph")
        self.assertEqual(block["text"], "完成设计与验证")
        self.assertEqual(block["items"], [])


if __name__ == "__main__":
    unittest.main()
