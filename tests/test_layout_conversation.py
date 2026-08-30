import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from backend.layout_config import default_layout_config
from backend.layout_capabilities import build_layout_capability_manifest, build_layout_context_text
from backend.resume_agent import (
    AgentState,
    build_local_layout_candidate,
    classify_local_edit_request,
    conversation_node,
    direct_edit_node,
    entry_router,
    has_explicit_change_authorization,
    is_resume_coaching_request,
    make_pending_confirmation,
    proposal_generator_node,
    request_resume_edit,
    render_resume_pdf_images_tool,
    tool_node,
)


def resume_payload(name="测试用户"):
    return {
        "basics": {"name": name, "gender": "", "phone": "", "email": "", "target_position": ""},
        "education": [{
            "school_name": "测试大学", "major": "计算机", "degree": "本科",
            "date_range": ["2020", "2024"], "school_tags": ["211"],
            "gpa": "3.5", "gpa_scale": "4.0", "ranking": "", "theses": [],
        }],
        "work_experience": [], "project_experience": [],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }


class LayoutConversationTests(unittest.IsolatedAsyncioTestCase):
    def test_layout_contract_separates_operation_paths_from_state_wrapper(self):
        manifest = build_layout_capability_manifest()
        namespace = manifest["operation_namespace"]
        self.assertIn("global", namespace["roots"])
        self.assertIn("self_evaluation", namespace["roots"])
        self.assertNotIn("modules", namespace["roots"])
        self.assertTrue(namespace["state_wrapper_is_not_an_operation_root"])
        self.assertIn("self_evaluation.listStyle", namespace["paths"]["self_evaluation"])
        self.assertNotIn("basics", namespace["paths"])
        self.assertNotIn("basics", manifest["scope"]["modules"])
        exposed_values = {
            value
            for scope in (manifest["scope"]["global"], *manifest["scope"]["modules"].values())
            for values in scope.get("allowed_values", {}).values()
            for value in values
        }
        self.assertTrue(exposed_values.issubset(manifest["user_facing_labels"]["values"]))
        title_shape = manifest["object_value_shapes"]["global.titleOverrides"]
        self.assertEqual(title_shape["value"]["optional_keys"], ["zh", "en"])
        context = build_layout_context_text(default_layout_config())
        self.assertIn("operation_namespace", context)
        self.assertNotIn("contactLayout", context)
        self.assertNotIn("metricsPlacement", context)
        self.assertIn("当前可编辑排版状态（只读，不是操作路径）", context)

    def test_edit_skill_description_defines_selection_boundary(self):
        description = request_resume_edit.description
        self.assertIn("经过多轮对话", description)
        self.assertIn("目标、范围和期望结果足够明确", description)
        self.assertIn("信息或指代仍不明确时先澄清", description)
        self.assertIn("只提交本次明确要求的修改", description)
        self.assertIn("只生成候选", description)
        self.assertIn("确认后才保存", description)
        answer_schema = request_resume_edit.args_schema.model_json_schema()["properties"]["answer_text"]
        self.assertIn("纯修改请求留空", answer_schema["description"])
        self.assertIn("执行状态由系统生成", answer_schema["description"])
        self.assertEqual(answer_schema["default"], "")

    def test_visual_skill_description_defines_visual_only_selection(self):
        description = render_resume_pdf_images_tool.description
        self.assertIn("页面、排版或视觉效果", description)
        self.assertIn("不能只根据排版配置或简历文字推断", description)
        self.assertIn("无需传入简历数据", description)
        self.assertIn("不会修改或保存简历", description)
        self.assertIn("不要重复调用", description)

    async def test_edit_tool_adds_system_preview_status_when_answer_text_is_empty(self):
        before = resume_payload()
        state = AgentState(
            messages=[
                HumanMessage(content="把姓名改为张伟。"),
                AIMessage(content="", tool_calls=[{
                    "name": "request_resume_edit",
                    "args": {
                        "answer_text": "",
                        "resume_operations": [{
                            "op": "set", "path": "basics.name", "value": "张伟",
                        }],
                        "layout_operations": [],
                    },
                    "id": "call-edit-empty-reply",
                    "type": "tool_call",
                }]),
            ],
            resume_data=before,
            layout_data=default_layout_config(),
            user_id=7,
            task_id="task-1",
        )

        result = await tool_node(state)

        self.assertIsNotNone(result["pending_confirmation"])
        self.assertEqual(result["resume_data"], before)
        self.assertIn("已根据你的要求生成修改预览", result["messages"][-1].content)
        self.assertIn("接受前不会保存", result["messages"][-1].content)

    async def test_edit_tool_places_answer_before_system_preview_status(self):
        answer = "原名称没有明确体现服务端研发方向。"
        state = AgentState(
            messages=[
                HumanMessage(content="为什么职位名称不准确？同时改成服务端研发实习生。"),
                AIMessage(content="", tool_calls=[{
                    "name": "request_resume_edit",
                    "args": {
                        "answer_text": answer,
                        "resume_operations": [{
                            "op": "set",
                            "path": "basics.target_position",
                            "value": "服务端研发实习生",
                        }],
                        "layout_operations": [],
                    },
                    "id": "call-edit-with-answer",
                    "type": "tool_call",
                }]),
            ],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
            user_id=7,
            task_id="task-1",
        )

        result = await tool_node(state)

        content = result["messages"][-1].content
        self.assertLess(content.index(answer), content.index("已根据你的要求生成修改预览"))
        self.assertIsNotNone(result["pending_confirmation"])

    def test_review_and_interview_requests_stay_in_conversation_mode(self):
        review_requests = [
            "请分析这份简历有哪些不足，并推荐如何修改和完善",
            "请先全面诊断我的简历，先不要修改",
            "请以面试官身份开始拷打我的项目经历",
            "结合 JD 分析匹配度并给出优化建议",
            "请分析当前简历排版并给出建议，本轮只分析，不修改简历",
        ]
        for request in review_requests:
            with self.subTest(request=request):
                state = AgentState(
                    messages=[HumanMessage(content=request)],
                    resume_data=resume_payload(), layout_data=default_layout_config(),
                )
                self.assertTrue(is_resume_coaching_request(request))
                self.assertEqual(entry_router(state), "conversation_llm")

    def test_explicit_apply_request_still_uses_edit_pipeline(self):
        request = "请直接优化项目经历并应用到简历"
        state = AgentState(
            messages=[HumanMessage(content=request)],
            resume_data=resume_payload(), layout_data=default_layout_config(),
        )
        self.assertFalse(is_resume_coaching_request(request))
        self.assertEqual(entry_router(state), "conversation_llm")

    def test_mixed_question_and_concrete_edit_is_not_forced_read_only(self):
        for request in (
            "教育经历怎样写会更紧凑？请回答后把本科专业改为软件工程。",
            "先说明当前专业有什么问题，再把本科专业改为软件工程。",
        ):
            with self.subTest(request=request):
                state = AgentState(
                    messages=[HumanMessage(content=request)],
                    resume_data=resume_payload(), layout_data=default_layout_config(),
                )
                self.assertTrue(has_explicit_change_authorization(request))
                self.assertFalse(is_resume_coaching_request(request))
                self.assertEqual(entry_router(state), "conversation_llm")

    def test_question_without_edit_authorization_stays_read_only(self):
        for request in ("教育经历怎样写会更紧凑？", "如何修改项目经历？"):
            with self.subTest(request=request):
                self.assertFalse(has_explicit_change_authorization(request))
                self.assertTrue(is_resume_coaching_request(request))

    async def test_coaching_turn_still_exposes_both_skills_for_model_selection(self):
        bound = SimpleNamespace(
            ainvoke=AsyncMock(return_value=AIMessage(content="诊断结果")),
        )
        fake_llm = SimpleNamespace(
            bind_tools=MagicMock(return_value=bound),
        )
        state = AgentState(
            messages=[HumanMessage(content="请全面诊断简历并给出修改建议")],
            resume_data=resume_payload(), layout_data=default_layout_config(),
        )
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            result = await conversation_node(state)
        exposed = fake_llm.bind_tools.call_args.args[0]
        self.assertEqual(
            {item.name for item in exposed},
            {"render_resume_pdf_images", "request_resume_edit"},
        )
        bound.ainvoke.assert_awaited_once()
        system_prompt = bound.ainvoke.await_args.args[0][0].content
        self.assertIn("本轮模式：只读诊断与简历教练", system_prompt)
        self.assertEqual(result["messages"][-1].content, "诊断结果")

    async def test_mixed_mission_apply_and_consultation_still_exposes_edit_skill(self):
        bound = SimpleNamespace(
            ainvoke=AsyncMock(return_value=AIMessage(content="已处理明确修改，并继续回答咨询。")),
        )
        fake_llm = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[
                AIMessage(content="1. 调整模块间距。"),
                HumanMessage(content="执行第一点，另外工作经历还有什么优化建议吗？"),
            ],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
            context_type="layout",
            context_metadata={"initial_analysis_completed": True},
        )
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            await conversation_node(state)
        exposed = {item.name for item in fake_llm.bind_tools.call_args.args[0]}
        self.assertEqual(exposed, {"render_resume_pdf_images", "request_resume_edit"})

    async def test_common_layout_request_is_local_and_previews_without_llm(self):
        state = AgentState(
            messages=[HumanMessage(content="学校后面的211改成描边")],
            resume_data=resume_payload(), layout_data=default_layout_config(),
            user_id=7, task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        candidate = build_local_layout_candidate(state)
        self.assertEqual(candidate["education"]["schoolTagStyle"], "outline")

        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        pending = result["pending_confirmation"]
        self.assertEqual([item["id"] for item in pending["changes"]], ["layout-education"])
        self.assertEqual(pending["resume_candidate"]["basics"]["name"], "测试用户")
        self.assertEqual(pending["layout_candidate"]["education"]["schoolTagStyle"], "outline")

    def test_retired_education_preset_is_not_parsed_as_a_local_layout_edit(self):
        state = AgentState(
            messages=[HumanMessage(content="把专业和GPA放到学校右边。")],
            resume_data=resume_payload(), layout_data=default_layout_config(),
        )
        self.assertIsNone(build_local_layout_candidate(state))

    def test_retired_contact_arrangement_is_not_parsed_as_a_local_layout_edit(self):
        state = AgentState(
            messages=[HumanMessage(content="把联系方式改为竖排。")],
            resume_data=resume_payload(), layout_data=default_layout_config(),
        )
        self.assertIsNone(build_local_layout_candidate(state))

    async def test_complete_default_layout_request_is_local_and_uses_current_defaults(self):
        current_layout = default_layout_config()
        current_layout["education"]["schoolTagStyle"] = "outline"
        state = AgentState(
            messages=[HumanMessage(content="请恢复默认排版。")],
            resume_data=resume_payload(), layout_data=current_layout,
            user_id=7, task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        with patch("backend.resume_agent.conversation_llm") as llm:
            result = await direct_edit_node(state)
        llm.ainvoke.assert_not_called()
        candidate = result["pending_confirmation"]["layout_candidate"]
        self.assertNotIn("preset", candidate["basics"])
        self.assertEqual(candidate["education"]["schoolTagStyle"], "text")
        self.assertNotIn("preset", candidate["work_experience"])

    async def test_recognized_layout_noops_stay_local_without_confirmation(self):
        requests = [
            "请恢复默认排版。",
            "学校标签不要黑底，改成普通文字。",
            "把工作经历移到项目经历前面。",
        ]
        for request in requests:
            with self.subTest(request=request):
                current_layout = default_layout_config()
                state = AgentState(
                    messages=[HumanMessage(content=request)],
                    resume_data=resume_payload(),
                    layout_data=current_layout,
                    user_id=7,
                    task_id="task-1",
                )
                self.assertEqual(entry_router(state), "direct_edit")
                result = await direct_edit_node(state)
                self.assertIsNone(result["pending_confirmation"])
                self.assertEqual(result["layout_data"], current_layout)
                self.assertIn("已经符合", result["messages"][-1].content)

    def test_layout_title_override_is_not_misclassified_as_content_edit(self):
        state = AgentState(
            messages=[HumanMessage(content="工作经历标题改为实习与工作经历。")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )
        self.assertEqual(entry_router(state), "direct_edit")
        candidate = build_local_layout_candidate(state)
        self.assertEqual(
            candidate["global"]["titleOverrides"]["work_experience"]["zh"],
            "实习与工作经历",
        )

    def test_layout_title_override_strips_balanced_outer_quotes(self):
        for opening, closing in (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'"), ("「", "」"), ("『", "』")):
            with self.subTest(opening=opening):
                state = AgentState(
                    messages=[HumanMessage(content=f"工作经历标题改为{opening}实习与工作经历{closing}。")],
                    resume_data=resume_payload(),
                    layout_data=default_layout_config(),
                )
                self.assertEqual(entry_router(state), "direct_edit")
                candidate = build_local_layout_candidate(state)
                self.assertEqual(
                    candidate["global"]["titleOverrides"]["work_experience"]["zh"],
                    "实习与工作经历",
                )

    async def test_layout_title_override_preview_uses_plain_chinese_text(self):
        state = AgentState(
            messages=[HumanMessage(content="工作经历标题改为‘实习与工作经历’。")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
            user_id=7,
            task_id="task-1",
        )

        result = await direct_edit_node(state)
        content = result["messages"][-1].content
        self.assertIn("工作/实习经历：实习与工作经历", content)
        self.assertNotIn("{'zh'", content)

    def test_ambiguous_quote_semantics_do_not_use_local_parser(self):
        requests = (
            "工作经历标题改为“实习与工作经历，并保留引号。",
            "工作经历标题改为“实习与工作经历”，内容需要包含引号。",
        )
        for request in requests:
            with self.subTest(request=request):
                state = AgentState(
                    messages=[HumanMessage(content=request)],
                    resume_data=resume_payload(),
                    layout_data=default_layout_config(),
                )
                self.assertEqual(entry_router(state), "conversation_llm")
                self.assertIsNone(build_local_layout_candidate(state))

    def test_basic_information_layout_is_not_exposed_to_local_edits(self):
        for request in ("把姓名和基本信息改为左对齐。", "隐藏照片。", "隐藏手机号。", "恢复基本信息默认布局。"):
            with self.subTest(request=request):
                state = AgentState(
                    messages=[HumanMessage(content=request)],
                    resume_data=resume_payload(),
                    layout_data=default_layout_config(),
                )
                self.assertIsNone(build_local_layout_candidate(state))

    def test_global_default_layout_preserves_basic_information_renderer_state(self):
        layout = default_layout_config()
        layout["basics"]["photoHeightMm"] = 31
        state = AgentState(
            messages=[HumanMessage(content="恢复整份简历默认排版。")],
            resume_data=resume_payload(),
            layout_data=layout,
        )

        candidate = build_local_layout_candidate(state)
        self.assertEqual(candidate["basics"], layout["basics"])

    async def test_semantic_edit_with_independent_layout_change_uses_conversation_skill_policy(self):
        requests = [
            "重新撰写项目职责，并把项目经历放到工作经历前面。",
            "优化工作经历，同时隐藏照片。",
            "润色自我评价，另外把技能改成标签形式。",
        ]
        for request in requests:
            with self.subTest(request=request):
                state = AgentState(
                    messages=[HumanMessage(content=request)],
                    resume_data=resume_payload(),
                    layout_data=default_layout_config(),
                )
                self.assertEqual(entry_router(state), "conversation_llm")

        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="请补充改写方向。")))
        fake_llm = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[HumanMessage(content=requests[0])],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            await conversation_node(state)
        exposed = {item.name for item in fake_llm.bind_tools.call_args.args[0]}
        self.assertIn("request_resume_edit", exposed)
        system_prompt = bound.ainvoke.await_args.args[0][0].content
        self.assertIn("需要澄清的修改", system_prompt)
        self.assertIn("独立且明确", system_prompt)
        self.assertIn("不得提交完整简历或完整布局 JSON", system_prompt)
        self.assertIn("custom_sections", system_prompt)
        self.assertIn("title", system_prompt)
        self.assertIn("items", system_prompt)

    def test_question_and_edit_request_stays_in_conversation_mode(self):
        state = AgentState(
            messages=[HumanMessage(content="教育经历怎样写会更紧凑？请回答后把本科专业改为软件工程。")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )
        self.assertEqual(entry_router(state), "conversation_llm")

    def test_local_edit_resolution_has_explicit_noop_and_unresolved_states(self):
        base = resume_payload()
        resolved = AgentState(
            messages=[HumanMessage(content="把姓名改为张伟。")],
            resume_data=base,
            layout_data=default_layout_config(),
        )
        self.assertEqual(classify_local_edit_request(resolved), "resolved")

        noop = AgentState(
            messages=[HumanMessage(content="把姓名改为测试用户。")],
            resume_data=base,
            layout_data=default_layout_config(),
        )
        self.assertEqual(classify_local_edit_request(noop), "resolved_noop")

        unresolved = AgentState(
            messages=[HumanMessage(content="重新撰写项目职责。")],
            resume_data=base,
            layout_data=default_layout_config(),
        )
        self.assertEqual(classify_local_edit_request(unresolved), "unresolved")

    def test_partially_resolved_edit_does_not_use_local_route(self):
        state = AgentState(
            messages=[HumanMessage(content="把姓名改为张伟，同时把籍贯改为杭州市。")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )
        self.assertEqual(entry_router(state), "conversation_llm")

    async def test_explicit_edit_without_tool_call_does_not_retry(self):
        state = AgentState(
            messages=[HumanMessage(content="把姓名改为张伟。")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )
        first = AIMessage(content="已根据你的要求生成修改预览。")
        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=first))
        fake_llm = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            result = await conversation_node(state)

        self.assertEqual(bound.ainvoke.await_count, 1)
        self.assertEqual(result["messages"][-1].tool_calls, [])
        self.assertIn("当前尚未生成修改候选", result["messages"][-1].content)
        self.assertEqual(
            result["context_metadata_updates"]["edit_intent_state"]["status"],
            "awaiting_tool",
        )

    async def test_ambiguous_execution_claim_is_replaced_without_retry(self):
        state = AgentState(
            messages=[HumanMessage(content="删除不重要的内容。")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
        )
        bound = SimpleNamespace(
            ainvoke=AsyncMock(return_value=AIMessage(content="已根据你的要求生成修改预览。"))
        )
        fake_llm = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            result = await conversation_node(state)

        bound.ainvoke.assert_awaited_once()
        reply = result["messages"][-1].content
        self.assertIn("尚未生成修改候选", reply)
        self.assertNotIn("已根据你的要求生成修改预览", reply)

    async def test_mixed_content_and_layout_request_uses_one_local_preview(self):
        layout = default_layout_config()
        layout["education"]["schoolTagStyle"] = "outline"
        state = AgentState(
            messages=[HumanMessage(content="把姓名改为张伟，学校标签不要黑底")],
            resume_data=resume_payload(), layout_data=layout,
            user_id=7, task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        result = await direct_edit_node(state)
        self.assertEqual(result["pending_confirmation"]["resume_candidate"]["basics"]["name"], "张伟")
        kinds = [item.get("kind", "content") for item in result["pending_confirmation"]["changes"]]
        self.assertIn("content", kinds)
        self.assertIn("layout", kinds)

    async def test_contextual_content_and_layout_request_merges_one_local_preview(self):
        resume = resume_payload()
        resume["project_experience"] = [{
            "project_name": "项目A",
            "role": "开发",
            "date_range": [],
            "content_blocks": [{
                "type": "numbered_list",
                "semantic_role": "responsibilities",
                "label": "项目职责",
                "items": ["设计接口"],
            }],
        }]
        layout = default_layout_config()
        layout["education"]["schoolTagStyle"] = "outline"
        state = AgentState(
            messages=[HumanMessage(content="将项目职责中的设计接口改为实现接口，并把学校标签改成普通文字。")],
            resume_data=resume,
            layout_data=layout,
            user_id=7,
            task_id="task-1",
        )
        self.assertEqual(entry_router(state), "direct_edit")
        result = await direct_edit_node(state)
        candidate = result["pending_confirmation"]["resume_candidate"]
        self.assertEqual(
            candidate["project_experience"][0]["content_blocks"][0]["items"],
            ["实现接口"],
        )
        self.assertEqual(
            result["pending_confirmation"]["layout_candidate"]["education"]["schoolTagStyle"],
            "text",
        )

    async def test_complex_combined_request_uses_exactly_one_model_call(self):
        layout = default_layout_config()
        project_index = layout["global"]["sectionOrder"].index("project_experience")
        state = AgentState(
            messages=[HumanMessage(content="重新组织项目经历描述，并将它放到教育经历前面")],
            resume_data=resume_payload(), layout_data=layout,
            user_id=7, task_id="task-1",
            context_metadata={
                "resume_operations": [{
                    "op": "append", "path": "project_experience",
                    "value": {"project_name": "项目A", "role": "开发", "date_range": [], "content_blocks": [{"type": "bullet_list", "semantic_role": "generic", "items": ["完成接口优化"]}]},
                }],
                "layout_operations": [{
                    "op": "move", "path": "global.sectionOrder",
                    "from_index": project_index, "to_index": 0,
                }],
            },
        )
        with patch("backend.resume_agent.conversation_llm") as fake_llm:
            result = await proposal_generator_node(state)
        fake_llm.ainvoke.assert_not_called()
        ids = [item["id"] for item in result["pending_confirmation"]["changes"]]
        self.assertIn("layout-global", ids)
        self.assertTrue(any(not value.startswith("layout-") for value in ids))

    async def test_structured_model_cannot_bypass_modal_only_font_sizes(self):
        before_layout = default_layout_config()
        state = AgentState(
            messages=[HumanMessage(content="重新组织项目经历描述并应用")],
            resume_data=resume_payload(), layout_data=before_layout,
            user_id=7, task_id="task-1",
            context_metadata={
                "resume_operations": [{
                    "op": "append", "path": "project_experience",
                    "value": {"project_name": "项目A", "role": "开发", "date_range": [], "content_blocks": [{"type": "bullet_list", "semantic_role": "generic", "items": ["完成接口优化"]}]},
                }],
                "layout_operations": [{"op": "set", "path": "global.fontSize", "value": 11.5}],
            },
        )
        with patch("backend.resume_agent.conversation_llm") as fake_llm:
            result = await proposal_generator_node(state)
        fake_llm.ainvoke.assert_not_called()
        self.assertIsNone(result["pending_confirmation"])
        self.assertIn("无法安全生成", result["proposal_error"])

    async def test_selecting_layout_group_persists_only_that_group(self):
        before_layout = default_layout_config()
        before_layout["education"]["schoolTagStyle"] = "outline"
        after_layout = default_layout_config()
        after_layout["education"]["schoolTagStyle"] = "text"
        before_resume = resume_payload()
        proposal_state = AgentState(
            resume_data=before_resume, layout_data=before_layout, user_id=7, task_id="task-1"
        )
        pending = make_pending_confirmation(proposal_state, before_resume, after_layout)
        confirm_state = AgentState(
            messages=[HumanMessage(content=f'[CONFIRM_REPLY:{pending["confirm_id"]}:confirm_selected:layout-education]')],
            resume_data=before_resume, layout_data=before_layout, pending_confirmation=pending,
            user_id=7, task_id="task-1",
        )
        fake_db = SimpleNamespace(close=lambda: None)
        with (
            patch("backend.tools.update_resume", return_value="简历已成功保存"),
            patch("backend.database.SessionLocal", return_value=fake_db),
            patch("backend.database.save_task_layout_config", return_value=after_layout) as save_layout,
            patch("backend.resume_agent.record_assistant_revision") as record_revision,
        ):
            result = await tool_node(confirm_state)
        save_layout.assert_called_once()
        record_revision.assert_called_once()
        self.assertEqual(result["layout_data"]["education"]["schoolTagStyle"], "text")
        self.assertTrue(result["just_saved"])


if __name__ == "__main__":
    unittest.main()
