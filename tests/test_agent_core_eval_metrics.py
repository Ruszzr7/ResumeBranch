import unittest
from collections import Counter
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tests.agent_core_eval.total.metrics import (
    operation_outcome_metrics,
    operation_protocol_metrics,
    operation_semantic_metrics,
    routing_metrics,
    safety_metrics,
    skill_metrics,
)
from tests.agent_core_eval.total.run_eval import (
    EVAL_ROOT,
    FORBIDDEN_CASE_MARKERS,
    SYNTHETIC_PHOTO_DATA_URL,
    SYNTHETIC_RESUME,
    _base_state,
    _case_messages,
    _case_state_overrides,
    _load_cases,
    run_skill,
)


class AgentCoreEvalMetricTests(unittest.TestCase):
    def test_targeted_report_distinguishes_independent_and_merged_metrics(self):
        from tests.agent_core_eval.total.run_eval import _report

        online = {
            "dataset_id": "agent-core-total-600",
            "dataset_case_counts": {"routing": 200, "skill": 300, "safety": 100},
            "metrics": {"skill": skill_metrics([])},
            "cases": [],
            "run_scope": {
                "type": "targeted_rerun",
                "executed_case_count": 19,
                "merged_with_existing": False,
            },
        }
        independent = _report(None, online, results_dir=EVAL_ROOT / "total" / "results")
        self.assertIn("仅基于本轮案例，不代表 300 条 Skill 总集结果", independent)
        online["run_scope"]["merged_with_existing"] = True
        merged = _report(None, online, results_dir=EVAL_ROOT / "total" / "results")
        self.assertIn("其余案例沿用上一轮实际结果后重新计算总体指标", merged)

    def test_total_dataset_has_target_counts_and_unique_prompts(self):
        payload = _load_cases(EVAL_ROOT / "total" / "cases.json")
        self.assertEqual(
            {category: len(payload[category]) for category in ("routing", "skill", "safety")},
            {"routing": 200, "skill": 300, "safety": 100},
        )
        case_ids = [
            case["id"]
            for category in ("routing", "skill", "safety")
            for case in payload[category]
        ]
        prompts = [case["prompt"].strip() for case in payload["routing"] + payload["skill"] + payload["safety"]]
        self.assertEqual(len(case_ids), 600)
        self.assertEqual(len(set(case_ids)), 600)
        self.assertEqual(len(prompts), len(set(prompts)))
        self.assertEqual(sum(case.get("smoke") is True for case in payload["skill"]), 20)
        self.assertEqual(
            payload["scenario_counts"],
            {
                "legacy_unclassified": 300,
                "complex_operation": 101,
                "mixed_request": 53,
                "ambiguous_request": 91,
                "multi_turn_summary": 55,
            },
        )

    def test_v4_hard_intent_gold_matches_case_content(self):
        total = _load_cases(EVAL_ROOT / "total" / "cases.json")
        prefixes = {"routing": "route-v4-", "skill": "skill-v4-", "safety": "safe-v4-"}
        payload = {
            category: [
                case for case in total[category]
                if case["id"].startswith(prefix)
            ]
            for category, prefix in prefixes.items()
        }
        payload["scenario_counts"] = dict(Counter(
            case.get("scenario_type") or "legacy_unclassified"
            for category in ("routing", "skill", "safety")
            for case in payload[category]
        ))
        self.assertEqual(
            {category: len(payload[category]) for category in ("routing", "skill", "safety")},
            {"routing": 59, "skill": 66, "safety": 25},
        )
        self.assertEqual(
            payload["scenario_counts"],
            {
                "complex_operation": 61,
                "mixed_request": 18,
                "ambiguous_request": 56,
                "multi_turn_summary": 15,
            },
        )
        edit_cases = [
            case for case in payload["skill"]
            if case.get("expected_tools") == ["resume_edit"]
            and not case.get("optional_tools")
        ]
        self.assertEqual(len(edit_cases), 26)
        self.assertTrue(all(case["scenario_type"] == "complex_operation" for case in edit_cases))
        contact_case = next(case for case in payload["skill"] if case["id"] == "skill-v4-052")
        self.assertEqual(contact_case["expected_tools"], ["resume_snapshot"])
        self.assertEqual(contact_case["forbidden_tools"], ["resume_edit"])

    def test_total_dataset_routes_mixed_unresolved_edits_to_conversation(self):
        payload = _load_cases(EVAL_ROOT / "total" / "cases.json")
        from tests.agent_core_eval.total.run_eval import _route_state
        from backend.resume_agent import entry_router

        mismatches = {
            case["id"]
            for case in payload["routing"]
            if (
                "confirm_endpoint" if case.get("confirmation")
                else entry_router(_route_state(case))
            ) != case["expected_route"]
        }
        self.assertEqual(mismatches, set())

    def test_datasets_exclude_markers_that_bias_integrity_responses(self):
        text = (EVAL_ROOT / "total" / "cases.json").read_text(encoding="utf-8")
        for marker in FORBIDDEN_CASE_MARKERS:
            self.assertNotIn(marker, text)

    def test_photo_fixture_is_scoped_to_photo_cases(self):
        photo_state = _case_state_overrides({"fixture": "photo"})
        normal_state = _case_state_overrides({})
        self.assertEqual(photo_state["photo"], SYNTHETIC_PHOTO_DATA_URL)
        self.assertEqual(photo_state["resume_data"]["basics"]["photo"], SYNTHETIC_PHOTO_DATA_URL)
        self.assertNotIn("photo", normal_state)
        self.assertEqual(SYNTHETIC_RESUME["basics"]["photo"], "")

    def test_v3_hard_gpa_noop_is_not_labeled_as_an_operation(self):
        payload = _load_cases(EVAL_ROOT / "total" / "cases.json")
        case = next(item for item in payload["skill"] if item["id"] == "skill-v3-016")
        paths = {operation["path"] for operation in case["expected_operations"]}
        self.assertEqual(paths, {"education[0].major", "education[0].gpa"})

    def test_routing_accuracy_per_path_and_confusion_matrix(self):
        result = routing_metrics([
            {"id": "r1", "expected": "conversation_llm", "actual": "conversation_llm"},
            {"id": "r2", "expected": "direct_edit", "actual": "conversation_llm"},
            {"id": "r3", "expected": "direct_edit", "actual": "direct_edit"},
        ])
        self.assertEqual(result["correct"], 2)
        self.assertAlmostEqual(result["accuracy"], 2 / 3)
        self.assertEqual(result["per_path"]["direct_edit"], {"correct": 1, "incorrect": 1})
        self.assertEqual(result["confusion_matrix"]["direct_edit"]["conversation_llm"], 1)

    def test_skill_metrics_are_multilabel_and_case_based(self):
        result = skill_metrics([
            {
                "id": "s1",
                "expected_tools": ["resume_edit"],
                "forbidden_tools": ["resume_snapshot"],
                "predicted_calls": [{
                    "name": "resume_edit", "schema_valid": True, "executable": True,
                }],
            },
            {
                "id": "s2",
                "expected_tools": ["resume_snapshot"],
                "forbidden_tools": ["resume_edit"],
                "predicted_calls": [
                    {"name": "resume_snapshot", "schema_valid": True},
                    {"name": "resume_edit", "schema_valid": False, "executable": False},
                ],
            },
            {
                "id": "s3", "expected_tools": [],
                "forbidden_tools": ["resume_edit", "resume_snapshot"],
                "predicted_calls": [],
            },
        ])
        edit = result["per_skill"]["resume_edit"]
        self.assertEqual((edit["tp"], edit["fp"], edit["fn"]), (1, 1, 0))
        self.assertEqual(result["forbidden_skill_call_count"], 1)
        self.assertAlmostEqual(result["schema"]["pass_rate"], 2 / 3)
        self.assertEqual(result["no_tool_subset_accuracy"], 1.0)

    def test_skill_metrics_accept_optional_tools_without_false_positive(self):
        result = skill_metrics([{
            "id": "optional-1",
            "required_tools": ["resume_edit"],
            "optional_tools": ["resume_snapshot"],
            "predicted_calls": [
                {"name": "resume_snapshot", "schema_valid": True},
                {"name": "resume_edit", "schema_valid": True, "executable": True},
            ],
        }])
        self.assertEqual(result["valid_tool_selection_accuracy"], 1.0)
        self.assertEqual(result["exact_tool_set_accuracy"], 0.0)
        self.assertEqual(
            result["per_skill"]["resume_snapshot"],
            {"tp": 0, "fp": 0, "fn": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0},
        )

    def test_skill_metrics_accept_explicit_multi_valid_outcomes(self):
        result = skill_metrics([{
            "id": "multi-1",
            "required_tools": ["resume_edit"],
            "predicted_calls": [],
            "assistant_text": "当前技能顺序可以结合岗位要求再确认，你希望保留 Redis 吗？",
            "accepted_outcomes": [
                {"tools": ["resume_edit"], "answer_expectation": "required"},
                {"tools": [], "answer_expectation": "clarification"},
            ],
        }])
        self.assertEqual(result["valid_tool_selection_accuracy"], 1.0)
        self.assertEqual(result["exact_tool_set_accuracy"], 1.0)
        self.assertEqual(result["multi_outcome_case_count"], 1)
        self.assertEqual(
            result["per_skill"]["resume_edit"],
            {"tp": 0, "fp": 0, "fn": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0},
        )

    def test_skill_selection_requires_declared_answer_when_expected(self):
        missing = skill_metrics([{
            "id": "answer-required-missing",
            "expected_tools": [],
            "answer_expectation": "required",
            "predicted_calls": [],
            "assistant_text": "",
        }])
        present = skill_metrics([{
            "id": "answer-required-present",
            "expected_tools": [],
            "answer_expectation": "required",
            "predicted_calls": [],
            "assistant_text": "教育经历应保留与目标岗位相关的信息。",
        }])
        self.assertEqual(missing["valid_tool_selection_accuracy"], 0.0)
        self.assertEqual(present["valid_tool_selection_accuracy"], 1.0)

    def test_safety_rates_use_explicit_denominators(self):
        result = safety_metrics([
            {
                "id": "m1", "target_total": 2, "target_success": 2,
                "non_target_total": 10, "non_target_changed": 1,
                "unconfirmed_case": 1, "unconfirmed_write": 0,
                "collateral_case": 1, "collateral_case_changed": 1,
            },
            {
                "id": "m2", "cancel_case": 1, "cancel_preserved": 1,
                "stale_case": 1, "stale_blocked": 1,
            },
        ])
        self.assertEqual(result["target_edit_success_rate"], 1.0)
        self.assertEqual(result["non_target_field_error_rate"], 0.1)
        self.assertEqual(result["unconfirmed_write_rate"], 0.0)
        self.assertEqual(result["cancel_data_preservation_rate"], 1.0)
        self.assertEqual(result["stale_confirmation_block_rate"], 1.0)

    def test_operation_outcomes_compare_final_candidate_changes(self):
        rows = [{
            "id": "op-1",
            "expected_tools": ["resume_edit"],
            "expected_final_changes": {
                "resume.basics.name": {"before": "林沐辰", "after": "宋知遥"},
            },
            "actual_final_changes": {
                "resume.basics.name": {"before": "林沐辰", "after": "宋知遥"},
            },
        }, {
            "id": "op-2",
            "expected_tools": ["resume_edit"],
            "expected_final_changes": {
                "resume.basics.name": {"before": "林沐辰", "after": "宋知遥"},
            },
            "actual_final_changes": {},
        }]
        result = operation_outcome_metrics(rows)
        self.assertEqual(result["case_count"], 2)
        self.assertEqual(result["correct"], 1)
        self.assertAlmostEqual(result["accuracy"], 0.5)
        self.assertEqual([item["id"] for item in result["failures"]], ["op-2"])

    def test_operation_outcomes_ignore_extra_noop_operations(self):
        result = operation_semantic_metrics([{
            "id": "op-noop-1",
            "required_tools": ["resume_edit"],
            "expected_final_changes": {
                "resume.education[0].gpa": {"before": "3.6", "after": "3.8"},
            },
            "actual_final_changes": {
                "resume.education[0].gpa": {"before": "3.6", "after": "3.8"},
            },
        }])
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["failures"], [])

    def test_operation_outcomes_accept_multiple_final_states(self):
        result = operation_outcome_metrics([{
            "id": "op-multi",
            "required_tools": ["resume_edit"],
            "accepted_final_changes": [
                {"resume.others.skills": {"before": ["Python"], "after": ["Python", "Redis"]}},
                {},
            ],
            "actual_final_changes": {},
        }])
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["failures"], [])

    def test_operation_protocol_remains_available_as_diagnostic(self):
        result = operation_protocol_metrics([{
            "id": "op-empty-equivalent",
            "required_tools": ["resume_edit"],
            "expected_operations": [{
                "op": "set", "path": "basics.name", "value": "   ",
            }],
            "predicted_calls": [{
                "name": "resume_edit",
                "args": {
                    "resume_operations": [{
                        "op": "replace", "path": "basics.name", "value": "",
                    }],
                    "layout_operations": [],
                },
            }],
        }])
        self.assertEqual(result["exact_match"], 1)
        self.assertEqual(result["failures"], [])


class AgentCoreEvalRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_skill_cases_enter_the_llm_decision_boundary(self):
        from backend.resume_agent import entry_router

        payload = _load_cases(EVAL_ROOT / "total" / "cases.json")
        self.assertTrue(all(
            case.get("expected_route", "conversation_llm") == "conversation_llm"
            for case in payload["skill"]
        ))
        self.assertTrue(all(
            entry_router(_base_state(
                case["prompt"],
                messages=_case_messages(case),
                **_case_state_overrides(case),
            )) == "conversation_llm"
            for case in payload["skill"]
        ))

    async def test_all_skill_operation_gold_is_executable(self):
        from tests.agent_core_eval.total.run_eval import _expected_operation_changes

        payload = _load_cases(EVAL_ROOT / "total" / "cases.json")
        operation_cases = [case for case in payload["skill"] if case.get("expected_operations")]
        self.assertEqual(len(operation_cases), 72)
        for case in operation_cases:
            with self.subTest(case_id=case["id"]):
                self.assertIsInstance(await _expected_operation_changes(case), dict)

    async def test_equivalent_list_operations_have_the_same_final_changes(self):
        from tests.agent_core_eval.total.run_eval import _operation_changes

        moved = await _operation_changes([{
            "op": "move",
            "path": "project_experience[0].content_blocks[1].items",
            "from_index": 1,
            "to_index": 0,
        }], [])
        replaced = await _operation_changes([{
            "op": "set",
            "path": "project_experience[0].content_blocks[1].items",
            "value": ["为核心接口补充自动化测试", "设计文档权限校验接口"],
        }], [])
        self.assertEqual(moved, replaced)

    async def test_skill_runner_collects_the_complete_graph_tool_trace(self):
        messages = [
            HumanMessage(content="问题加修改"),
            AIMessage(content="", tool_calls=[{
                "name": "resume_snapshot", "args": {}, "id": "render-1",
            }]),
            ToolMessage(content="已附加快照", tool_call_id="render-1", name="resume_snapshot"),
            AIMessage(content="", tool_calls=[{
                "name": "resume_edit",
                "args": {
                    "answer_text": "教育经历可以压缩次要信息。",
                    "resume_operations": [{
                        "op": "set", "path": "education[0].major", "value": "软件工程",
                    }],
                    "layout_operations": [],
                },
                "id": "edit-1",
            }]),
            ToolMessage(content="已生成修改预览", tool_call_id="edit-1", name="resume_edit"),
            AIMessage(content="教育经历可以压缩次要信息。\n\n已生成修改预览。"),
        ]
        with (
            patch("tests.agent_core_eval.total.run_eval.LLM_ENABLED", True),
            patch("tests.agent_core_eval.total.run_eval.graph.ainvoke", new=AsyncMock(return_value={"messages": messages})),
            patch("tests.agent_core_eval.total.run_eval._validate_call", new=AsyncMock(return_value=(True, True, ""))),
        ):
            rows, metrics = await run_skill([{
                "id": "skill-trace-1",
                "prompt": "问题加修改",
                "required_tools": ["resume_edit"],
                "optional_tools": ["resume_snapshot"],
            }], mode="online")
        self.assertEqual(
            [call["name"] for call in rows[0]["predicted_calls"]],
            ["resume_snapshot", "resume_edit"],
        )
        self.assertIn("教育经历可以压缩次要信息", rows[0]["assistant_text"])
        self.assertEqual(metrics["valid_tool_selection_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
