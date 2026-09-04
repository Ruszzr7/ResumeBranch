import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.layout_config import default_layout_config
from backend.resume_changes import build_resume_state_version
from backend.resume_agent import AgentState, entry_router, is_mission_resume_edit_request, tool_node, tool_node_router
from langgraph.graph import END
from backend.resume_contract import build_resume_edit_contract, build_resume_edit_contract_text
from backend.skill_runtime import skill_runtime

_resume_edit_module = skill_runtime.get("resume-edit").module
ResumeEditOperationError = _resume_edit_module.ResumeEditOperationError
ResumeEditRequest = _resume_edit_module.ResumeEditRequest
run_resume_edit = _resume_edit_module.run_resume_edit


def resume_payload():
    return {
        "basics": {"name": "旧姓名", "target_position": "后端开发"},
        "education": [],
        "project_experience": [{
            "project_name": "项目 A",
            "role": "开发",
            "date_range": [],
            "content_blocks": [{
                "type": "bullet_list",
                "semantic_role": "generic",
                "label": "",
                "label_bold": False,
                "text": "",
                "items": ["第一条", "第二条", "第三条"],
            }],
        }],
    }


class ResumeEditSkillTests(unittest.IsolatedAsyncioTestCase):
    def test_resume_edit_contract_is_machine_readable_and_not_case_specific(self):
        contract = build_resume_edit_contract()
        self.assertIn("custom_sections", contract["path_namespace"]["roots"])
        operation_shape = contract["operation_shape"]
        self.assertEqual(operation_shape["required_fields"], ["op", "path"])
        self.assertIn("path", operation_shape["allowed_fields"])
        self.assertNotIn("target", operation_shape)
        self.assertEqual(
            contract["value_shapes"]["custom_section"]["required"],
            {"title": "string", "items": "string_list"},
        )
        self.assertTrue(
            contract["optional_field_policy"]["emit_only_when_explicitly_requested"]
        )
        self.assertFalse(contract["optional_field_policy"]["infer_or_repeat_defaults"])
        self.assertEqual(
            contract["value_shapes"]["project_experience"]["required_non_empty"],
            ["project_name"],
        )
        self.assertFalse(
            contract["value_shapes"]["project_experience"]["additional_properties"]
        )
        self.assertNotIn(
            "tech_stack",
            contract["value_shapes"]["work_experience"]["content_block_roles"],
        )
        text = build_resume_edit_contract_text()
        self.assertIn("path_namespace", text)
        self.assertIn("custom_section", text)
        self.assertIn("未明确要求时必须省略", text)
        self.assertNotIn("skill-v3", text)
        content_block = contract["value_shapes"]["content_block"]
        self.assertEqual(set(content_block["types"]), {"paragraph", "bullet_list", "numbered_list"})
        self.assertEqual(
            content_block["type_selection"],
            "semantic_role 不绑定 type；paragraph 使用 text，bullet_list/numbered_list 使用 items，具体形式按当前内容或用户明确要求",
        )
        self.assertEqual(
            content_block["role_descriptions"]["generic"]["roots"],
            ["work_experience", "project_experience"],
        )
        self.assertEqual(
            content_block["role_descriptions"]["responsibilities"]["labels_by_root"],
            {"work_experience": "工作职责", "project_experience": "项目职责"},
        )
        self.assertIn("self_evaluation", contract["root_value_shapes"]["top_level_lists"])

    def test_mission_follow_up_uses_the_edit_router(self):
        self.assertTrue(is_mission_resume_edit_request("执行第 1 点", "layout"))
        self.assertFalse(is_mission_resume_edit_request("分析第 1 点", "layout"))
        state = AgentState(messages=[HumanMessage(content="执行第 1 点")], context_type="layout")
        self.assertEqual(entry_router(state), "conversation_llm")

    async def test_structured_content_operation_is_deterministic_and_does_not_call_llm(self):
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                resume_operations=({
                    "op": "set", "path": "basics.name", "value": "新姓名", "expected": "旧姓名",
                },),
            )
        )
        self.assertEqual(result.resume_data["basics"]["name"], "新姓名")

    async def test_content_operation_checks_only_content_digest(self):
        resume = resume_payload()
        layout = default_layout_config()
        base_version = build_resume_state_version(resume, layout)
        changed_layout = default_layout_config()
        changed_layout["global"]["moduleMargin"] = 0.8
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume,
                layout_config=changed_layout,
                base_version=base_version,
                resume_operations=({
                    "op": "set", "path": "basics.name", "value": "新姓名", "expected": "旧姓名",
                },),
            )
        )
        self.assertEqual(result.resume_data["basics"]["name"], "新姓名")

        changed_resume = resume_payload()
        changed_resume["basics"]["name"] = "其他姓名"
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=changed_resume,
                    layout_config=layout,
                    base_version=base_version,
                    resume_operations=({
                        "op": "set", "path": "basics.name", "value": "新姓名",
                    },),
                )
            )

    async def test_layout_operation_checks_only_layout_digest(self):
        resume = resume_payload()
        layout = default_layout_config()
        base_version = build_resume_state_version(resume, layout)
        changed_resume = resume_payload()
        changed_resume["basics"]["name"] = "其他姓名"
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=changed_resume,
                layout_config=layout,
                base_version=base_version,
                layout_operations=({
                    "op": "set", "path": "global.moduleMargin", "value": 0.8,
                },),
            )
        )
        self.assertEqual(result.layout_config["global"]["moduleMargin"], 0.8)

        changed_layout = default_layout_config()
        changed_layout["global"]["moduleMargin"] = 0.7
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume,
                    layout_config=changed_layout,
                    base_version=base_version,
                    layout_operations=({
                        "op": "set", "path": "global.moduleMargin", "value": 0.8,
                    },),
                )
            )

    async def test_project_tech_stack_can_be_edited_without_becoming_top_level_skill(self):
        payload = resume_payload()
        payload["project_experience"][0]["content_blocks"].insert(0, {
            "type": "paragraph",
            "semantic_role": "tech_stack",
            "label": "技术栈",
            "label_bold": True,
            "text": "Python、FastAPI",
            "items": [],
        })
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=payload,
                layout_config=default_layout_config(),
                resume_operations=({
                    "op": "set",
                    "path": "project_experience[0].content_blocks[0].text",
                    "value": "Python、FastAPI、MySQL",
                    "expected": "Python、FastAPI",
                },),
            )
        )
        block = result.resume_data["project_experience"][0]["content_blocks"][0]
        self.assertEqual(block["semantic_role"], "tech_stack")
        self.assertEqual(block["text"], "Python、FastAPI、MySQL")
        self.assertEqual(result.resume_data["others"]["skills"], [])

    async def test_custom_section_uses_title_items_shape(self):
        payload = resume_payload()
        payload["custom_sections"] = []
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=payload,
                layout_config=default_layout_config(),
                resume_operations=({
                    "op": "append",
                    "path": "custom_sections",
                    "value": {"title": "开源实践", "items": ["维护权限校验示例项目"]},
                },),
            )
        )
        self.assertEqual(
            result.resume_data["custom_sections"][0],
            {"title": "开源实践", "items": ["维护权限校验示例项目"]},
        )

    async def test_indexed_custom_section_uses_the_same_contract(self):
        payload = resume_payload()
        payload["custom_sections"] = [{"title": "开源实践", "items": ["旧内容"]}]
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=payload,
                layout_config=default_layout_config(),
                resume_operations=({
                    "op": "set",
                    "path": "custom_sections[0]",
                    "value": {"title": "开源实践", "items": ["新内容"]},
                },),
            )
        )
        self.assertEqual(result.resume_data["custom_sections"][0]["items"], ["新内容"])

    async def test_experience_item_must_be_addressed_by_a_specific_field(self):
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                    resume_operations=({
                        "op": "set",
                        "path": "project_experience[0]",
                        "value": {"project_name": "新项目"},
                    },),
                )
            )
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                    resume_operations=({
                        "op": "set",
                        "path": "project_experience[0].content_blocks[0].type",
                        "value": "table",
                    },),
                )
            )

    async def test_resume_operations_follow_declared_paths(self):
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                resume_operations=({
                    "op": "set",
                    "path": "project_experience[0].content_blocks[0].items[0]",
                    "value": "改后的第一条",
                },),
            )
        )
        self.assertEqual(
            result.resume_data["project_experience"][0]["content_blocks"][0]["items"][0],
            "改后的第一条",
        )

        payload = resume_payload()
        payload["basics"]["photo_aspect_ratio"] = 1.5
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=payload,
                    layout_config=default_layout_config(),
                    resume_operations=({
                        "op": "set", "path": "basics.photo_aspect_ratio", "value": 1.8,
                    },),
                )
            )

    async def test_schema_valid_resume_roots_can_be_replaced(self):
        payload = resume_payload()
        payload["honors"] = ["旧荣誉"]
        payload["self_evaluation"] = ["旧评价"]
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=payload,
                layout_config=default_layout_config(),
                resume_operations=(
                    {"op": "set", "path": "honors", "value": ["新荣誉"]},
                    {"op": "replace", "path": "self_evaluation", "value": ["新评价"]},
                ),
            )
        )
        self.assertEqual(result.resume_data["honors"], ["新荣誉"])
        self.assertEqual(result.resume_data["self_evaluation"], ["新评价"])

    async def test_schema_invalid_resume_roots_are_rejected(self):
        invalid_operations = (
            {"op": "set", "path": "basics", "value": {"name": "新姓名", "unknown": "x"}},
            {"op": "set", "path": "others", "value": {"skills": "Python"}},
            {"op": "set", "path": "honors", "value": "新荣誉"},
        )
        for operation in invalid_operations:
            with self.subTest(operation=operation):
                with self.assertRaises(ResumeEditOperationError):
                    await run_resume_edit(
                        ResumeEditRequest(
                            resume_data=resume_payload(),
                            layout_config=default_layout_config(),
                            resume_operations=(operation,),
                        )
                    )
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                    resume_operations=({"op": "remove", "path": "honors"},),
                )
            )

    async def test_indexed_content_block_semantic_assertion_rejects_wrong_object(self):
        with self.assertRaisesRegex(ResumeEditOperationError, "内容块语义目标不匹配"):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                    resume_operations=({
                        "op": "set",
                        "path": "project_experience[0].content_blocks[0].items[0]",
                        "value": "错误目标",
                        "target_semantic_role": "responsibilities",
                    },),
                )
            )

        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                resume_operations=({
                    "op": "set",
                    "path": "project_experience[0].content_blocks[0].items[0]",
                    "value": "正确目标",
                    "target_semantic_role": "generic",
                },),
            )
        )
        self.assertEqual(
            result.resume_data["project_experience"][0]["content_blocks"][0]["items"][0],
            "正确目标",
        )

    async def test_semantic_parent_path_is_not_an_alternative_operation_protocol(self):
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                    resume_operations=({
                        "op": "remove",
                        "parent_path": "work_experience[0]",
                        "target_semantic_role": "responsibilities",
                        "expected": "第二条",
                    },),
                )
            )

    async def test_content_block_semantic_role_does_not_restrict_display_type(self):
        payload = resume_payload()
        payload["project_experience"][0]["content_blocks"] = [{
            "type": "paragraph", "semantic_role": "responsibilities", "label": "项目职责",
            "text": "完成接口设计", "items": [],
        }]
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=payload,
                layout_config=default_layout_config(),
                resume_operations=({
                    "op": "set",
                    "path": "project_experience[0].content_blocks[0].text",
                    "value": "完成接口设计与验证",
                    "target_semantic_role": "responsibilities",
                },),
            )
        )
        block = result.resume_data["project_experience"][0]["content_blocks"][0]
        self.assertEqual(block["type"], "paragraph")
        self.assertEqual(block["text"], "完成接口设计与验证")

    async def test_custom_section_rejects_content_blocks_shape(self):
        payload = resume_payload()
        payload["custom_sections"] = []
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=payload,
                    layout_config=default_layout_config(),
                    resume_operations=({
                        "op": "append",
                        "path": "custom_sections",
                        "value": {
                            "title": "开源实践",
                            "content_blocks": [{"type": "paragraph", "text": "维护权限校验示例项目"}],
                        },
                    },),
                )
            )

    async def test_content_block_rejects_custom_section_shape(self):
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                    resume_operations=({
                        "op": "append",
                        "path": "project_experience[0].content_blocks",
                        "value": {"title": "开源实践", "items": ["不应写入内容块"]},
                    },),
                )
            )

    async def test_new_experience_items_follow_the_declared_object_shape(self):
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                resume_operations=({
                    "op": "append",
                    "path": "project_experience",
                    "value": {
                        "project_name": "权限校验项目",
                        "role": "后端开发",
                        "content_blocks": [{
                            "type": "bullet_list", "semantic_role": "generic",
                            "label": "", "items": ["实现访问控制"],
                        }],
                    },
                },),
            )
        )
        self.assertEqual(
            result.resume_data["project_experience"][-1]["project_name"],
            "权限校验项目",
        )

        for invalid_value in (
            {"unexpected": "x"},
            {"project_name": "", "role": "开发"},
            {"project_name": "项目", "unexpected": "x"},
            {"project_name": "项目", "date_range": "2025"},
        ):
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ResumeEditOperationError):
                    await run_resume_edit(
                        ResumeEditRequest(
                            resume_data=resume_payload(),
                            layout_config=default_layout_config(),
                            resume_operations=({
                                "op": "append",
                                "path": "project_experience",
                                "value": invalid_value,
                            },),
                        )
                    )

    async def test_work_content_blocks_reject_project_only_and_parser_only_fields(self):
        payload = resume_payload()
        payload["work_experience"] = [{"company_name": "示例公司", "content_blocks": []}]
        invalid_blocks = (
            {
                "type": "paragraph", "semantic_role": "tech_stack",
                "label": "技术栈", "text": "Redis", "items": [],
            },
            {
                "type": "bullet_list", "semantic_role": "generic",
                "items": ["实现接口"], "source_layout_group": "group-1",
            },
        )
        for block in invalid_blocks:
            with self.subTest(block=block):
                with self.assertRaises(ResumeEditOperationError):
                    await run_resume_edit(
                        ResumeEditRequest(
                            resume_data=payload,
                            layout_config=default_layout_config(),
                            resume_operations=({
                                "op": "append",
                                "path": "work_experience[0].content_blocks",
                                "value": block,
                            },),
                        )
                    )

    async def test_list_operations_support_move_insert_and_remove(self):
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                resume_operations=(
                    {"op": "move", "path": "project_experience[0].content_blocks[0].items", "from_index": 0, "to_index": 2},
                    {"op": "insert", "path": "project_experience[0].content_blocks[0].items", "index": 1, "value": "新增"},
                    {"op": "remove", "path": "project_experience[0].content_blocks[0].items", "index": 2, "expected": "第三条"},
                ),
            )
        )
        self.assertEqual(
            result.resume_data["project_experience"][0]["content_blocks"][0]["items"],
            ["第二条", "新增", "第一条"],
        )

    async def test_layout_operation_is_supported_but_font_sizes_are_rejected(self):
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                layout_operations=({"op": "set", "path": "global.moduleMargin", "value": 0.7},),
            )
        )
        self.assertEqual(result.layout_config["global"]["moduleMargin"], 0.7)
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                    layout_operations=({"op": "set", "path": "global.fontSize", "value": 12},),
                )
            )
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                    layout_operations=({
                        "op": "set", "path": "global", "value": {"moduleMargin": 0.7},
                    },),
                )
            )

    async def test_layout_skill_rejects_renderer_only_fields_and_invalid_values(self):
        for operation in (
            {"op": "set", "path": "education.componentRows", "value": []},
            {"op": "set", "path": "education.metricsPlacement", "value": "info-column"},
            {"op": "set", "path": "skills.paragraphSpacing", "value": 0.5},
            {"op": "set", "path": "global.lineHeight", "value": 1.37},
        ):
            with self.assertRaises(ResumeEditOperationError):
                await run_resume_edit(
                    ResumeEditRequest(
                        resume_data=resume_payload(),
                        layout_config=default_layout_config(),
                        layout_operations=(operation,),
                    )
                )

    async def test_layout_skill_accepts_supported_content_forms(self):
        result = await run_resume_edit(
            ResumeEditRequest(
                resume_data=resume_payload(),
                layout_config=default_layout_config(),
                layout_operations=(
                    {"op": "set", "path": "project_experience.detailsStyle", "value": "paragraph"},
                    {"op": "set", "path": "education.supplementListStyle", "value": "numbered"},
                ),
            )
        )
        self.assertEqual(result.layout_config["project_experience"]["detailsStyle"], "paragraph")
        self.assertEqual(result.layout_config["education"]["supplementListStyle"], "numbered")

    async def test_layout_skill_rejects_basic_information_layout_fields(self):
        for operation in (
            {"op": "set", "path": "basics.preset", "value": "left-aligned"},
            {"op": "set", "path": "basics.photoPosition", "value": "hidden"},
            {"op": "set", "path": "basics.photoHeightMm", "value": 28},
            {"op": "set", "path": "basics.hiddenFields", "value": ["phone"]},
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(ResumeEditOperationError):
                    await run_resume_edit(
                        ResumeEditRequest(
                            resume_data=resume_payload(),
                            layout_config=default_layout_config(),
                            layout_operations=(operation,),
                        )
                    )

    async def test_missing_structured_operations_fails_closed_without_model_retry(self):
        with self.assertRaises(ResumeEditOperationError):
            await run_resume_edit(
                ResumeEditRequest(
                    resume_data=resume_payload(),
                    layout_config=default_layout_config(),
                )
            )

    async def test_structured_tool_call_creates_existing_confirmation_preview(self):
        state = AgentState(
            messages=[
                HumanMessage(content="把姓名改为新姓名"),
                AIMessage(content="", tool_calls=[{
                    "name": "resume_edit",
                    "args": {
                        "resume_operations": [{
                            "op": "set", "path": "basics.name", "value": "新姓名", "expected": "旧姓名",
                        }],
                        "layout_operations": [],
                    },
                    "id": "edit-1",
                }]),
            ],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
            user_id=1,
            task_id="task-1",
        )
        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await tool_node(state)
        self.assertIsNotNone(result["pending_confirmation"])
        self.assertEqual(
            result["pending_confirmation"]["resume_candidate"]["basics"]["name"],
            "新姓名",
        )
        self.assertEqual(
            result["context_metadata_updates"]["edit_intent_state"]["status"],
            "awaiting_confirmation",
        )
        llm.ainvoke.assert_not_called()

    async def test_structured_tool_call_keeps_answer_before_confirmation(self):
        state = AgentState(
            messages=[
                HumanMessage(content="把姓名改为新姓名，并告诉我还可以怎么优化。"),
                AIMessage(content="", tool_calls=[{
                    "name": "resume_edit",
                    "args": {
                        "answer_text": "还可以继续检查项目成果是否量化。",
                        "resume_operations": [{
                            "op": "set", "path": "basics.name", "value": "新姓名", "expected": "旧姓名",
                        }],
                        "layout_operations": [],
                    },
                    "id": "edit-with-reply-1",
                }]),
            ],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
            user_id=1,
            task_id="task-1",
        )

        result = await tool_node(state)

        self.assertIsNotNone(result["pending_confirmation"])
        self.assertIsInstance(result["messages"][-1], AIMessage)
        self.assertIn("还可以继续检查", result["messages"][-1].content)

    async def test_noop_edit_ends_tool_loop_without_confirmation(self):
        state = AgentState(
            messages=[
                HumanMessage(content="姓名保持旧姓名"),
                AIMessage(content="", tool_calls=[{
                    "name": "resume_edit",
                    "args": {
                        "resume_operations": [{
                            "op": "set", "path": "basics.name", "value": "旧姓名",
                        }],
                        "layout_operations": [],
                    },
                    "id": "noop-edit-1",
                }]),
            ],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )
        result = await tool_node(state)
        self.assertIsNone(result["pending_confirmation"])
        self.assertTrue(result["edit_noop"])
        self.assertIn("已经符合", result["messages"][-1].content)
        self.assertEqual(tool_node_router(AgentState(**result)), END)

    async def test_duplicate_structured_tool_calls_execute_once(self):
        tool_call = {
            "name": "resume_edit",
            "args": {
                "resume_operations": [{
                    "op": "set", "path": "basics.name", "value": "新姓名",
                }],
                "layout_operations": [],
            },
        }
        state = AgentState(
            messages=[
                HumanMessage(content="把姓名改为新姓名"),
                AIMessage(content="", tool_calls=[
                    {**tool_call, "id": "duplicate-1"},
                    {**tool_call, "id": "duplicate-2"},
                ]),
            ],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
            user_id=1,
            task_id="task-1",
        )
        with patch("backend.resume_agent._generate_resume_edit_preview", wraps=None) as generate:
            generate.side_effect = None
            generate.return_value = {
                "pending_confirmation": {
                    "confirm_id": "confirm-1",
                    "changes": [{"id": "change-1", "kind": "content"}],
                },
                "message": "已生成修改预览。",
            }
            result = await tool_node(state)

        generate.assert_awaited_once()
        self.assertIsNotNone(result["pending_confirmation"])
        duplicate_messages = [
            message for message in result["messages"]
            if isinstance(message, ToolMessage)
            and message.content == "本轮已处理相同工具调用，已忽略重复请求。"
        ]
        self.assertEqual(len(duplicate_messages), 1)


if __name__ == "__main__":
    unittest.main()
