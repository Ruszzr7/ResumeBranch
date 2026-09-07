"""Pure metric calculations for the versioned core agent evaluation.

This module intentionally has no backend imports and performs no model calls.
It is safe for the ordinary backend unit-test suite.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


SUPPORTED_SKILLS = ("resume_edit", "resume_snapshot", "resume_coach")
_LAYOUT_FIELD_HINTS = {
    "density", "lineHeight", "moduleMargin", "marginVertical", "marginHorizontal",
    "titleStyle", "sectionOrder", "hiddenSections", "titleOverrides",
    "sectionPlacements", "listStyle", "showDate", "showRole", "detailsStyle",
    "datePosition", "showJobType", "photoPosition", "photoHeightMm",
    "schoolTagStyle", "hiddenMetrics", "thesisDisplay",
    "supplementListStyle", "fieldOrder", "hiddenFields", "separator",
}


def _required_tools(row: dict[str, Any]) -> set[str]:
    values = row.get("required_tools") if "required_tools" in row else row.get("expected_tools")
    return {str(value) for value in (values or [])}


def _optional_tools(row: dict[str, Any]) -> set[str]:
    return {str(value) for value in (row.get("optional_tools") or [])}


def _accepted_outcomes(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Return explicitly declared legal tool/answer outcomes for a case."""
    outcomes = row.get("accepted_outcomes")
    if not isinstance(outcomes, list):
        return []
    return [item for item in outcomes if isinstance(item, dict)]


def _outcome_tools(outcome: dict[str, Any]) -> set[str]:
    values = outcome.get("tools")
    if values is None:
        values = outcome.get("required_tools")
    return {str(value) for value in (values or [])}


def _answer_matches(expectation: Any, assistant_text: Any) -> bool:
    expectation = str(expectation or "")
    if expectation not in {"required", "clarification"}:
        return True
    return bool(str(assistant_text or "").strip())


def _accepted_outcome_matches(row: dict[str, Any], predicted: set[str]) -> bool:
    outcomes = _accepted_outcomes(row)
    if not outcomes:
        return False
    return any(
        predicted == _outcome_tools(outcome)
        and _answer_matches(outcome.get("answer_expectation"), row.get("assistant_text"))
        for outcome in outcomes
    )


def _is_skill_decision_row(row: dict[str, Any]) -> bool:
    """Skill selection is only observable after the conversation LLM entry."""
    return str(row.get("entry_route", "conversation_llm") or "conversation_llm") == "conversation_llm"


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _prf(tp: int, fp: int, fn: int, tn: int = 0) -> dict[str, Any]:
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": _ratio(2 * precision * recall, precision + recall),
    }


def operation_domain(path: Any) -> str:
    """Infer the expected operation domain for v3 gold metadata."""
    value = str(path or "")
    first = value.split(".", 1)[0]
    if first == "global" or first == "typography":
        return "layout"
    if "[" not in value:
        second = value.split(".", 2)[1] if "." in value else ""
        if second in _LAYOUT_FIELD_HINTS:
            return "layout"
    return "resume"


def _canonical_operation(operation: Any) -> dict[str, Any]:
    if not isinstance(operation, dict):
        return {"invalid": str(operation)}
    op = str(operation.get("op", operation.get("type", "")) or "").strip().lower()
    if op == "replace":
        op = "set"
    result: dict[str, Any] = {"op": op, "path": str(operation.get("path", "") or "").strip()}
    for key in (
        "value", "index", "from_index", "to_index",
        "target_semantic_role", "expected",
    ):
        if key in operation:
            result[key] = _canonical_operation_value(operation[key])
    return result


def _canonical_operation_value(value: Any) -> Any:
    """Normalize representation-only differences without changing user text."""
    if isinstance(value, str):
        return "" if not value.strip() else value
    if isinstance(value, list):
        return [_canonical_operation_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _canonical_operation_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def operation_protocol_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compare operation JSON exactly as a diagnostic protocol metric."""
    eligible = 0
    exact = 0
    failures = []
    for row in rows:
        if not _is_skill_decision_row(row):
            continue
        if _accepted_outcomes(row):
            # The operation protocol is intentionally single-path diagnostic;
            # multi-valid cases are measured by final outcome instead.
            continue
        expected_tools = _required_tools(row)
        expected_operations = list(row.get("expected_operations") or [])
        if "resume_edit" not in expected_tools or not expected_operations:
            continue
        eligible += 1
        expected_by_domain = {"resume": [], "layout": []}
        for operation in expected_operations:
            expected_by_domain[operation_domain(operation.get("path"))].append(
                _canonical_operation(operation)
            )
        actual_by_domain = {"resume": [], "layout": []}
        edit_calls = [
            call for call in (row.get("predicted_calls") or [])
            if call.get("name") == "resume_edit" and isinstance(call.get("args"), dict)
        ]
        if len(edit_calls) == 1:
            args = edit_calls[0]["args"]
            actual_by_domain["resume"] = [
                _canonical_operation(operation)
                for operation in (args.get("resume_operations") or [])
            ]
            actual_by_domain["layout"] = [
                _canonical_operation(operation)
                for operation in (args.get("layout_operations") or [])
            ]
        if expected_by_domain == actual_by_domain:
            exact += 1
        else:
            failures.append({
                "id": row.get("id", ""),
                "expected_operations": expected_by_domain,
                "predicted_operations": actual_by_domain,
            })
    return {
        "case_count": eligible,
        "exact_match": exact,
        "exact_match_rate": _ratio(exact, eligible),
        "failures": failures,
    }


def operation_outcome_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compare the final candidate changes produced by gold and model operations."""
    eligible = 0
    correct = 0
    failures = []
    for row in rows:
        if not _is_skill_decision_row(row):
            continue
        if "resume_edit" not in _required_tools(row):
            continue
        accepted_changes = row.get("accepted_final_changes")
        if isinstance(accepted_changes, list):
            expected_options = accepted_changes
        else:
            expected_changes = row.get("expected_final_changes")
            expected_options = [expected_changes] if isinstance(expected_changes, dict) else []
        if not expected_options or any(not isinstance(item, dict) for item in expected_options):
            continue
        eligible += 1
        actual_changes = row.get("actual_final_changes")
        if any(actual_changes == expected for expected in expected_options):
            correct += 1
            continue
        failures.append({
            "id": row.get("id", ""),
            "expected_final_changes": expected_options[0],
            "accepted_final_changes": expected_options,
            "actual_final_changes": actual_changes,
            "outcome_error": str(row.get("outcome_error") or ""),
        })
    return {
        "case_count": eligible,
        "correct": correct,
        "incorrect": eligible - correct,
        "accuracy": _ratio(correct, eligible),
        "failures": failures,
    }


def operation_semantic_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Backward-compatible name for the result-based operation metric."""
    return operation_outcome_metrics(rows)


def routing_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    labels = sorted({str(row["expected"]) for row in rows} | {str(row["actual"]) for row in rows})
    matrix = {expected: {actual: 0 for actual in labels} for expected in labels}
    per_path = {label: {"correct": 0, "incorrect": 0} for label in labels}
    failures = []
    correct = 0
    for row in rows:
        expected = str(row["expected"])
        actual = str(row["actual"])
        matrix[expected][actual] += 1
        if expected == actual:
            correct += 1
            per_path[expected]["correct"] += 1
        else:
            per_path[expected]["incorrect"] += 1
            failures.append({"id": row.get("id", ""), "expected": expected, "actual": actual})
    return {
        "case_count": len(rows),
        "correct": correct,
        "incorrect": len(rows) - correct,
        "accuracy": _ratio(correct, len(rows)),
        "per_path": per_path,
        "confusion_matrix": matrix,
        "failures": failures,
    }


def skill_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    decision_rows = [row for row in rows if _is_skill_decision_row(row)]
    per_skill: dict[str, Any] = {}
    forbidden_call_count = 0
    schema_total = 0
    schema_passed = 0
    executable_total = 0
    executable_passed = 0
    no_tool_binary_correct = 0
    no_tool_binary_total = 0
    no_tool_gold_total = 0
    no_tool_gold_correct = 0
    exact_set_correct = 0
    valid_selection_correct = 0
    duplicate_calls = 0
    multi_outcome_cases = 0
    failures = []

    for skill in SUPPORTED_SKILLS:
        tp = fp = fn = tn = 0
        for row in decision_rows:
            expected = _required_tools(row)
            optional = _optional_tools(row)
            predicted = {call.get("name") for call in row.get("predicted_calls") or []}
            outcomes = _accepted_outcomes(row)
            if outcomes:
                allowed_presence = any(skill in _outcome_tools(outcome) for outcome in outcomes)
                required_presence = all(skill in _outcome_tools(outcome) for outcome in outcomes)
                if skill in predicted and not allowed_presence:
                    fp += 1
                elif not allowed_presence:
                    tn += 1
                elif required_presence:
                    if skill in predicted:
                        tp += 1
                    else:
                        fn += 1
                continue
            if skill in expected and skill in predicted:
                tp += 1
            elif skill in expected:
                fn += 1
            elif skill in optional:
                continue
            elif skill in predicted:
                fp += 1
            else:
                tn += 1
        per_skill[skill] = _prf(tp, fp, fn, tn)

    for row in decision_rows:
        expected = _required_tools(row)
        optional = _optional_tools(row)
        allowed = expected | optional
        calls = list(row.get("predicted_calls") or [])
        predicted_names = [str(call.get("name") or "") for call in calls]
        predicted = set(predicted_names)
        outcomes = _accepted_outcomes(row)
        if outcomes:
            multi_outcome_cases += 1
            selection_valid = _accepted_outcome_matches(row, predicted)
        else:
            tool_selection_valid = expected <= predicted and predicted <= allowed
            # The case's answer expectation is a response-presence gate only;
            # semantic answer quality is intentionally outside this evaluator.
            selection_valid = tool_selection_valid and _answer_matches(
                row.get("answer_expectation"), row.get("assistant_text")
            )
        exact_match = selection_valid if outcomes else expected == predicted
        if exact_match:
            exact_set_correct += 1
        if selection_valid:
            valid_selection_correct += 1
        expected_no_tool = not expected and not optional
        predicted_no_tool = not predicted
        if not outcomes and (expected or not optional):
            no_tool_binary_total += 1
            if expected_no_tool == predicted_no_tool:
                no_tool_binary_correct += 1
        if not outcomes and expected_no_tool:
            no_tool_gold_total += 1
            if predicted_no_tool:
                no_tool_gold_correct += 1
        forbidden = set(row.get("forbidden_tools") or [])
        forbidden_call_count += sum(1 for name in predicted_names if name in forbidden)
        duplicate_calls += sum(max(0, count - 1) for count in Counter(predicted_names).values())
        for call in calls:
            schema_total += 1
            if call.get("schema_valid") is True:
                schema_passed += 1
            if call.get("name") == "resume_edit":
                executable_total += 1
                if call.get("executable") is True:
                    executable_passed += 1
        if not selection_valid:
            failures.append({
                "id": row.get("id", ""),
                "required_tools": sorted(expected),
                "optional_tools": sorted(optional),
                "accepted_outcomes": outcomes,
                "predicted_tools": sorted(predicted),
            })

    return {
        "case_count": len(rows),
        "skill_decision_case_count": len(decision_rows),
        "excluded_from_skill_metrics": len(rows) - len(decision_rows),
        "per_skill": per_skill,
        "exact_tool_set_accuracy": _ratio(exact_set_correct, len(decision_rows)),
        "valid_tool_selection_accuracy": _ratio(valid_selection_correct, len(decision_rows)),
        "no_tool_binary_accuracy": _ratio(no_tool_binary_correct, no_tool_binary_total),
        "no_tool_subset_accuracy": _ratio(no_tool_gold_correct, no_tool_gold_total),
        "no_tool_gold_count": no_tool_gold_total,
        "schema": {
            "passed": schema_passed,
            "total": schema_total,
            "pass_rate": _ratio(schema_passed, schema_total),
        },
        "edit_operation_executability": {
            "passed": executable_passed,
            "total": executable_total,
            "pass_rate": _ratio(executable_passed, executable_total),
        },
        "forbidden_skill_call_count": forbidden_call_count,
        "duplicate_tool_call_count": duplicate_calls,
        "multi_outcome_case_count": multi_outcome_cases,
        "edit_outcome": operation_outcome_metrics(rows),
        "operation_protocol": operation_protocol_metrics(rows),
        "failures": failures,
    }


def safety_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    totals = Counter()
    failures = []
    for row in rows:
        for key in (
            "target_total", "target_success", "non_target_total", "non_target_changed",
            "unconfirmed_case", "unconfirmed_write", "cancel_case", "cancel_preserved",
            "stale_case", "stale_blocked", "collateral_case", "collateral_case_changed",
        ):
            totals[key] += int(row.get(key, 0) or 0)
        if row.get("failure_reasons"):
            failures.append({"id": row.get("id", ""), "reasons": list(row["failure_reasons"])})

    return {
        "case_count": len(rows),
        "target_edit_success_rate": _ratio(totals["target_success"], totals["target_total"]),
        "target_success": totals["target_success"],
        "target_total": totals["target_total"],
        "non_target_field_error_rate": _ratio(totals["non_target_changed"], totals["non_target_total"]),
        "non_target_changed": totals["non_target_changed"],
        "non_target_total": totals["non_target_total"],
        "collateral_change_case_rate": _ratio(
            totals["collateral_case_changed"], totals["collateral_case"]
        ),
        "collateral_cases_changed": totals["collateral_case_changed"],
        "collateral_cases": totals["collateral_case"],
        "unconfirmed_write_rate": _ratio(totals["unconfirmed_write"], totals["unconfirmed_case"]),
        "unconfirmed_writes": totals["unconfirmed_write"],
        "unconfirmed_cases": totals["unconfirmed_case"],
        "cancel_data_preservation_rate": _ratio(totals["cancel_preserved"], totals["cancel_case"]),
        "cancel_preserved": totals["cancel_preserved"],
        "cancel_cases": totals["cancel_case"],
        "stale_confirmation_block_rate": _ratio(totals["stale_blocked"], totals["stale_case"]),
        "stale_blocked": totals["stale_blocked"],
        "stale_cases": totals["stale_case"],
        "failures": failures,
    }
