import unittest

from backend.resume_data import normalize_resume_data
from backend.resume_agent import normalize_and_validate_resume


class ResumeDataNormalizationTests(unittest.TestCase):
    def test_education_supplement_is_a_flat_lossless_list(self):
        result = normalize_resume_data({
            "education_supplement": ["**论文标题**", {"text": "校级奖励"}, ""],
            "education": [],
        })
        self.assertEqual(result["education_supplement"], ["**论文标题**", "校级奖励"])

    def test_publications_are_a_standalone_editable_string_list(self):
        result = normalize_resume_data({
            "publications": ["论文 A，已接收", {"text": "论文 B，返修"}],
            "education": [{"school_name": "示例大学", "theses": []}],
        })
        self.assertEqual(result["publications"], ["论文 A，已接收", "论文 B，返修"])
        self.assertEqual(result["education"][0]["theses"], [])

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

    def test_removes_retired_average_score_and_keeps_single_sided_basic_fields(self):
        result = normalize_resume_data({
            "basics": {
                "additional_fields": [
                    {"label": "籍贯", "value": ""},
                    {"label": "", "value": "广州"},
                    {"label": "", "value": ""},
                ],
            },
            "education": [{
                "average_score": "88/100", "平均分": "90", "gpa": "3.8",
                "school_tags": "211/985/双一流",
            }],
        })

        self.assertEqual(result["basics"]["additional_fields"], [
            {"label": "籍贯", "value": ""},
            {"label": "", "value": "广州"},
        ])
        self.assertNotIn("average_score", result["education"][0])
        self.assertNotIn("平均分", result["education"][0])
        self.assertEqual(result["education"][0]["school_tags"], ["211", "985", "双一流"])

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
        self.assertEqual(work["content_blocks"][0]["semantic_role"], "responsibilities")
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
            "type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "label_bold": True,
            "text": "面向展厅导航场景", "items": [],
        })
        self.assertEqual(project["content_blocks"][1]["type"], "numbered_list")
        self.assertEqual(project["content_blocks"][1]["items"], ["完成轨迹训练", "验证控制策略"])

    def test_intro_followed_by_unlabelled_lines_becomes_responsibilities(self):
        source = {
            "basics": {"name": "测试"},
            "work_experience": [{
                "company_name": "示例公司",
                "details": [
                    "项目简介：负责展厅导航系统",
                    "完成模块设计与实现",
                    "完成联调与性能验证",
                ],
            }],
            "project_experience": [{
                "project_name": "机器人项目",
                "details": [
                    "项目简介：面向复杂场景",
                    "（1）完成轨迹训练",
                    "（2）验证控制策略",
                ],
            }],
        }

        result = normalize_resume_data(source)
        for item in (result["work_experience"][0], result["project_experience"][0]):
            blocks = item["content_blocks"]
            self.assertEqual(blocks[0]["semantic_role"], "introduction")
            self.assertEqual(blocks[1]["semantic_role"], "responsibilities")
            self.assertEqual(blocks[1]["label"], "项目职责")
            self.assertEqual(blocks[1]["type"], "numbered_list")
            self.assertEqual(len(blocks[1]["items"]), 2)

    def test_explicit_content_block_aliases_and_boolean_strings_are_normalized(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [{
                    "type": "numbered",
                    "semantic_role": "responsibility",
                    "label": "项目职责",
                    "label_bold": "false",
                    "items": ["(1) 设计模块", "2. 验证模块"],
                }],
            }],
        })

        block = result["project_experience"][0]["content_blocks"][0]
        self.assertEqual(block["type"], "numbered_list")
        self.assertEqual(block["semantic_role"], "responsibilities")
        self.assertFalse(block["label_bold"])
        self.assertEqual(block["items"], ["设计模块", "验证模块"])

    def test_bold_headings_and_following_points_keep_project_responsibility_semantics(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "work_experience": [{
                "company_name": "示例公司",
                "details": [
                    "**项目简介**：**负责导航系统设计**",
                    "**完成模块实现**",
                    "完成联调验证",
                ],
            }],
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "项目背景"},
                    {"type": "bullet_list", "semantic_role": "generic", "label": "", "items": ["补充说明"]},
                ],
            }],
        })

        work_blocks = result["work_experience"][0]["content_blocks"]
        self.assertEqual(work_blocks[0]["semantic_role"], "introduction")
        self.assertEqual(work_blocks[0]["text"], "**负责导航系统设计**")
        self.assertEqual(work_blocks[1]["semantic_role"], "responsibilities")
        self.assertEqual(work_blocks[1]["items"], ["**完成模块实现**", "完成联调验证"])

        project_blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual(project_blocks[1]["semantic_role"], "generic")
        self.assertEqual(project_blocks[1]["type"], "bullet_list")
        self.assertEqual(project_blocks[1]["items"], ["补充说明"])

    def test_generic_ui_labels_after_intro_remain_separate_generic_blocks(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {"type": "bullet_list", "label": "普通工作内容", "items": ["完成设计"]},
                    {"type": "bullet_list", "label": "其他项目内容", "items": ["补充说明"]},
                ],
            }],
        })

        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual(len(blocks), 3)
        self.assertEqual([block["semantic_role"] for block in blocks], ["introduction", "generic", "generic"])
        self.assertEqual([block["type"] for block in blocks], ["paragraph", "bullet_list", "bullet_list"])
        self.assertEqual([block["label"] for block in blocks], ["项目简介", "", ""])
        self.assertEqual([block["items"] for block in blocks[1:]], [["完成设计"], ["补充说明"]])

    def test_unlabelled_content_after_explicit_intro_defaults_to_responsibilities(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {"type": "bullet_list", "items": ["职责条目一"]},
                ],
            }],
        })

        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual(blocks[1]["semantic_role"], "responsibilities")
        self.assertEqual(blocks[1]["type"], "numbered_list")
        self.assertEqual(blocks[1]["label"], "项目职责")
        self.assertEqual(blocks[1]["items"], ["职责条目一"])

    def test_unlabelled_paragraph_after_explicit_intro_becomes_one_responsibility_item(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {"type": "paragraph", "text": "职责段落"},
                ],
            }],
        })

        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual([block["semantic_role"] for block in blocks], ["introduction", "responsibilities"])
        self.assertEqual(blocks[1]["type"], "numbered_list")
        self.assertEqual(blocks[1]["label"], "项目职责")
        self.assertEqual(blocks[1]["items"], ["职责段落"])

    def test_experience_without_semantic_headings_stays_generic(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "bullet_list", "items": ["内容一", "内容二"]},
                    {"type": "paragraph", "text": "补充内容"},
                ],
            }],
        })

        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual([block["semantic_role"] for block in blocks], ["generic", "generic"])
        self.assertEqual([block["type"] for block in blocks], ["bullet_list", "paragraph"])

    def test_explicit_generic_multi_item_block_after_intro_is_not_reclassified(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {"type": "bullet_list", "semantic_role": "generic", "label": "", "items": ["补充说明一", "补充说明二"]},
                ],
            }],
        })

        block = result["project_experience"][0]["content_blocks"][1]
        self.assertEqual(block["semantic_role"], "generic")
        self.assertEqual(block["type"], "bullet_list")
        self.assertEqual(block["items"], ["补充说明一", "补充说明二"])

    def test_unknown_generic_labels_stay_inline_and_role_defaults_are_stable(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {"label": "未定义前缀", "items": ["基于 **方法** 完成"]},
                    {"semantic_role": "responsibilities", "label": "项目职责", "items": ["完成联调"]},
                    {"semantic_role": "generic", "label": "普通内容", "items": ["补充说明"]},
                ],
            }],
        })

        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual(blocks[0]["type"], "paragraph")
        self.assertEqual(blocks[1], {
            "type": "bullet_list", "semantic_role": "generic", "label": "",
            "label_bold": True, "text": "", "items": ["**未定义前缀**：基于 **方法** 完成"],
        })
        self.assertEqual(blocks[2]["type"], "numbered_list")
        self.assertEqual(blocks[3], {
            "type": "bullet_list", "semantic_role": "generic", "label": "",
            "label_bold": True, "text": "", "items": ["补充说明"],
        })

    def test_content_block_type_defaults_follow_semantic_role(self):
        result = normalize_resume_data({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {"semantic_role": "responsibilities", "label": "项目职责", "items": ["职责"]},
                    {"semantic_role": "generic", "label": "", "items": ["普通内容"]},
                ],
            }],
        })
        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual([block["type"] for block in blocks], ["paragraph", "numbered_list", "bullet_list"])

    def test_unlabelled_work_body_is_not_promoted_by_inline_wording(self):
        source = {
            "basics": {"name": "测试"},
            "work_experience": [{
                "company_name": "示例公司", "job_title": "工程师", "job_type": "实习",
                "content_blocks": [{
                    "type": "bullet_list", "label": "", "items": [
                         "**背景说明：某项背景**",
                         "**责任提示**：",
                         "完成流程一",
                         "完成流程二",
                    ],
                }],
            }],
        }

        blocks = normalize_resume_data(source)["work_experience"][0]["content_blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["semantic_role"], "generic")
        self.assertEqual(blocks[0]["label"], "")
        self.assertEqual(blocks[0]["items"], [
            "**背景说明：某项背景**",
            "**责任提示**：",
            "完成流程一",
            "完成流程二",
        ])

    def test_hidden_work_intro_does_not_reclassify_generic_content(self):
        source = {
            "basics": {"name": "测试"},
            "work_experience": [{
                "company_name": "示例公司",
                "content_blocks": [
                    {
                        "type": "paragraph", "semantic_role": "introduction",
                        "label": "", "text": "保留但隐藏的介绍",
                    },
                    {
                        "type": "bullet_list", "semantic_role": "generic",
                        "label": "", "items": ["日常工作内容"],
                    },
                ],
            }],
        }

        blocks = normalize_resume_data(source)["work_experience"][0]["content_blocks"]
        self.assertEqual(blocks[0]["semantic_role"], "introduction")
        self.assertEqual(blocks[0]["label"], "")
        self.assertEqual(blocks[1]["semantic_role"], "generic")

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

    def test_user_added_language_stays_in_language_module(self):
        result = normalize_resume_data({
            "formatting_version": 3,
            "basics": {"name": "**测试**"},
            "others": {
                "skills": ["英语相关 NLP 技术"],
                "certificates": [],
                "languages": ["英语 CET-6"],
            },
        })

        self.assertEqual(result["others"]["skills"], ["英语相关 NLP 技术"])
        self.assertEqual(result["others"]["languages"], ["英语 CET-6"])

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
