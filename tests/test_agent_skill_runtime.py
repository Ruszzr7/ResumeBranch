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


if __name__ == "__main__":
    unittest.main()
