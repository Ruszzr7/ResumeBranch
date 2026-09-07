import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.resume_agent import AgentState, conversation_node, tool_node
from backend.skill_runtime import load_agent_skill, skill_runtime


class AgentSkillRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def test_discovers_three_standard_skill_packages(self):
        skills = skill_runtime.discover(refresh=True)
        self.assertEqual(set(skills), {"resume-edit", "resume-snapshot", "resume-coach"})
        self.assertEqual(skills["resume-edit"].tool_name, "resume_edit")
        self.assertEqual(skills["resume-snapshot"].tool_name, "resume_snapshot")
        self.assertEqual(skills["resume-coach"].tool_name, "resume_coach")
        for name, package in skills.items():
            self.assertEqual(package.root.name, name)
            self.assertEqual(package.skill_file.name, "SKILL.md")
            self.assertEqual(package.entrypoint_file.name, "run.py")
            self.assertTrue(package.instructions)

    def test_checked_in_schemas_match_entrypoint_models(self):
        for package in skill_runtime.discover(refresh=True).values():
            expected = package.module.export_schemas()
            for filename, schema in expected.items():
                actual = json.loads((package.root / "references" / filename).read_text("utf-8"))
                self.assertEqual(actual, schema)

    async def test_loader_returns_selected_skill_and_preserves_live_tool_protocol(self):
        state = AgentState(messages=[AIMessage(content="", tool_calls=[{
            "name": load_agent_skill.name,
            "args": {"name": "resume-edit"},
            "id": "load-edit-1",
        }])])
        result = await tool_node(state)
        self.assertEqual(result["active_skill_names"], ["resume-edit"])
        self.assertIsInstance(result["messages"][-1], ToolMessage)
        self.assertIn("本 Skill 永远不会保存简历", result["messages"][-1].content)

        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="请说明修改目标。")))
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        active_state = AgentState(**result)
        with patch("backend.resume_agent.conversation_llm", model):
            await conversation_node(active_state)

        self.assertEqual(
            {item.name for item in model.bind_tools.call_args.args[0]},
            {"load_agent_skill", "resume_edit"},
        )
        sent_messages = bound.ainvoke.await_args.args[0]
        self.assertTrue(sent_messages[-2].tool_calls)
        self.assertIsInstance(sent_messages[-1], ToolMessage)
        self.assertEqual(sent_messages[-1].name, "load_agent_skill")
        self.assertIn("本 Skill 永远不会保存简历", sent_messages[-1].content)
        system_prompt = sent_messages[0].content
        self.assertNotIn("已加载 Agent Skill：resume-edit", system_prompt)
        self.assertNotIn("已加载 Agent Skill：resume-snapshot", system_prompt)

    async def test_executing_a_loaded_skill_generates_confirmation(self):
        state = AgentState(
            messages=[AIMessage(content="", tool_calls=[{
                "name": "resume_edit",
                "args": {
                    "answer_text": "",
                    "resume_operations": [{
                        "op": "set", "path": "basics.name",
                        "value": "新姓名",
                    }],
                    "layout_operations": [],
                },
                "id": "edit-1",
            }])],
            resume_data={"basics": {"name": "旧姓名"}},
            active_skill_names=["resume-edit"],
        )
        result = await tool_node(state)
        self.assertIsNotNone(result["pending_confirmation"])

    async def test_deep_polish_command_forces_coach_tool(self):
        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="")))
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[HumanMessage(content="开始深度打磨")],
            resume_data={"basics": {"name": "测试"}},
            context_type="coaching",
            assistant_command="coaching",
            coach_required=True,
            coach_state={},
            active_skill_names=["resume-coach"],
        )
        with patch("backend.resume_agent.conversation_llm", model):
            await conversation_node(state)

        self.assertEqual(model.bind_tools.call_args.kwargs["tool_choice"], "required")
        self.assertEqual(
            {item.name for item in model.bind_tools.call_args.args[0]},
            {"resume_coach"},
        )
        system_prompt = bound.ainvoke.await_args.args[0][0].content
        self.assertIn("已加载 Agent Skill：resume-coach", system_prompt)
        self.assertIn("resume-coach 私有状态", system_prompt)

    async def test_coach_handoff_forces_one_resume_edit_call(self):
        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(
            content="",
            tool_calls=[{
                "name": "resume_edit",
                "args": {"answer_text": "请查看修改预览"},
                "id": "handoff-edit-1",
            }],
        )))
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[HumanMessage(content="可以按刚才的方案生成预览")],
            resume_data={"basics": {"name": "测试"}},
            coach_state={"active": True},
            coach_required=True,
            coach_turn_processed=True,
            coach_edit_handoff={
                "offer_id": "offer-1",
                "summary": "补充已确认结果",
                "resume_operations": [{
                    "op": "set",
                    "path": "basics.name",
                    "value": "新姓名",
                }],
            },
            active_skill_names=["resume-coach", "resume-edit"],
        )
        with patch("backend.resume_agent.conversation_llm", model):
            await conversation_node(state)

        self.assertEqual(model.bind_tools.call_args.kwargs["tool_choice"], "required")
        self.assertEqual(
            {item.name for item in model.bind_tools.call_args.args[0]},
            {"resume_edit"},
        )

    async def test_pending_start_offer_forces_one_resolution_without_private_history(self):
        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="")))
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[HumanMessage(content="先不用了")],
            resume_data={"basics": {"name": "测试"}},
            coach_state={
                "active": False,
                "pending_start_offer": {
                    "offer_id": "start-offer-1",
                    "problem": "项目成果缺少证据",
                    "source_request_id": "request-1",
                    "status": "offered",
                },
                "issues": {"historical": {"evidence": [{"claim": "private"}]}},
            },
            coach_required=False,
            active_skill_names=["resume-coach"],
        )
        with patch("backend.resume_agent.conversation_llm", model):
            await conversation_node(state)

        self.assertEqual(model.bind_tools.call_args.kwargs["tool_choice"], "required")
        self.assertEqual(
            {item.name for item in model.bind_tools.call_args.args[0]},
            {"resume_coach"},
        )
        system_prompt = bound.ainvoke.await_args.args[0][0].content
        self.assertIn("resume-coach 待启动邀请", system_prompt)
        self.assertNotIn("private", system_prompt)

    async def test_undone_offer_is_injected_as_existing_actionable_proposal(self):
        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="")))
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        state = AgentState(
            messages=[HumanMessage(content="重新生成同一条吧")],
            resume_data={"basics": {"name": "测试"}},
            coach_state={
                "active": True,
                "current_issue_id": "issue-1",
                "issues": {
                    "issue-1": {
                        "problem": "工作经历需要完善",
                        "pending_preview_offer": {
                            "offer_id": "offer-1",
                            "summary": "补充已确认结果",
                            "resume_operations": [],
                            "source_content_digest": "digest",
                            "status": "undone",
                        },
                    },
                },
            },
            coach_required=True,
            active_skill_names=["resume-coach"],
        )
        with patch("backend.resume_agent.conversation_llm", model):
            await conversation_node(state)

        system_prompt = bound.ainvoke.await_args.args[0][0].content
        self.assertIn("撤回后明确要求重新生成", system_prompt)
        self.assertIn("必须对现有建议调用 handoff_to_edit", system_prompt)

    async def test_handoff_execution_consumes_authorized_operations(self):
        state = AgentState(
            messages=[AIMessage(content="", tool_calls=[{
                "name": "resume_edit",
                "args": {"answer_text": "请查看预览"},
                "id": "handoff-edit-2",
            }])],
            resume_data={"basics": {"name": "旧姓名"}},
            coach_state={
                "active": True,
                "current_issue_id": "issue-1",
                "issues": {
                    "issue-1": {
                        "problem": "姓名需要修正",
                        "pending_preview_offer": {
                            "offer_id": "offer-2",
                            "summary": "修正姓名",
                            "resume_operations": [{
                                "op": "set",
                                "path": "basics.name",
                                "value": "新姓名",
                            }],
                            "source_content_digest": "digest",
                            "status": "authorized",
                        },
                    },
                },
            },
            coach_edit_handoff={
                "offer_id": "offer-2",
                "summary": "修正姓名",
                "resume_operations": [{
                    "op": "set",
                    "path": "basics.name",
                    "value": "新姓名",
                }],
            },
            active_skill_names=["resume-coach", "resume-edit"],
        )
        preview = {
            "pending_confirmation": {"confirm_id": "confirm-2", "changes": []},
            "already_satisfied": False,
            "state_changed": False,
            "message": "已生成预览",
        }
        with patch(
            "backend.resume_agent.generate_resume_edit_preview",
            new=AsyncMock(return_value=preview),
        ) as generate_preview:
            result = await tool_node(state)

        generate_preview.assert_awaited_once()
        self.assertEqual(
            result["pending_confirmation"]["coach_offer_id"], "offer-2"
        )
        self.assertIsNone(result["coach_edit_handoff"])
        self.assertTrue(result["coach_edit_processed"])
        self.assertEqual(
            result["coach_state"]["issues"]["issue-1"]
            ["pending_preview_offer"]["status"],
            "preview_generated",
        )

    async def test_only_one_coach_state_transition_runs_per_model_turn(self):
        state = AgentState(
            messages=[
                HumanMessage(content="开始深度打磨"),
                AIMessage(content="", tool_calls=[
                    {
                        "name": "resume_coach",
                        "args": {"operation": "start", "problem": "项目成果不足"},
                        "id": "coach-start-1",
                    },
                    {
                        "name": "resume_coach",
                        "args": {"operation": "start", "problem": "另一个问题"},
                        "id": "coach-start-2",
                    },
                ]),
            ],
            resume_data={"basics": {"name": "测试"}},
            context_type="coaching",
            assistant_command="coaching",
            coach_required=True,
            active_skill_names=["resume-coach"],
            request_id="request-coach-start",
        )

        result = await tool_node(state)

        self.assertTrue(result["coach_state"]["active"])
        self.assertEqual(len(result["coach_state"]["issues"]), 1)
        self.assertIn("每轮只能执行一次", result["messages"][-1].content)

    async def test_invalid_coach_transition_remains_required_for_retry(self):
        coach_state = {
            "active": True,
            "current_issue_id": "issue-1",
            "issues": {
                "issue-1": {
                    "problem": "项目结果需要改写",
                    "pending_preview_offer": {
                        "offer_id": "offer-1",
                        "summary": "补充项目结果",
                        "resume_operations": [{
                            "op": "set",
                            "path": "basics.name",
                            "value": "新姓名",
                        }],
                        "source_content_digest": "digest",
                        "status": "offered",
                    },
                },
            },
        }
        state = AgentState(
            messages=[
                HumanMessage(content="可以"),
                AIMessage(content="", tool_calls=[{
                    "name": "resume_coach",
                    "args": {
                        "operation": "offer_preview",
                        "issue_id": "issue-1",
                        "proposal": {
                            "summary": "补充项目结果",
                            "resume_operations": [{
                                "op": "set",
                                "path": "basics.name",
                                "value": "新姓名",
                            }],
                        },
                    },
                    "id": "duplicate-offer",
                }]),
            ],
            resume_data={"basics": {"name": "测试"}},
            coach_state=coach_state,
            coach_required=True,
            coach_turn_processed=False,
            active_skill_names=["resume-coach"],
            request_id="request-approval",
            context_type="coaching",
        )

        result = await tool_node(state)

        self.assertFalse(result["coach_turn_processed"])
        self.assertFalse(result["coach_state_changed"])
        self.assertIn("已有等待处理的修改建议", result["messages"][-1].content)

        bound = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="")))
        model = SimpleNamespace(bind_tools=MagicMock(return_value=bound))
        retry_state = AgentState(
            messages=result["messages"],
            resume_data=state.resume_data,
            coach_state=result["coach_state"],
            coach_required=True,
            coach_turn_processed=result["coach_turn_processed"],
            coach_state_changed=result["coach_state_changed"],
            active_skill_names=result["active_skill_names"],
            request_id=state.request_id,
            context_type=state.context_type,
        )
        with patch("backend.resume_agent.conversation_llm", model):
            await conversation_node(retry_state)

        self.assertEqual(model.bind_tools.call_args.kwargs["tool_choice"], "required")
        self.assertEqual(
            {item.name for item in model.bind_tools.call_args.args[0]},
            {"resume_coach"},
        )


if __name__ == "__main__":
    unittest.main()
