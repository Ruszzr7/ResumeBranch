import unittest

from backend.import_contract import prepare_import_resume
from backend.resume_schema import validate_resume_data


def prepare_resume(data):
    return validate_resume_data(prepare_import_resume(data))


class ResumeImportPreparationTests(unittest.TestCase):
    def test_education_supplement_is_a_flat_lossless_list(self):
        result = prepare_resume({
            "education_supplement": ["**论文标题**", "校级奖励", ""],
            "education": [],
        })
        self.assertEqual(result["education_supplement"], ["**论文标题**", "校级奖励"])

    def test_project_tech_stack_is_a_fixed_block_and_top_level_tech_stack_stays_skills(self):
        result = prepare_resume({
            "basics": {"name": "张三"},
            "others": {"skills": ["Python"]},
            "project_experience": [{
                "project_name": "项目 A",
                "content_blocks": [
                    {"semantic_role": "responsibilities", "label": "项目职责", "items": ["完成联调"]},
                    {"label": "技术栈", "text": "Python、FastAPI"},
                    {"semantic_role": "introduction", "label": "项目简介", "text": "项目背景"},
                    {"semantic_role": "generic", "label": "", "items": ["补充说明"]},
                ],
            }],
        })

        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual([block["semantic_role"] for block in blocks], [
            "responsibilities", "tech_stack", "introduction", "generic",
        ])
        self.assertEqual(blocks[0]["type"], "numbered_list")
        self.assertEqual(blocks[0]["label"], "项目职责")
        self.assertEqual(blocks[1]["label"], "技术栈")
        self.assertEqual(result["others"]["skills"], ["Python"])

    def test_publications_are_a_standalone_editable_string_list(self):
        result = prepare_resume({
            "publications": ["论文 A，已接收", "论文 B，返修"],
            "education": [{"school_name": "示例大学", "theses": []}],
        })
        self.assertEqual(result["publications"], ["论文 A，已接收", "论文 B，返修"])
        self.assertEqual(result["education"][0]["theses"], [])

    def test_preserves_unknown_import_sections(self):
        source = {
            "basics": {"name": "李靖华", "birth_date": "2002.06"},
            "志愿服务": ["校级志愿服务队成员"],
        }

        result = prepare_resume(source)

        self.assertEqual(result["basics"]["birth_date"], "2002.06")
        self.assertEqual(result["custom_sections"], [{"title": "志愿服务", "items": ["校级志愿服务队成员"]}])

    def test_rejects_retired_work_content_field(self):
        with self.assertRaises(ValueError):
            prepare_resume({
                "basics": {"name": "测试"},
                "work_experience": [{
                    "company": "示例公司", "position": "实习生",
                    "time": "2025.01 - 2025.06",
                    "content": ["项目职责：（1）完成模块A；（2）完成模块B"],
                }],
            })

    def test_rejects_retired_project_details_field(self):
        with self.assertRaises(ValueError):
            prepare_resume({
                "basics": {"name": "测试"},
                "project_experience": [{
                    "project_name": "机器人项目", "details": ["项目简介：面向展厅导航场景"],
                }],
            })

    def test_explicit_intro_and_responsibilities_are_canonical_blocks(self):
        source = {
            "basics": {"name": "测试"},
            "work_experience": [{
                "company_name": "示例公司",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "负责展厅导航系统"},
                    {"type": "numbered_list", "semantic_role": "responsibilities", "label": "项目职责", "items": ["完成模块设计与实现", "完成联调与性能验证"]},
                ],
            }],
            "project_experience": [{
                "project_name": "机器人项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "面向复杂场景"},
                    {"type": "numbered_list", "semantic_role": "responsibilities", "label": "项目职责", "items": ["完成轨迹训练", "验证控制策略"]},
                ],
            }],
        }

        result = prepare_resume(source)
        for item, intro_label, duties_label in (
            (result["work_experience"][0], "工作简介", "工作职责"),
            (result["project_experience"][0], "项目简介", "项目职责"),
        ):
            blocks = item["content_blocks"]
            self.assertEqual(blocks[0]["semantic_role"], "introduction")
            self.assertEqual(blocks[0]["label"], intro_label)
            self.assertEqual(blocks[1]["semantic_role"], "responsibilities")
            self.assertEqual(blocks[1]["label"], duties_label)
            self.assertEqual(blocks[1]["type"], "numbered_list")
            self.assertEqual(len(blocks[1]["items"]), 2)

    def test_explicit_content_block_aliases_and_boolean_strings_are_normalized(self):
        result = prepare_resume({
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

    def test_explicit_bold_content_blocks_keep_project_responsibility_semantics(self):
        result = prepare_resume({
            "basics": {"name": "测试"},
            "work_experience": [{
                "company_name": "示例公司",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "**负责导航系统设计**"},
                    {"type": "bullet_list", "semantic_role": "responsibilities", "label": "项目职责", "items": ["**完成模块实现**", "完成联调验证"]},
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
        self.assertEqual(work_blocks[0]["label"], "工作简介")
        self.assertEqual(work_blocks[0]["text"], "**负责导航系统设计**")
        self.assertEqual(work_blocks[1]["semantic_role"], "responsibilities")
        self.assertEqual(work_blocks[1]["label"], "工作职责")
        self.assertEqual(work_blocks[1]["items"], ["**完成模块实现**", "完成联调验证"])

        project_blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual(project_blocks[1]["semantic_role"], "generic")
        self.assertEqual(project_blocks[1]["type"], "bullet_list")
        self.assertEqual(project_blocks[1]["items"], ["补充说明"])

    def test_visual_group_is_required_for_generic_content_after_intro(self):
        result = prepare_resume({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {"type": "bullet_list", "label": "普通工作内容", "items": ["完成设计"], "source_layout_group": "duties"},
                    {"type": "bullet_list", "label": "其他项目内容", "items": ["补充说明"], "source_layout_group": "generic"},
                ],
            }],
        })

        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual(len(blocks), 3)
        self.assertEqual([block["semantic_role"] for block in blocks], ["introduction", "responsibilities", "generic"])
        self.assertEqual([block["type"] for block in blocks], ["paragraph", "numbered_list", "bullet_list"])
        self.assertEqual([block["label"] for block in blocks], ["项目简介", "项目职责", ""])
        self.assertEqual([block["items"] for block in blocks[1:]], [["完成设计"], ["补充说明"]])

    def test_unlabelled_content_after_explicit_intro_defaults_to_responsibilities(self):
        result = prepare_resume({
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
        result = prepare_resume({
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

    def test_intro_following_visual_groups_split_responsibilities_and_generic_content(self):
        result = prepare_resume({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {
                        "type": "bullet_list", "items": ["职责一", "职责二", "职责三"],
                        "source_layout_group": "duties", "source_indent_level": 1, "source_marker_type": "bullet",
                    },
                    {
                        "type": "bullet_list", "items": ["补充内容"],
                        "source_layout_group": "generic", "source_indent_level": 0, "source_marker_type": "bullet",
                    },
                ],
            }],
        })

        blocks = result["project_experience"][0]["content_blocks"]
        self.assertEqual([block["semantic_role"] for block in blocks], ["introduction", "responsibilities", "generic"])
        self.assertEqual([block["type"] for block in blocks], ["paragraph", "numbered_list", "bullet_list"])
        self.assertEqual(blocks[1]["items"], ["职责一", "职责二", "职责三"])
        self.assertEqual(blocks[2]["items"], ["补充内容"])
        self.assertFalse(any(key.startswith("source_") for key in blocks[1]))

    def test_experience_without_semantic_headings_stays_generic(self):
        result = prepare_resume({
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
        result = prepare_resume({
            "basics": {"name": "测试"},
            "project_experience": [{
                "project_name": "项目",
                "content_blocks": [
                    {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "text": "背景"},
                    {"type": "bullet_list", "semantic_role": "generic", "label": "", "items": ["补充说明一", "补充说明二"], "source_layout_group": "generic"},
                ],
            }],
        })

        block = result["project_experience"][0]["content_blocks"][1]
        self.assertEqual(block["semantic_role"], "generic")
        self.assertEqual(block["type"], "bullet_list")
        self.assertEqual(block["items"], ["补充说明一", "补充说明二"])

    def test_unknown_generic_labels_stay_inline_and_role_defaults_are_stable(self):
        result = prepare_resume({
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
            "type": "numbered_list", "semantic_role": "responsibilities", "label": "项目职责",
            "label_bold": True, "text": "", "items": [
                "**未定义前缀**：基于 **方法** 完成", "完成联调",
            ],
        })
        self.assertEqual(blocks[2]["semantic_role"], "generic")
        self.assertEqual(blocks[2]["items"], ["补充说明"])
        self.assertEqual(len(blocks), 3)

    def test_content_block_type_defaults_follow_semantic_role(self):
        result = prepare_resume({
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
        self.assertEqual([block["semantic_role"] for block in blocks], ["introduction", "responsibilities", "generic"])

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

        blocks = prepare_resume(source)["work_experience"][0]["content_blocks"]
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

        blocks = prepare_resume(source)["work_experience"][0]["content_blocks"]
        self.assertEqual(blocks[0]["semantic_role"], "introduction")
        self.assertEqual(blocks[0]["label"], "")
        self.assertEqual(blocks[1]["semantic_role"], "generic")

    def test_import_keeps_explicit_custom_section_boundary(self):
        result = prepare_resume({
            "basics": {"name": "测试"},
            "others": {"skills": ["Python"]},
            "custom_sections": [
                {"title": "专业技能", "items": ["ROS2", "Python"]},
                {"title": "校园经历", "items": ["学生干部"]},
            ],
        })

        self.assertEqual(result["others"]["skills"], ["Python"])
        self.assertEqual(result["custom_sections"], [
            {"title": "专业技能", "items": ["ROS2", "Python"]},
            {"title": "校园经历", "items": ["学生干部"]},
        ])

    def test_preserves_custom_section_list_style_when_explicit(self):
        result = prepare_resume({
            "basics": {"name": "测试"},
            "custom_sections": [
                {"title": "段落栏目", "items": ["第一句", "第二句"], "list_style": "paragraph"},
                {"title": "编号栏目", "items": ["第一项"], "list_style": "numbered"},
            ],
        })

        self.assertEqual(result["custom_sections"][0]["list_style"], "paragraph")
        self.assertEqual(result["custom_sections"][1]["list_style"], "numbered")

    def test_import_does_not_reclassify_language_and_skills(self):
        result = prepare_resume({
            "basics": {"name": "测试"},
            "others": {
                "skills": ["5. 仿真、强化学习与英语：Isaac Sim、PyTorch"],
                "certificates": [],
                "languages": ["英语 CET-4"],
            },
        })

        self.assertEqual(result["others"]["languages"], ["英语 CET-4"])
        self.assertEqual(result["others"]["skills"], ["5. 仿真、强化学习与英语：Isaac Sim、PyTorch"])

    def test_user_added_language_stays_in_language_module(self):
        result = prepare_resume({
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

if __name__ == "__main__":
    unittest.main()
