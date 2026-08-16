import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from backend.harness.interview import (
    apply_suggestion_candidate,
    handle_control_action,
    interview_feature_config,
    run_interview_turn,
    validate_fact_candidates,
    validate_suggestion,
)
from backend.layout_config import default_layout_config
from backend.resume_agent import AgentState, entry_router, interview_coach_node


def resume_payload():
    return {
        "basics": {
            "name": "测试候选人", "gender": "", "phone": "", "email": "",
            "target_position": "产品经理",
        },
        "education": [],
        "work_experience": [{
            "company_name": "示例科技", "job_title": "产品实习生",
            "date_range": ["2025.01", "2025.06"], "job_type": "实习",
            "details": ["参与落地页优化。"],
        }],
        "project_experience": [],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }


class InterviewHarnessTests(unittest.IsolatedAsyncioTestCase):
    def test_fact_validation_requires_verbatim_current_user_source(self):
        answer = "我负责了A/B测试，最终注册转化率提升20%。"
        accepted = validate_fact_candidates([
            {
                "claim": "注册转化率提升20%",
                "source_quote": "注册转化率提升20%",
                "section": "work_experience",
                "dimension": "impact",
            },
            {
                "claim": "收入提升30%",
                "source_quote": "注册转化率提升20%",
                "section": "work_experience",
                "dimension": "impact",
            },
            {
                "claim": "独立负责全项目",
                "source_quote": "用户没有说过这句话",
                "section": "work_experience",
                "dimension": "ownership",
            },
        ], answer, "request-1")

        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["source_type"], "user_message")
        self.assertEqual(accepted[0]["source_request_id"], "request-1")

    async def test_interview_turn_keeps_one_question_and_builds_sourced_suggestion(self):
        output = {
            "diagnosis_summary": "这段经历缺少影响证明？",
            "strengths": [],
            "gaps": ["缺少个人动作？"],
            "acknowledgement": "已核实转化结果。",
            "focus_section": "work_experience",
            "dimension": "impact",
            "question": "你具体设计了哪一个实验？还做了什么？",
            "phase": "awaiting_apply",
            "fact_candidates": [{
                "claim": "注册转化率提升20%",
                "source_quote": "注册转化率提升20%",
                "section": "work_experience",
                "dimension": "impact",
            }],
            "open_items": ["实验设计"],
            "rejected_suggestions": [],
            "suggestion": {
                "target_path": "work_experience.0.details.0",
                "suggested": "参与落地页 A/B 测试，推动注册转化率提升20%。",
                "rationale": "补充已核实结果",
            },
        }
        llm = AsyncMock()
        llm.ainvoke.return_value = AIMessage(content=json.dumps(output, ensure_ascii=False))

        result = await run_interview_turn(
            llm=llm,
            action="answer",
            mode="coaching",
            user_text="我做了落地页A/B测试，注册转化率提升20%。",
            resume_data=resume_payload(),
            jd_data={},
            memory={},
            workflow={"status": "active", "phase": "questioning"},
            request_id="request-2",
            layout_data=default_layout_config(),
        )

        prompt = llm.ainvoke.call_args.args[0][1].content
        self.assertIn("当前排版与经历内容契约", prompt)
        self.assertIn("项目职责", prompt)

        self.assertEqual(result["content"].count("？"), 1)
        self.assertNotIn("?", result["content"])
        self.assertEqual(result["workflow_updates"]["phase"], "awaiting_apply")
        self.assertEqual(len(result["memory"]["verified_facts"]), 1)
        self.assertIsNotNone(result["memory"]["latest_suggestion"])

    def test_suggestion_application_is_deterministic_and_stale_safe(self):
        resume = resume_payload()
        facts = [{"claim": "注册转化率提升20%", "source_quote": "注册转化率提升20%"}]
        suggestion = validate_suggestion({
            "target_path": "work_experience.0.details.0",
            "suggested": "推动注册转化率提升20%。",
            "rationale": "量化结果",
        }, resume, facts)
        candidate = apply_suggestion_candidate(resume, suggestion)

        self.assertEqual(resume["work_experience"][0]["details"][0], "参与落地页优化。")
        self.assertEqual(candidate["work_experience"][0]["details"][0], "推动注册转化率提升20%。")
        stale = dict(suggestion)
        stale["original"] = "已变化"
        with self.assertRaisesRegex(ValueError, "简历已变化"):
            apply_suggestion_candidate(resume, stale)

    def test_pause_resume_and_end_are_deterministic_without_llm(self):
        workflow = {
            "phase": "questioning", "status": "active",
            "current_question": "你具体做了什么？", "focus_section": "work_experience",
        }
        paused = handle_control_action("pause", "coaching", workflow, {})
        self.assertEqual(paused["workflow_updates"]["status"], "paused")
        resumed = handle_control_action(
            "resume", "coaching", {**workflow, "status": "paused"}, {},
        )
        self.assertEqual(resumed["content"].count("？"), 1)
        ended = handle_control_action("end", "coaching", workflow, {})
        self.assertEqual(ended["workflow_updates"]["phase"], "completed")

    def test_feature_rollout_is_stable_per_user_and_task(self):
        with patch.dict(os.environ, {
            "INTERVIEW_HARNESS_ENABLED": "true",
            "INTERVIEW_HARNESS_ROLLOUT_PERCENT": "37",
        }, clear=False):
            first = interview_feature_config(7, "task-1")
            second = interview_feature_config(7, "task-1")
        self.assertEqual(first, second)
        self.assertEqual(first["enabled"], first["bucket"] < 37)

    async def test_graph_entry_and_apply_reuse_existing_confirmation_preview(self):
        resume = resume_payload()
        suggestion = {
            "target_path": "work_experience.0.details.0",
            "original": "参与落地页优化。",
            "suggested": "推动注册转化率提升20%。",
            "rationale": "量化结果",
        }
        state = AgentState(
            messages=[HumanMessage(content="应用当前改写建议")],
            resume_data=resume,
            layout_data=default_layout_config(),
            user_id=7,
            task_id="task-1",
            interaction_mode="coaching",
            interaction_action="apply",
            interview_memory={"latest_suggestion": suggestion, "verified_facts": [{"claim": "20%"}]},
            workflow_state={
                "focus_section": "work_experience",
                "status": "active",
                "phase": "awaiting_apply",
            },
        )
        self.assertEqual(entry_router(state), "interview_coach")

        result = await interview_coach_node(state)
        pending = result["pending_confirmation"]
        self.assertEqual(pending["tool_name"], "save_resume_tool")
        self.assertEqual(pending["status"], "pending")
        self.assertTrue(pending["changes"])

    async def test_invalid_llm_output_fails_read_only_with_recoverable_question(self):
        state = AgentState(
            messages=[HumanMessage(content="开始拷打")],
            resume_data=resume_payload(),
            layout_data=default_layout_config(),
            user_id=7,
            task_id="task-1",
            interaction_mode="coaching",
            interaction_action="start",
            interview_memory={},
            workflow_state={},
            request_id="bad-output",
        )
        fake_llm = AsyncMock()
        fake_llm.ainvoke.return_value = AIMessage(content="not json")
        with patch("backend.resume_agent.conversation_llm", fake_llm):
            result = await interview_coach_node(state)

        self.assertIn("简历未被修改", result["messages"][-1].content)
        self.assertEqual(result["messages"][-1].content.count("？"), 1)
        self.assertIsNone(result["pending_confirmation"])
        self.assertEqual(result["resume_data"], resume_payload())
        self.assertEqual(result["workflow_updates"]["last_node"], "interview_fallback")


if __name__ == "__main__":
    unittest.main()
