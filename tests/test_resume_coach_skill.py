import unittest

from pydantic import ValidationError

from backend.resume_agent import AgentState, entry_router
from backend.skill_runtime import skill_runtime


class ResumeCoachSkillTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.package = skill_runtime.get("resume-coach")
        self.context = {
            "resume_data": {"basics": {"name": "测试用户"}},
            "source_content_digest": "content-digest-1",
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

    async def test_explicit_empty_snapshots_clear_resolved_questions(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start",
            "problem": "项目结果需要核实",
            "conclusions": ["尚未确认交付结果"],
            "open_questions": ["是否有实际交付结果？"],
        }, self.context)
        state = started.coach_state.model_dump()
        issue_id = state["current_issue_id"]

        resolved = await skill_runtime.invoke("resume-coach", {
            "operation": "update",
            "issue_id": issue_id,
            "evidence_candidates": [{
                "claim": "交付阶段连续运行一天未出现错误",
                "source_quote": "交付阶段实测运行一天没有出错",
            }],
            "conclusions": ["已有连续运行一天无错误的交付结果"],
            "open_questions": [],
        }, {
            **self.context,
            "request_id": "request-result",
            "latest_user_message": "交付阶段实测运行一天没有出错",
            "coach_state": state,
        })

        issue = resolved.coach_state.issues[issue_id]
        self.assertEqual(issue.open_questions, [])
        self.assertEqual(
            issue.conclusions,
            ["已有连续运行一天无错误的交付结果"],
        )
        self.assertEqual(issue.evidence[-1].source_request_id, "request-result")

    async def test_omitted_snapshots_preserve_existing_issue_reasoning(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start",
            "problem": "项目结果需要核实",
            "conclusions": ["需要确认结果"],
            "open_questions": ["是否完成交付？"],
        }, self.context)
        state = started.coach_state.model_dump()
        issue_id = state["current_issue_id"]

        updated = await skill_runtime.invoke("resume-coach", {
            "operation": "update",
            "issue_id": issue_id,
            "evidence_candidates": [{
                "claim": "项目已经交付",
                "source_quote": "项目已经交付",
            }],
        }, {
            **self.context,
            "request_id": "request-delivery",
            "latest_user_message": "项目已经交付",
            "coach_state": state,
        })

        issue = updated.coach_state.issues[issue_id]
        self.assertEqual(issue.conclusions, ["需要确认结果"])
        self.assertEqual(issue.open_questions, ["是否完成交付？"])

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
                    "op": "set",
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
        retried = await skill_runtime.invoke("resume-coach", {
            "operation": "handoff_to_edit", "issue_id": issue_id,
            "approval_quote": "仍然同意生成预览",
        }, {
            **self.context,
            "latest_user_message": "仍然同意生成预览",
            "coach_state": approved.coach_state.model_dump(),
        })
        self.assertEqual(retried.edit_handoff.offer_id, approved.edit_handoff.offer_id)

    async def test_unresolved_preview_offer_cannot_be_overwritten(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start", "problem": "项目结果需要改写",
        }, self.context)
        state = started.coach_state.model_dump()
        issue_id = state["current_issue_id"]
        proposal = {
            "summary": "补充已确认结果",
            "resume_operations": [{
                "op": "set",
                "path": "basics.name",
                "value": "新姓名",
            }],
        }
        offered = await skill_runtime.invoke("resume-coach", {
            "operation": "offer_preview",
            "issue_id": issue_id,
            "proposal": proposal,
        }, {**self.context, "coach_state": state})

        with self.assertRaisesRegex(ValueError, "已有等待处理的修改建议"):
            await skill_runtime.invoke("resume-coach", {
                "operation": "offer_preview",
                "issue_id": issue_id,
                "proposal": proposal,
            }, {
                **self.context,
                "request_id": "request-approval",
                "latest_user_message": "可以",
                "coach_state": offered.coach_state.model_dump(),
            })

    async def test_new_evidence_invalidates_an_unresolved_preview_offer(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start", "problem": "项目结果需要改写",
        }, self.context)
        state = started.coach_state.model_dump()
        issue_id = state["current_issue_id"]
        offered = await skill_runtime.invoke("resume-coach", {
            "operation": "offer_preview",
            "issue_id": issue_id,
            "proposal": {
                "summary": "补充运行结果",
                "resume_operations": [{
                    "op": "set",
                    "path": "basics.name",
                    "value": "新姓名",
                }],
            },
        }, {**self.context, "coach_state": state})

        revised = await skill_runtime.invoke("resume-coach", {
            "operation": "update",
            "issue_id": issue_id,
            "evidence_candidates": [{
                "claim": "测试为间歇运行而非连续运行",
                "source_quote": "是间歇运行，不是连续运行",
            }],
            "conclusions": ["只能表述为间歇运行"],
            "open_questions": [],
        }, {
            **self.context,
            "request_id": "request-correction",
            "latest_user_message": "是间歇运行，不是连续运行",
            "coach_state": offered.coach_state.model_dump(),
        })

        offer = revised.coach_state.issues[issue_id].pending_preview_offer
        self.assertEqual(offer.status, "invalidated")

    async def test_suggested_entry_requires_a_matching_user_acceptance(self):
        suggestion_context = {**self.context, "explicit_command": False}
        offered = await skill_runtime.invoke("resume-coach", {
            "operation": "offer_start",
            "problem": "项目经历缺少可核验结果",
        }, suggestion_context)
        offered_state = offered.coach_state.model_dump()
        start_offer = offered_state["pending_start_offer"]
        self.assertFalse(offered.active)
        self.assertEqual(start_offer["status"], "offered")

        with self.assertRaises(ValueError):
            await skill_runtime.invoke("resume-coach", {
                "operation": "start",
                "entry": "explicit_request",
                "approval_quote": "可以开始",
                "problem": "Agent 试图替换邀请问题",
            }, {
                **suggestion_context,
                "latest_user_message": "可以开始",
                "coach_state": offered_state,
            })

        with self.assertRaises(ValueError):
            await skill_runtime.invoke("resume-coach", {
                "operation": "start",
                "entry": "accepted_offer",
                "offer_id": start_offer["offer_id"],
                "approval_quote": "可以",
                "problem": start_offer["problem"],
            }, {
                **suggestion_context,
                "latest_user_message": "我还需要想一想。",
                "coach_state": offered_state,
            })

        accepted = await skill_runtime.invoke("resume-coach", {
            "operation": "start",
            "entry": "accepted_offer",
            "offer_id": start_offer["offer_id"],
            "approval_quote": "可以开始",
            "problem": "Agent 不得换成另一个问题",
        }, {
            **suggestion_context,
            "latest_user_message": "可以开始，请继续追问。",
            "coach_state": offered_state,
        })
        self.assertTrue(accepted.active)
        self.assertEqual(accepted.coach_state.entry, "accepted_offer")
        self.assertIsNone(accepted.coach_state.pending_start_offer)
        current = accepted.coach_state.issues[accepted.coach_state.current_issue_id]
        self.assertEqual(current.problem, start_offer["problem"])

    async def test_direct_request_requires_a_current_user_quote(self):
        direct_context = {
            **self.context,
            "explicit_command": False,
            "latest_user_message": "请深入追问我的项目成果",
        }
        with self.assertRaises(ValueError):
            await skill_runtime.invoke("resume-coach", {
                "operation": "start",
                "entry": "explicit_request",
                "problem": "项目成果缺少证据",
            }, direct_context)

        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start",
            "entry": "explicit_request",
            "approval_quote": "请深入追问我的项目成果",
            "problem": "项目成果缺少证据",
        }, direct_context)
        self.assertTrue(started.active)

    async def test_dismisses_a_pending_start_offer(self):
        offered = await skill_runtime.invoke("resume-coach", {
            "operation": "offer_start", "problem": "需要更多事实",
        }, {**self.context, "explicit_command": False})
        offer_id = offered.coach_state.pending_start_offer.offer_id
        dismissed = await skill_runtime.invoke("resume-coach", {
            "operation": "dismiss_start", "offer_id": offer_id,
        }, {
            **self.context,
            "explicit_command": False,
            "coach_state": offered.coach_state.model_dump(),
        })
        self.assertFalse(dismissed.active)
        self.assertIsNone(dismissed.coach_state.pending_start_offer)

    async def test_active_session_rejects_duplicate_start_and_issue_switch(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start", "problem": "项目成果缺少证据",
        }, self.context)
        state = started.coach_state.model_dump()
        with self.assertRaises(ValueError):
            await skill_runtime.invoke("resume-coach", {
                "operation": "start", "problem": "另一个问题",
            }, {**self.context, "coach_state": state})
        with self.assertRaises(ValueError):
            await skill_runtime.invoke("resume-coach", {
                "operation": "update", "issue_id": "another-issue",
            }, {**self.context, "coach_state": state})

    async def test_user_correction_supersedes_old_evidence(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start",
            "problem": "项目成果数字需要核实",
            "evidence_candidates": [{
                "claim": "性能提升 20%",
                "source_quote": "性能提升 20%",
            }],
        }, {**self.context, "latest_user_message": "性能提升 20%"})
        state = started.coach_state.model_dump()
        issue_id = state["current_issue_id"]
        old_id = state["issues"][issue_id]["evidence"][0]["id"]
        corrected = await skill_runtime.invoke("resume-coach", {
            "operation": "update",
            "issue_id": issue_id,
            "supersede_evidence_ids": [old_id],
            "evidence_candidates": [{
                "claim": "性能提升 15%",
                "source_quote": "刚才说错了，实际提升是 15%。",
            }],
        }, {
            **self.context,
            "request_id": "request-2",
            "latest_user_message": "刚才说错了，实际提升是 15%。",
            "coach_state": state,
        })
        evidence = corrected.coach_state.issues[issue_id].evidence
        self.assertEqual(evidence[0].status, "superseded")
        self.assertEqual(evidence[0].superseded_by_request_id, "request-2")
        self.assertEqual(evidence[1].status, "active")

    def test_preview_operations_use_resume_edit_contract(self):
        with self.assertRaises(ValidationError):
            self.package.module.ResumeCoachToolInput.model_validate({
                "operation": "offer_preview",
                "proposal": {
                    "summary": "修正姓名",
                    "resume_operations": [{
                        "operation": "set",
                        "path": "basics.name",
                        "value": "新姓名",
                    }],
                },
            })

    async def test_complete_issue_marks_status_and_can_open_next_issue(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start", "problem": "项目经历缺少结果",
        }, self.context)
        state = started.coach_state.model_dump()
        issue_id = state["current_issue_id"]
        completed = await skill_runtime.invoke("resume-coach", {
            "operation": "complete_issue",
            "issue_id": issue_id,
            "result": "已完成证据整理",
            "next_problem": "项目经历缺少决策过程",
        }, {**self.context, "coach_state": state})
        completed_state = completed.coach_state.model_dump()
        self.assertTrue(completed.active)
        self.assertEqual(completed_state["issues"][issue_id]["status"], "completed")
        self.assertNotEqual(completed_state["current_issue_id"], issue_id)

        next_issue_id = completed_state["current_issue_id"]
        ended = await skill_runtime.invoke("resume-coach", {
            "operation": "complete_issue",
            "issue_id": next_issue_id,
            "completion_status": "skipped",
            "reason": "用户暂时跳过",
        }, {**self.context, "coach_state": completed_state})
        ended_state = ended.coach_state.model_dump()
        self.assertFalse(ended.active)
        self.assertEqual(ended_state["issues"][next_issue_id]["status"], "skipped")
        self.assertEqual(ended_state["current_issue_id"], "")

    async def test_undone_offer_blocks_completion_but_explicit_skip_can_continue(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start", "problem": "工作经历表述需要完善",
        }, self.context)
        state = started.coach_state.model_dump()
        issue_id = state["current_issue_id"]
        offered = await skill_runtime.invoke("resume-coach", {
            "operation": "offer_preview",
            "issue_id": issue_id,
            "proposal": {
                "summary": "完善工作经历",
                "resume_operations": [{
                    "op": "set",
                    "path": "basics.name",
                    "value": "新姓名",
                }],
            },
        }, {**self.context, "coach_state": state})
        undone_state = offered.coach_state.model_dump()
        undone_state["issues"][issue_id]["pending_preview_offer"]["status"] = "undone"

        with self.assertRaisesRegex(ValueError, "尚未完整应用或已被撤回"):
            await skill_runtime.invoke("resume-coach", {
                "operation": "complete_issue",
                "issue_id": issue_id,
                "next_problem": "教育经历需要完善",
            }, {**self.context, "coach_state": undone_state})

        skipped = await skill_runtime.invoke("resume-coach", {
            "operation": "complete_issue",
            "issue_id": issue_id,
            "completion_status": "skipped",
            "reason": "用户明确跳过",
            "next_problem": "教育经历需要完善",
        }, {**self.context, "coach_state": undone_state})
        skipped_state = skipped.coach_state.model_dump()
        self.assertEqual(skipped_state["issues"][issue_id]["status"], "skipped")
        self.assertNotEqual(skipped_state["current_issue_id"], issue_id)

    async def test_undone_offer_can_be_reauthorized_without_reoffering(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start", "problem": "工作经历表述需要完善",
        }, self.context)
        state = started.coach_state.model_dump()
        issue_id = state["current_issue_id"]
        offered = await skill_runtime.invoke("resume-coach", {
            "operation": "offer_preview",
            "issue_id": issue_id,
            "proposal": {
                "summary": "完善工作经历",
                "resume_operations": [{
                    "op": "set",
                    "path": "basics.name",
                    "value": "新姓名",
                }],
            },
        }, {**self.context, "coach_state": state})
        undone_state = offered.coach_state.model_dump()
        offer = undone_state["issues"][issue_id]["pending_preview_offer"]
        offer["status"] = "undone"

        reauthorized = await skill_runtime.invoke("resume-coach", {
            "operation": "handoff_to_edit",
            "issue_id": issue_id,
            "approval_quote": "重新生成同一条吧",
        }, {
            **self.context,
            "latest_user_message": "重新生成同一条吧",
            "coach_state": undone_state,
        })

        self.assertEqual(reauthorized.edit_handoff.offer_id, offer["offer_id"])
        self.assertEqual(
            reauthorized.coach_state.issues[issue_id].pending_preview_offer.status,
            "authorized",
        )
        self.assertEqual(
            [item.model_dump() for item in reauthorized.edit_handoff.resume_operations],
            offer["resume_operations"],
        )

        with self.assertRaisesRegex(ValueError, "不能重复创建或覆盖"):
            await skill_runtime.invoke("resume-coach", {
                "operation": "offer_preview",
                "issue_id": issue_id,
                "proposal": {
                    "summary": "重复建议",
                    "resume_operations": [{
                        "op": "set", "path": "basics.name", "value": "另一姓名",
                    }],
                },
            }, {**self.context, "coach_state": undone_state})

    async def test_exit_clears_pending_entry_offer_but_keeps_history(self):
        offered = await skill_runtime.invoke("resume-coach", {
            "operation": "offer_start", "problem": "需要更多事实",
        }, {**self.context, "explicit_command": False})
        exited = await skill_runtime.invoke("resume-coach", {
            "operation": "exit",
        }, {**self.context, "explicit_command": False,
            "coach_state": offered.coach_state.model_dump()})
        self.assertFalse(exited.active)
        self.assertIsNone(exited.coach_state.pending_start_offer)

    async def test_exit_marks_the_current_issue_skipped(self):
        started = await skill_runtime.invoke("resume-coach", {
            "operation": "start", "problem": "项目成果需要补充",
        }, self.context)
        issue_id = started.coach_state.current_issue_id
        exited = await skill_runtime.invoke("resume-coach", {
            "operation": "exit", "reason": "用户结束深度打磨",
        }, {**self.context, "coach_state": started.coach_state.model_dump()})
        self.assertFalse(exited.active)
        self.assertEqual(exited.coach_state.issues[issue_id].status, "skipped")
        self.assertEqual(
            exited.coach_state.issues[issue_id].result,
            "用户结束深度打磨",
        )

    def test_active_coach_bypasses_direct_edit_route(self):
        state = AgentState(
            messages=[], coach_required=True,
            coach_state={"active": True}, assistant_command="coaching",
        )
        self.assertEqual(entry_router(state), "conversation_llm")


if __name__ == "__main__":
    unittest.main()
