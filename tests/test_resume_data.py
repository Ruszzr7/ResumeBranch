import unittest

from backend.resume_data import normalize_resume_data
from backend.resume_agent import normalize_and_validate_resume


class ResumeDataNormalizationTests(unittest.TestCase):
    def test_migrates_gpa_from_legacy_thesis(self):
        source = {
            "education": [
                {
                    "school_name": "示例大学",
                    "theses": [
                        {"title": "GPA", "details": ["3.72/4.0"]},
                        {"title": "真实论文", "details": ["研究内容"]},
                    ],
                }
            ]
        }

        result = normalize_resume_data(source)
        education = result["education"][0]

        self.assertEqual(education["gpa"], "3.72")
        self.assertEqual(education["gpa_scale"], "4.0")
        self.assertEqual(education["theses"], [{"title": "真实论文", "details": ["研究内容"]}])
        self.assertNotIn("gpa", source["education"][0])

    def test_preserves_real_thesis_mentioning_gpa(self):
        source = {
            "education": [
                {
                    "theses": [
                        {"title": "基于 GPA 数据的学生表现研究", "details": []},
                    ]
                }
            ]
        }

        result = normalize_resume_data(source)

        self.assertEqual(result["education"][0]["gpa"], "")
        self.assertEqual(len(result["education"][0]["theses"]), 1)

    def test_normalizes_alias_and_combined_scale(self):
        source = {"education": [{"GPA": "3.8/4.0", "专业排名": "前 10%"}]}

        result = normalize_resume_data(source)["education"][0]

        self.assertEqual(result["gpa"], "3.8")
        self.assertEqual(result["gpa_scale"], "4.0")
        self.assertEqual(result["ranking"], "前 10%")
        self.assertNotIn("GPA", result)

    def test_migrates_chinese_gpa_with_full_score_phrase(self):
        source = {
            "education": [
                {"theses": [{"title": "平均绩点", "details": ["3.7（满分4.0）"]}]}
            ]
        }

        result = normalize_resume_data(source)["education"][0]

        self.assertEqual(result["gpa"], "3.7")
        self.assertEqual(result["gpa_scale"], "4.0")
        self.assertEqual(result["theses"], [])


    def test_preserves_new_and_unknown_sections(self):
        source = {
            "basics": {"name": "李靖华", "date_of_birth": "2002.06"},
            "research_directions": ["机器人控制", "强化学习"],
            "awards": ["研究生二等奖学金"],
            "志愿服务": ["校级志愿服务队成员"],
        }

        result = normalize_and_validate_resume(source)

        self.assertEqual(result["basics"]["birth_date"], "2002.06")
        self.assertEqual(result["research_interests"], ["机器人控制", "强化学习"])
        self.assertEqual(result["honors"], ["研究生二等奖学金"])
        self.assertEqual(result["custom_sections"], [{"title": "志愿服务", "items": ["校级志愿服务队成员"]}])

    def test_splits_numbered_responsibilities_without_rewriting(self):
        source = {
            "basics": {"name": "测试"},
            "work_experience": [{
                "company": "示例公司",
                "position": "实习生",
                "time": "2025.01 - 2025.06",
                "content": ["项目职责：（1）完成模块A；（2）完成模块B；（3）验证模块C"],
            }],
        }

        result = normalize_and_validate_resume(source)
        work = result["work_experience"][0]
        details = work["details"]

        self.assertEqual(details, ["项目职责：", "（1）完成模块A", "（2）完成模块B", "（3）验证模块C"])
        self.assertEqual(work["date_range"], ["2025.01", "2025.06"])
        self.assertEqual(work["content_blocks"][0]["type"], "numbered_list")
        self.assertEqual(work["content_blocks"][0]["label"], "项目职责")
        self.assertEqual(work["content_blocks"][0]["items"], ["完成模块A", "完成模块B", "验证模块C"])

    def test_migrates_project_details_into_semantic_blocks(self):
        source = {
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "机器人项目",
                "role": "",
                "details": [
                    "项目简介：面向展厅导航场景",
                    "项目职责：",
                    "（1）完成轨迹训练",
                    "（2）验证控制策略",
                ],
            }],
        }

        project = normalize_resume_data(source)["project_experience"][0]

        self.assertEqual(project["role"], "")
        self.assertEqual(project["content_blocks"][0], {
            "type": "paragraph", "label": "项目简介", "label_bold": True,
            "text": "面向展厅导航场景", "items": [],
        })
        self.assertEqual(project["content_blocks"][1]["type"], "numbered_list")
        self.assertEqual(project["content_blocks"][1]["items"], ["完成轨迹训练", "验证控制策略"])

    def test_promotes_common_skill_custom_section(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "others": {"skills": ["Python"]},
            "custom_sections": [
                {"title": "专业技能", "items": ["ROS2", "Python"]},
                {"title": "校园经历", "items": ["学生干部"]},
            ],
        })

        self.assertEqual(result["others"]["skills"], ["Python", "ROS2"])
        self.assertEqual(result["custom_sections"], [{"title": "校园经历", "items": ["学生干部"]}])

    def test_keeps_language_inside_original_skills_module(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "others": {
                "skills": ["5. 仿真、强化学习与英语：Isaac Sim、PyTorch"],
                "certificates": [],
                "languages": ["英语 CET-4"],
            },
        })

        self.assertEqual(result["others"]["languages"], [])
        self.assertEqual(result["others"]["skills"], [
            "5. 仿真、强化学习与英语：Isaac Sim、PyTorch",
            "英语 CET-4",
        ])

    def test_parser_metadata_never_becomes_a_resume_module(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "parsing_status": "completed",
            "custom_sections": [
                {"title": "parsing_status", "items": ["completed"]},
                {"title": "校园经历", "items": ["学生会"]},
            ],
        })

        self.assertNotIn("parsing_status", result)
        self.assertEqual(result["custom_sections"], [{"title": "校园经历", "items": ["学生会"]}])


if __name__ == "__main__":
    unittest.main()
