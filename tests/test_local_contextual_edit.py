import unittest

from langchain_core.messages import HumanMessage

from backend.layout_config import default_layout_config
from backend.resume_agent import AgentState, build_local_edit_candidate, entry_router


def resume_payload(*, gender="男", schools=None):
    school_values = schools or ["海岚大学"]
    return {
        "basics": {
            "name": "测试用户",
            "gender": gender,
            "phone": "13800000000",
            "email": "test@example.test",
            "target_position": "后端工程师",
        },
        "education": [
            {
                "school_name": school,
                "major": "计算机科学与技术",
                "degree": "本科",
                "date_range": ["2020", "2024"],
                "school_tags": [],
                "gpa": "3.5",
                "gpa_scale": "4.0",
                "ranking": "",
                "theses": [],
            }
            for school in school_values
        ],
        "education_supplement": [],
        "research_interests": [],
        "honors": [],
        "publications": [],
        "work_experience": [],
        "project_experience": [],
        "custom_sections": [],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }


class LocalContextualEditTests(unittest.TestCase):
    def test_module_scoped_school_replacement_uses_direct_edit(self):
        state = AgentState(
            messages=[HumanMessage(content="请将教育经历中的‘海岚大学’改为‘云川大学’，其余教育字段保持原样。")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )

        self.assertEqual(entry_router(state), "direct_edit")
        candidate = build_local_edit_candidate(state)
        self.assertEqual(candidate["education"][0]["school_name"], "云川大学")

    def test_module_scoped_basic_replacement_uses_direct_edit(self):
        state = AgentState(
            messages=[HumanMessage(content="将基本信息中的男改为女")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )

        self.assertEqual(entry_router(state), "direct_edit")
        candidate = build_local_edit_candidate(state)
        self.assertEqual(candidate["basics"]["gender"], "女")

    def test_non_unique_old_value_falls_back_to_conversation(self):
        state = AgentState(
            messages=[HumanMessage(content="将教育经历中的‘海岚大学’改为‘云川大学’")],
            resume_data=resume_payload(schools=["海岚大学", "海岚大学"]),
            layout_data=default_layout_config(),
        )

        self.assertEqual(entry_router(state), "conversation_llm")
        self.assertIsNone(build_local_edit_candidate(state))

    def test_contextual_replacement_strips_only_outer_quotes(self):
        resume = resume_payload()
        resume["project_experience"] = [{
            "project_name": "权限平台",
            "role": "后端开发",
            "date_range": [],
            "content_blocks": [{
                "type": "bullet_list",
                "semantic_role": "responsibilities",
                "label": "项目职责",
                "items": ["设计接口"],
            }],
        }]
        state = AgentState(
            messages=[HumanMessage(content="将项目职责中的‘设计接口’改为“实现‘权限校验’接口”")],
            resume_data=resume,
            layout_data=default_layout_config(),
        )

        self.assertEqual(entry_router(state), "direct_edit")
        candidate = build_local_edit_candidate(state)
        self.assertEqual(
            candidate["project_experience"][0]["content_blocks"][0]["items"],
            ["实现‘权限校验’接口"],
        )

    def test_explicit_quote_semantics_fall_back_to_conversation(self):
        state = AgentState(
            messages=[HumanMessage(content="把姓名改为“林沐辰”，保留引号")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )

        self.assertEqual(entry_router(state), "conversation_llm")
        self.assertIsNone(build_local_edit_candidate(state))


if __name__ == "__main__":
    unittest.main()
