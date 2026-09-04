import unittest

from backend.resume_agent import AgentState, entry_router
from backend.skill_runtime import skill_runtime


class ResumeCoachSkillTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.package = skill_runtime.get("resume-coach")
        self.context = {
            "resume_data": {"basics": {"name": "测试用户"}},
            "base_revision": "revision-1",
            "latest_user_message": "我负责重构结算流程，把耗时从 20 分钟降到 5 分钟。",
            "request_id": "request-1",
            "context_type": "coaching",
            "explicit_command": True,
            "coach_state": {},
        }

    async def test_accumulates_source_traceable_evidence(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start",
            "problem": "项目经历缺少个人贡献和结果",
            "evidence_candidates": [{
                "claim": "负责重构结算流程，耗时从 20 分钟降到 5 分钟",
                "source_quote": "我负责重构结算流程，把耗时从 20 分钟降到 5 分钟。",
            }],
            "open_questions": ["采用了什么关键方案？"],
        }, self.context)
        state = started.coach_state.model_dump()
        issue = state["issues"][state["current_issue_id"]]
        self.assertTrue(started.active)
        self.assertEqual(len(issue["evidence"]), 1)
        self.assertEqual(issue["evidence"][0]["source_request_id"], "request-1")

    async def test_handoff_requires_latest_user_approval(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start", "problem": "表述不具体",
        }, self.context)
        started_state = started.coach_state.model_dump()
        issue_id = started_state["current_issue_id"]
        offered = await skill_runtime.invoke("resume-coach", {
            "operation": "offer_preview",
            "issue_id": issue_id,
            "proposal": {
                "summary": "补充已确认的效率结果",
                "resume_operations": [{
                    "operation": "set",
                    "path": "project_experience[0].description",
                    "value": "重构结算流程，将耗时从 20 分钟降至 5 分钟。",
                }],
            },
        }, {**self.context, "coach_state": started_state})
        offered_state = offered.coach_state.model_dump()
        with self.assertRaises(ValueError):
            await skill_runtime.invoke("resume-coach", {
                "operation": "handoff_to_edit", "issue_id": issue_id,
                "approval_quote": "可以",
            }, {**self.context, "coach_state": offered_state})

        approved = await skill_runtime.invoke("resume-coach", {
            "operation": "handoff_to_edit", "issue_id": issue_id,
            "approval_quote": "可以生成预览",
        }, {
            **self.context,
            "latest_user_message": "可以生成预览",
            "coach_state": offered_state,
        })
        self.assertEqual(approved.edit_handoff.offer_id, offered_state[
            "issues"
        ][issue_id]["pending_preview_offer"]["offer_id"])

    def test_active_coach_bypasses_direct_edit_route(self):
        state = AgentState(
            messages=[], coach_required=True,
            coach_state={"active": True}, assistant_command="coaching",
        )
        self.assertEqual(entry_router(state), "conversation_llm")


if __name__ == "__main__":
    unittest.main()
