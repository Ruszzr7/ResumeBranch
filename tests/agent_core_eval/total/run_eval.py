"""Run ResumeBranch core agent evaluations without changing production code.

Offline mode is deterministic and never calls an LLM. Smoke and online modes
use the locally configured chat profile through the production conversation
graph, execute its tool loop, and stop at the normal graph boundary. Resume
edits remain preview-only and never persist without confirmation.
"""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_core.messages import AIMessage, HumanMessage

from backend.layout_config import apply_layout_change_groups, default_layout_config, normalize_layout_config
from backend.resume_agent import (
    AgentState,
    LLM_ENABLED,
    LLM_MODEL,
    LLM_PROVIDER,
    entry_router,
    graph,
    make_pending_confirmation,
    resume_snapshot_tool,
    resume_edit_tool,
)
from backend.resume_changes import (
    apply_resume_changes,
    build_resume_state_version,
    resume_state_version_matches,
)
from backend.resume_schema import validate_resume_data
from backend.skill_runtime import skill_runtime

_resume_edit_module = skill_runtime.get("resume-edit").module
ResumeEditRequest = _resume_edit_module.ResumeEditRequest
run_resume_edit = _resume_edit_module.run_resume_edit
from tests.agent_core_eval.total.metrics import (
    operation_domain,
    routing_metrics,
    safety_metrics,
    skill_metrics,
)


HERE = Path(__file__).resolve().parent
EVAL_ROOT = HERE.parent
CASES_PATH = HERE / "cases.json"
EXPECTED_COUNTS = {"routing": 200, "skill": 400, "safety": 100}
FORBIDDEN_CASE_MARKERS = ("虚构", "虚假", "伪造", "捏造", "测试信息")
TOOLS = {
    resume_edit_tool.name: resume_edit_tool,
    resume_snapshot_tool.name: resume_snapshot_tool,
}


SYNTHETIC_RESUME = {
    "formatting_version": 4,
    "basics": {
        "name": "林沐辰", "gender": "女", "birth_date": "2001.04",
        "phone": "13900001234", "email": "lin.muchen@example.test",
        "target_position": "后端开发工程师", "photo": "", "additional_fields": [],
    },
    "education": [{
        "school_name": "海岚大学", "major": "计算机科学与技术", "degree": "本科",
        "date_range": ["2020.09", "2024.06"], "school_tags": ["示例院校"],
        "gpa": "3.6", "gpa_scale": "4.0", "ranking": "前15%", "theses": [],
    }],
    "education_supplement": ["主修数据结构、操作系统与数据库系统"],
    "research_interests": [],
    "honors": ["2023 年海岚大学创新实践奖"],
    "publications": [],
    "work_experience": [{
        "company_name": "星桥科技有限公司", "job_title": "后端开发实习生",
        "date_range": ["2023.07", "2023.12"], "job_type": "实习",
        "content_blocks": [{
            "type": "bullet_list", "semantic_role": "responsibilities", "label": "工作职责",
            "label_bold": True, "text": "", "items": [
                "参与订单服务接口开发与单元测试",
                "整理接口文档并协助定位慢查询",
            ],
        }, {
            "type": "bullet_list", "semantic_role": "generic", "label": "",
            "label_bold": False, "text": "", "items": [
                "协助团队进行接口质量复盘",
            ],
        }],
    }],
    "project_experience": [{
        "project_name": "云笺协作平台", "role": "后端开发",
        "date_range": ["2023.02", "2023.06"],
        "content_blocks": [
            {"type": "paragraph", "semantic_role": "tech_stack", "label": "技术栈", "label_bold": True, "text": "Python、FastAPI、PostgreSQL", "items": []},
            {"type": "bullet_list", "semantic_role": "responsibilities", "label": "项目职责", "label_bold": True, "text": "", "items": ["设计文档权限校验接口", "为核心接口补充自动化测试"]},
            {"type": "bullet_list", "semantic_role": "generic", "label": "", "label_bold": False, "text": "", "items": ["参与项目复盘与文档整理"]},
        ],
    }],
    "custom_sections": [],
    "others": {"skills": ["Python", "SQL", "Git"], "certificates": ["云计算基础认证"], "languages": ["英语 CET-6"]},
    "self_evaluation": ["注重代码质量，能够持续复盘并推动问题闭环"],
}

# A small, locally generated neutral avatar used only by the photo-layout
# cases.  It is intentionally kept out of the default fixture so no-photo
# behavior remains testable for the other cases.
SYNTHETIC_PHOTO_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABQCAIAAAAm3eQSAAABLElEQVR42u2ZzQ3CMAxGU4slEAuwD3ckxgDO0DGQuLMPCyA4cWACBqCHNP5pQ16OVWV/L3Zbp1/3en9SzUtS5QsAAAAAAIC2ARZOcR+38+/F1eZgnqgzHyUGpfthSLD6zHsmqECBLJNS8BZSdIVJL8lU6q0Ymm8h/RYqI/AQAwAAAHUD6OcZZQRaSLeF+gLaVKBMB+O0w5Eyc7AxPFUaVyBHme2ZuHPyByr+K5Eq+i+0PV2sdFyPu9AKDErv18/8CPv70gRDpt14fWSZj/qy+DIr9QVZZG7qx+ZqZhqN3P5RGTkPAJDwyMzW4HRABQAAAAAAAAAAAAAAAAAAAAAAAIC2AYotoORsOrXUQpFFyM8lMV6iXxYJ80Od4kukp+sRWeXUV2x08yED4G8AvvS6bBAZO5UsAAAAAElFTkSuQmCC"
)

SYNTHETIC_JD = {
    "company": "远帆数据有限公司", "position": "Python 后端开发工程师",
    "department": "平台研发部", "location": "杭州", "job_type": "全职",
    "salary": "", "description": "负责业务接口、数据库性能与自动化质量保障。",
    "requirements": {
        "education": "本科", "experience": "1 年以上项目经验",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis"], "language": "",
    },
    "preferred_qualifications": ["具备性能优化经验"],
    "highlights": ["接口性能", "数据一致性", "自动化测试"],
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cases(cases_path: Path = CASES_PATH) -> dict[str, Any]:
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("不支持的评测数据 schema_version")
    configured_counts = payload.get("case_counts") or EXPECTED_COUNTS
    if not isinstance(configured_counts, dict):
        raise ValueError("评测数据 case_counts 必须是对象")
    expected_counts = {}
    for category, default_count in EXPECTED_COUNTS.items():
        value = configured_counts.get(category, default_count)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{category} 案例数必须是非负整数")
        expected_counts[category] = value
    all_ids: list[str] = []
    for category, expected_count in expected_counts.items():
        cases = payload.get(category)
        if not isinstance(cases, list) or len(cases) != expected_count:
            raise ValueError(f"{category} 案例数必须为 {expected_count}")
        for case in cases:
            case_id = str(case.get("id") or "")
            if not case_id.startswith({"routing": "route-", "skill": "skill-", "safety": "safe-"}[category]):
                raise ValueError(f"案例 ID 与分类不匹配：{case_id}")
            all_ids.append(case_id)
    total_count = sum(expected_counts.values())
    if len(all_ids) != total_count or len(set(all_ids)) != total_count:
        raise ValueError(f"评测集必须包含 {total_count} 个唯一案例 ID")
    serialized = json.dumps(payload, ensure_ascii=False)
    found_markers = [marker for marker in FORBIDDEN_CASE_MARKERS if marker in serialized]
    if found_markers:
        raise ValueError(f"评测集包含会干扰模型判断的标识：{', '.join(found_markers)}")
    fixture_text = json.dumps({"resume": SYNTHETIC_RESUME, "jd": SYNTHETIC_JD}, ensure_ascii=False)
    fixture_markers = [marker for marker in FORBIDDEN_CASE_MARKERS if marker in fixture_text]
    if fixture_markers:
        raise ValueError(f"匿名评测上下文包含会干扰模型判断的标识：{', '.join(fixture_markers)}")
    smoke = [case for case in payload["skill"] if case.get("smoke") is True]
    smoke_count = payload.get("smoke_case_count", 5)
    if isinstance(smoke_count, bool) or not isinstance(smoke_count, int) or smoke_count < 0:
        raise ValueError("在线 Smoke 数量必须是非负整数")
    if len(smoke) != smoke_count:
        raise ValueError(f"在线 Smoke 子集必须恰好为 {smoke_count} 条")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _base_state(prompt: str, **overrides: Any) -> AgentState:
    values = {
        "messages": [HumanMessage(content=prompt)],
        "resume_data": deepcopy(SYNTHETIC_RESUME),
        "jd_data": deepcopy(SYNTHETIC_JD),
        "layout_data": default_layout_config(),
        "pending_confirmation": None,
        "user_id": 9001,
        "task_id": "synthetic-agent-eval",
        "context_type": "main",
        "coach_state": {},
        "coach_required": False,
        "assistant_command": "",
        "context_metadata": {},
        "request_id": "synthetic-eval",
    }
    values.update(overrides)
    return AgentState(**values)


def _case_state_overrides(case: dict[str, Any]) -> dict[str, Any]:
    """Apply only the fixture explicitly requested by a test case."""
    overrides = dict(case.get("state") or {})
    if case.get("fixture") == "photo":
        fixture_resume = deepcopy(SYNTHETIC_RESUME)
        fixture_resume["basics"]["photo"] = SYNTHETIC_PHOTO_DATA_URL
        overrides.setdefault("resume_data", fixture_resume)
        overrides.setdefault("photo", SYNTHETIC_PHOTO_DATA_URL)
    return overrides


def _case_messages(case: dict[str, Any], *, prompt: str | None = None) -> list[Any]:
    """Build the real conversation history for a case with optional prior turns."""
    messages: list[Any] = []
    for turn in case.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "")
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=str(prompt if prompt is not None else case["prompt"])))
    return messages


def _route_state(case: dict[str, Any]) -> AgentState:
    overrides = _case_state_overrides(case)
    prompt = str(case["prompt"])
    return _base_state(prompt, messages=_case_messages(case, prompt=prompt), **overrides)


def run_routing(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for case in cases:
        actual = "confirm_endpoint" if case.get("confirmation") else entry_router(_route_state(case))
        rows.append({
            "id": case["id"], "prompt": case["prompt"],
            "expected": case["expected_route"], "actual": actual,
        })
    return rows, routing_metrics(rows)


def _tokens(path: str) -> list[str | int]:
    result: list[str | int] = []
    for segment in path.split("."):
        head = segment.split("[")[0]
        result.append(head)
        rest = segment[len(head):]
        while rest:
            close = rest.index("]")
            result.append(int(rest[1:close]))
            rest = rest[close + 1:]
    return result


def _get_path(root: Any, path: str) -> Any:
    current = root
    for token in _tokens(path):
        current = current[token]
    return current


def _set_path(root: Any, path: str, value: Any) -> None:
    tokens = _tokens(path)
    current = root
    for token in tokens[:-1]:
        current = current[token]
    current[tokens[-1]] = deepcopy(value)


def _flatten(root: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(root, dict):
        result: dict[str, Any] = {}
        for key, value in root.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(value, child))
        return result
    if isinstance(root, list):
        result = {}
        for index, value in enumerate(root):
            result.update(_flatten(value, f"{prefix}[{index}]"))
        if not root:
            result[prefix] = []
        return result
    return {prefix: root}


def _combined(resume: dict, layout: dict) -> dict[str, Any]:
    return {"resume": validate_resume_data(resume), "layout": normalize_layout_config(layout)}


_MISSING_CHANGE_VALUE = {"__agent_eval_missing__": True}


def _final_change_map(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Return only observable final-state differences, independent of operation form."""
    before_flat = _flatten(before)
    after_flat = _flatten(after)
    changes: dict[str, Any] = {}
    for path in sorted(set(before_flat) | set(after_flat)):
        before_value = before_flat.get(path, _MISSING_CHANGE_VALUE)
        after_value = after_flat.get(path, _MISSING_CHANGE_VALUE)
        if before_value != after_value:
            changes[path] = {
                "before": deepcopy(before_value),
                "after": deepcopy(after_value),
            }
    return changes


def _collateral_counts(before: dict[str, Any], after: dict[str, Any], target_paths: set[str]) -> tuple[int, int]:
    before_flat = _flatten(before)
    after_flat = _flatten(after)
    paths = set(before_flat) | set(after_flat)

    def targeted(path: str) -> bool:
        return any(
            path == target or path.startswith(target + ".") or path.startswith(target + "[")
            for target in target_paths
        )

    checked = [path for path in paths if not targeted(path)]
    changed = sum(1 for path in checked if before_flat.get(path, object()) != after_flat.get(path, object()))
    return len(checked), changed


async def run_safety(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for case in cases:
        before_resume = validate_resume_data(deepcopy(SYNTHETIC_RESUME))
        before_layout = normalize_layout_config(default_layout_config())
        base_state = _base_state(case["prompt"], resume_data=before_resume, layout_data=before_layout)
        request = ResumeEditRequest(
            resume_data=before_resume,
            layout_config=before_layout,
            resume_operations=tuple(case.get("resume_operations") or ()),
            layout_operations=tuple(case.get("layout_operations") or ()),
            base_version=build_resume_state_version(before_resume, before_layout),
        )
        failure_reasons: list[str] = []
        with patch("backend.database.commit_resume_mutation") as commit_mutation:
            edit_result = await run_resume_edit(request)
            candidate_resume = edit_result.resume_data
            candidate_layout = edit_result.layout_config
            pending = make_pending_confirmation(base_state, candidate_resume, candidate_layout)
            writes_before_confirmation = commit_mutation.call_count
            before_combined = _combined(before_resume, before_layout)
            candidate_combined = _combined(candidate_resume, candidate_layout)
            targets = dict(case.get("expected_changes") or {})
            non_target_total, non_target_changed = _collateral_counts(
                before_combined, candidate_combined, set(targets)
            )
            if non_target_changed:
                failure_reasons.append(f"候选数据改动了 {non_target_changed} 个非目标叶子字段")

            phase = case["phase"]
            final_resume = before_resume
            final_layout = before_layout
            target_observation = candidate_combined
            cancel_preserved = stale_blocked = 0
            if phase in {"confirm", "cancel", "stale"}:
                live_resume = deepcopy(before_resume)
                live_layout = deepcopy(before_layout)
                if phase == "stale":
                    mutation = case["stale_mutation"]
                    mutation_target = (
                        live_layout
                        if operation_domain(mutation["path"]) == "layout"
                        else live_resume
                    )
                    _set_path(mutation_target, mutation["path"], mutation["value"])
                changes = list(pending["changes"])
                has_layout = any(item.get("kind") == "layout" for item in changes)
                has_content = any(item.get("kind") != "layout" for item in changes)
                version_matches = resume_state_version_matches(
                    pending["base_version"], live_resume, live_layout,
                    check_content=has_content, check_layout=has_layout,
                )
                if phase == "confirm":
                    change_ids = [item["id"] for item in changes]
                    final_resume = validate_resume_data(apply_resume_changes(
                        live_resume,
                        [item for item in changes if item.get("kind") != "layout"],
                        change_ids,
                    ))
                    final_layout = apply_layout_change_groups(
                        live_layout, candidate_layout, change_ids,
                    )
                    target_observation = _combined(final_resume, final_layout)
                elif phase == "cancel":
                    cancel_preserved = int(
                        validate_resume_data(live_resume) == before_resume
                        and normalize_layout_config(live_layout) == before_layout
                        and commit_mutation.call_count == 0
                    )
                    if not cancel_preserved:
                        failure_reasons.append("取消后正式数据或持久化调用发生变化")
                else:
                    stale_blocked = int(
                        commit_mutation.call_count == 0
                        and not version_matches
                    )
                    if not stale_blocked:
                        failure_reasons.append("过期确认未被确定性拦截")

            measure_target = phase in {"candidate", "isolation", "confirm"}
            target_success = 0
            if measure_target:
                for path, expected in targets.items():
                    try:
                        actual = _get_path(target_observation, path)
                    except (KeyError, IndexError, TypeError):
                        actual = object()
                    if actual == expected:
                        target_success += 1
                    else:
                        failure_reasons.append(f"目标字段未达到预期：{path}")
            if writes_before_confirmation:
                failure_reasons.append("确认前发生持久化调用")
            rows.append({
                "id": case["id"], "phase": phase,
                "target_total": len(targets) if measure_target else 0,
                "target_success": target_success,
                "non_target_total": non_target_total,
                "non_target_changed": non_target_changed,
                "collateral_case": 1,
                "collateral_case_changed": int(non_target_changed > 0),
                "unconfirmed_case": 1,
                "unconfirmed_write": int(writes_before_confirmation > 0),
                "cancel_case": int(phase == "cancel"),
                "cancel_preserved": cancel_preserved,
                "stale_case": int(phase == "stale"),
                "stale_blocked": stale_blocked,
                "failure_reasons": failure_reasons,
            })
    return rows, safety_metrics(rows)


def _tool_call_value(call: Any, key: str, default: Any = None) -> Any:
    if isinstance(call, dict):
        return call.get(key, default)
    return getattr(call, key, default)


async def _validate_call(name: str, args: Any) -> tuple[bool, bool | None, str]:
    tool = TOOLS.get(name)
    if tool is None or not isinstance(args, dict):
        return False, None, "未知工具或参数不是对象"
    try:
        tool.args_schema.model_validate(args)
    except Exception as exc:
        return False, None, f"Schema: {type(exc).__name__}"
    if name != "resume_edit":
        return True, None, ""
    try:
        await run_resume_edit(ResumeEditRequest(
            resume_data=deepcopy(SYNTHETIC_RESUME),
            layout_config=default_layout_config(),
            resume_operations=tuple(args.get("resume_operations") or ()),
            layout_operations=tuple(args.get("layout_operations") or ()),
            base_version=build_resume_state_version(
                validate_resume_data(SYNTHETIC_RESUME), default_layout_config()
            ),
        ))
    except Exception as exc:
        return True, False, f"Executable: {type(exc).__name__}: {str(exc)}"
    return True, True, ""


async def _operation_changes(
    resume_operations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    layout_operations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    before_resume = validate_resume_data(deepcopy(SYNTHETIC_RESUME))
    before_layout = normalize_layout_config(default_layout_config())
    result = await run_resume_edit(ResumeEditRequest(
        resume_data=before_resume,
        layout_config=before_layout,
        resume_operations=tuple(resume_operations or ()),
        layout_operations=tuple(layout_operations or ()),
        base_version=build_resume_state_version(before_resume, before_layout),
    ))
    return _final_change_map(
        _combined(before_resume, before_layout),
        _combined(result.resume_data, result.layout_config),
    )


async def _expected_operation_changes(case: dict[str, Any]) -> dict[str, Any] | None:
    operations = list(case.get("expected_operations") or [])
    if not operations:
        return None
    resume_operations = [
        operation for operation in operations
        if operation_domain(operation.get("path")) == "resume"
    ]
    layout_operations = [
        operation for operation in operations
        if operation_domain(operation.get("path")) == "layout"
    ]
    return await _operation_changes(resume_operations, layout_operations)


async def _accepted_operation_changes(case: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Build final-change alternatives for a multi-valid case."""
    outcomes = case.get("accepted_outcomes")
    if not isinstance(outcomes, list):
        return None
    result: list[dict[str, Any]] = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        operations = list(outcome.get("expected_operations") or [])
        if not operations:
            result.append({})
            continue
        resume_operations = [
            operation for operation in operations
            if operation_domain(operation.get("path")) == "resume"
        ]
        layout_operations = [
            operation for operation in operations
            if operation_domain(operation.get("path")) == "layout"
        ]
        result.append(await _operation_changes(resume_operations, layout_operations))
    return result


def _pending_operation_changes(result: dict[str, Any]) -> dict[str, Any] | None:
    pending = result.get("pending_confirmation")
    if not isinstance(pending, dict):
        return None
    candidate_resume = pending.get("resume_candidate")
    candidate_layout = pending.get("layout_candidate")
    if not isinstance(candidate_resume, dict) or not isinstance(candidate_layout, dict):
        return None
    return _final_change_map(
        _combined(SYNTHETIC_RESUME, default_layout_config()),
        _combined(candidate_resume, candidate_layout),
    )


async def _reconstructed_operation_changes(
    predicted_calls: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    last_successful: dict[str, Any] | None = None
    error = ""
    for call in predicted_calls:
        if call.get("name") != "resume_edit" or call.get("executable") is not True:
            continue
        args = call.get("args")
        if not isinstance(args, dict):
            continue
        try:
            last_successful = await _operation_changes(
                list(args.get("resume_operations") or []),
                list(args.get("layout_operations") or []),
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)}"
    return last_successful, error


async def _attach_operation_outcome(
    row: dict[str, Any],
    case: dict[str, Any],
    *,
    graph_result: dict[str, Any] | None = None,
) -> None:
    accepted_outcomes = case.get("accepted_outcomes")
    expected_operations = list(case.get("expected_operations") or [])
    if isinstance(accepted_outcomes, list):
        # Keep one operation list for backwards-compatible result shape and
        # store the complete final-state alternatives separately.
        for outcome in accepted_outcomes:
            if isinstance(outcome, dict) and outcome.get("expected_operations"):
                expected_operations = list(outcome["expected_operations"])
                break
        row["accepted_outcomes"] = accepted_outcomes
        try:
            row["accepted_final_changes"] = await _accepted_operation_changes(case)
        except Exception as exc:
            row["accepted_final_changes"] = None
            row["outcome_error"] = f"Gold: {type(exc).__name__}: {str(exc)}"
    else:
        row.pop("accepted_outcomes", None)
        row.pop("accepted_final_changes", None)
    row["expected_operations"] = expected_operations
    if not expected_operations and not isinstance(accepted_outcomes, list):
        row.pop("expected_final_changes", None)
        row.pop("actual_final_changes", None)
        row.pop("outcome_error", None)
        return
    if expected_operations:
        try:
            row["expected_final_changes"] = await _expected_operation_changes({**case, "expected_operations": expected_operations})
        except Exception as exc:
            row["expected_final_changes"] = None
            row["actual_final_changes"] = None
            row["outcome_error"] = f"Gold: {type(exc).__name__}: {str(exc)}"
            return

    if graph_result is not None:
        actual_changes = _pending_operation_changes(graph_result)
        if actual_changes is not None:
            row["actual_final_changes"] = actual_changes
            row["outcome_error"] = ""
            return
        reconstructed, error = await _reconstructed_operation_changes(
            list(row.get("predicted_calls") or [])
        )
        if reconstructed == {} or (reconstructed is None and isinstance(accepted_outcomes, list)):
            row["actual_final_changes"] = {}
            row["outcome_error"] = ""
        else:
            row["actual_final_changes"] = None
            row["outcome_error"] = error or "未生成可供用户确认的修改候选"
        return

    if "actual_final_changes" not in row:
        reconstructed, error = await _reconstructed_operation_changes(
            list(row.get("predicted_calls") or [])
        )
        row["actual_final_changes"] = {} if reconstructed is None and isinstance(accepted_outcomes, list) else reconstructed
        row["outcome_error"] = error or ("" if reconstructed is not None else "未生成可执行修改候选")


async def run_skill(cases: list[dict[str, Any]], *, mode: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not LLM_ENABLED:
        raise RuntimeError("当前对话 API 未配置，无法执行在线 Skill 评测")
    selected = [case for case in cases if case.get("smoke") is True] if mode == "smoke" else cases
    rows = []
    for index, case in enumerate(selected, start=1):
        state = _base_state(
            case["prompt"],
            messages=_case_messages(case),
            request_id=case["id"],
            **_case_state_overrides(case),
        )
        started_route = entry_router(state)
        try:
            result = await graph.ainvoke(state, config={"recursion_limit": 12})
            new_messages = list(result.get("messages") or [])[len(state.messages):]
            predicted_calls = []
            assistant_parts = []
            for response in new_messages:
                if not isinstance(response, AIMessage):
                    continue
                calls = list(getattr(response, "tool_calls", None) or [])
                invalid_calls = list(getattr(response, "invalid_tool_calls", None) or [])
                for call in calls + invalid_calls:
                    name = str(_tool_call_value(call, "name", "") or "")
                    if name == "load_agent_skill":
                        continue
                    args = _tool_call_value(call, "args", {})
                    schema_valid, executable, validation_error = await _validate_call(name, args)
                    predicted_calls.append({
                        "name": name, "args": args if isinstance(args, dict) else {},
                        "schema_valid": schema_valid, "executable": executable,
                        "validation_error": validation_error,
                    })
                content = getattr(response, "content", "")
                if content:
                    assistant_parts.append(
                        content if isinstance(content, str)
                        else json.dumps(content, ensure_ascii=False)
                    )
            assistant_text = "\n\n".join(assistant_parts)
            error = ""
        except Exception as exc:
            result = {}
            predicted_calls = []
            assistant_text = ""
            error = f"{type(exc).__name__}: {str(exc)}"
        required_tools = (
            case.get("required_tools")
            if "required_tools" in case
            else case.get("expected_tools")
        ) or []
        row = {
            "id": case["id"], "prompt": case["prompt"],
            "expected_tools": required_tools,
            "required_tools": required_tools,
            "optional_tools": case.get("optional_tools") or [],
            "forbidden_tools": case.get("forbidden_tools") or [],
            "expected_operations": case.get("expected_operations") or [],
            "answer_expectation": case.get("answer_expectation", ""),
            "entry_route": started_route,
            "expected_route": case.get("expected_route", "conversation_llm"),
            "predicted_calls": predicted_calls,
            "assistant_text": assistant_text[:1000],
            "error": error,
        }
        await _attach_operation_outcome(row, case, graph_result=result)
        rows.append(row)
        predicted = [call["name"] for call in predicted_calls]
        print(
            f"[{index}/{len(selected)}] {case['id']} required={row['required_tools']} "
            f"optional={row['optional_tools']} predicted={predicted}"
        )
    return rows, skill_metrics(rows)


async def _refresh_skill_rows(
    rows: list[dict[str, Any]], cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cases_by_id = {case["id"]: case for case in cases}
    refreshed = []
    for row in rows:
        case = cases_by_id.get(row.get("id"))
        if case is None:
            continue
        required_tools = (
            case.get("required_tools")
            if "required_tools" in case
            else case.get("expected_tools")
        ) or []
        row["expected_tools"] = required_tools
        row["required_tools"] = required_tools
        row["optional_tools"] = case.get("optional_tools") or []
        row["forbidden_tools"] = case.get("forbidden_tools") or []
        row["answer_expectation"] = case.get("answer_expectation", "")
        row["expected_route"] = case.get("expected_route", "conversation_llm")
        await _attach_operation_outcome(row, case)
        refreshed.append(row)
    return refreshed


def _percentage(value: float) -> str:
    return f"{value * 100:.2f}%"


def _report(
    offline: dict[str, Any] | None,
    online: dict[str, Any] | None,
    smoke: dict[str, Any] | None = None,
    *,
    results_dir: Path,
) -> str:
    dataset_id = next(
        (payload.get("dataset_id") for payload in (offline, online, smoke) if payload),
        "agent-core",
    )
    dataset_counts = next(
        (payload.get("dataset_case_counts") for payload in (offline, online, smoke)
         if payload and isinstance(payload.get("dataset_case_counts"), dict)),
        None,
    ) or dict(EXPECTED_COUNTS)
    total_count = sum(int(value) for value in dataset_counts.values())
    lines = ["# ResumeBranch Agent 核心评测报告", ""]
    lines.append(f"- 数据集：`{dataset_id}`，{total_count} 条唯一评测案例")
    lines.append(
        f"- 分类：路由 {dataset_counts['routing']} 条、Skill 选择 {dataset_counts['skill']} 条、"
        f"修改安全 {dataset_counts['safety']} 条"
    )
    lines.append("- 本轮评测调整：修改正确性按最终候选结果判定；操作 JSON 严格匹配仅作为诊断信息，不作为核心指标")
    lines.append(f"- 报告生成时间：{_utc_now()}")
    if smoke:
        lines.append(
            f"- 在线 Smoke：已执行 {smoke.get('case_count', 0)} 条，结果仅用于接口与结果格式检查"
        )
    lines.extend([
        "", "## 指标定义", "",
        "- 路由准确率：入口节点预测正确数 / 路由案例数。",
        "- Skill Precision、Recall：只对实际进入 conversation_llm 的案例，以是否调用对应 Skill 进行多标签统计。",
        "- 多合法结果：案例显式列出允许的工具与回答分支，命中任一完整分支即计为有效。",
        "- 修改可执行率：通过工具参数与操作契约校验的修改调用数 / 全部修改调用数。",
        "- 修改结果准确率：在同一基准简历上生成金标候选与实际候选，最终差异符合用户目标的案例数 / 有结果金标的修改案例数。",
        "- 非目标字段误改率：候选中发生变化的非目标叶子字段数 / 检查的非目标叶子字段数；另报发生任意连带修改的案例率。",
    ])
    if offline:
        route = offline["metrics"]["routing"]
        safe = offline["metrics"]["safety"]
        lines.extend([
            "", "## 离线结果", "",
            f"- 路由准确率：{_percentage(route['accuracy'])}（{route['correct']}/{route['case_count']}）",
            f"- 目标修改成功率：{_percentage(safe['target_edit_success_rate'])}",
            f"- 非目标字段误改率：{_percentage(safe['non_target_field_error_rate'])}",
            f"- 未确认写入率：{_percentage(safe['unconfirmed_write_rate'])}",
            f"- 取消后数据保持率：{_percentage(safe['cancel_data_preservation_rate'])}",
            f"- 过期确认拦截率：{_percentage(safe['stale_confirmation_block_rate'])}",
        ])
        lines.extend(["", "### 路由各路径", ""])
        for path, values in route["per_path"].items():
            lines.append(f"- `{path}`：正确 {values['correct']}，错误 {values['incorrect']}")
        labels = list(route["confusion_matrix"])
        lines.extend(["", "### 路由混淆矩阵", ""])
        lines.append("| 金标 \\ 实际 | " + " | ".join(labels) + " |")
        lines.append("|---|" + "---:|" * len(labels))
        for expected in labels:
            lines.append(
                f"| {expected} | "
                + " | ".join(str(route["confusion_matrix"][expected][actual]) for actual in labels)
                + " |"
            )
        lines.extend([
            "", "### 修改安全计数", "",
            f"- 目标字段：{safe['target_success']}/{safe['target_total']} 正确。",
            f"- 非目标叶子字段：{safe['non_target_changed']}/{safe['non_target_total']} 发生变化；"
            f"连带修改案例 {safe['collateral_cases_changed']}/{safe['collateral_cases']}。",
            f"- 确认前写入：{safe['unconfirmed_writes']}/{safe['unconfirmed_cases']}。",
            f"- 取消后保持：{safe['cancel_preserved']}/{safe['cancel_cases']}。",
            f"- 过期确认拦截：{safe['stale_blocked']}/{safe['stale_cases']}。",
        ])
    if online:
        skill = online["metrics"]["skill"]
        lines.extend(["", "## 在线 Skill 结果", ""])
        run_scope = online.get("run_scope") or {}
        if run_scope.get("type") == "targeted_rerun":
            if run_scope.get("merged_with_existing"):
                lines.append(
                    f"- 本轮定向复测 {run_scope.get('executed_case_count', 0)} 条上一轮失败案例；"
                    "其余案例沿用上一轮实际结果后重新计算总体指标。"
                )
            else:
                lines.append(
                    f"- 本轮为独立定向复测，共执行 {run_scope.get('executed_case_count', 0)} 条案例；"
                    "下列在线指标仅基于本轮案例，不代表 400 条 Skill 总集结果。"
                )
        for name, values in skill["per_skill"].items():
            lines.append(
                f"- `{name}`：Precision {_percentage(values['precision'])}，"
                f"Recall {_percentage(values['recall'])} "
                f"（TP={values['tp']}，FP={values['fp']}，FN={values['fn']}，TN={values.get('tn', 0)}）"
            )
        executability = skill["edit_operation_executability"]
        lines.extend([
            f"- Skill 总案例：{skill['case_count']}；进入 LLM Skill 决策：{skill['skill_decision_case_count']}；排除：{skill['excluded_from_skill_metrics']}。",
            f"- 修改可执行率：{_percentage(executability['pass_rate'])} "
            f"（{executability['passed']}/{executability['total']}）",
        ])
        edit_outcome = skill.get("edit_outcome")
        if edit_outcome:
            lines.append(
                f"- 修改结果准确率：{_percentage(edit_outcome['accuracy'])} "
                f"（{edit_outcome['correct']}/{edit_outcome['case_count']}）"
            )
    failures = []
    if offline:
        failures.extend(offline["metrics"]["routing"]["failures"])
        failures.extend(offline["metrics"]["safety"]["failures"])
    if online:
        failures.extend(online["metrics"]["skill"]["failures"])
    lines.extend(["", "## 失败案例", ""])
    if failures:
        lines.extend(f"- `{item.get('id', '')}`：{json.dumps(item, ensure_ascii=False)}" for item in failures)
    else:
        lines.append("- 无")
    if online:
        invalid_edits = []
        for case in online.get("cases", []):
            for call in case.get("predicted_calls", []):
                if call.get("name") == "resume_edit" and call.get("executable") is False:
                    invalid_edits.append({
                        "id": case.get("id"),
                        "validation_error": call.get("validation_error", ""),
                    })
        lines.extend(["", "### 参数可执行失败", ""])
        if invalid_edits:
            lines.extend(
                f"- `{item['id']}`：{item['validation_error']}" for item in invalid_edits
            )
        else:
            lines.append("- 无")
        edit_outcome = online.get("metrics", {}).get("skill", {}).get("edit_outcome")
        if edit_outcome:
            lines.extend(["", "### 目标修改结果失败", ""])
            if edit_outcome.get("failures"):
                lines.extend(
                    f"- `{item.get('id', '')}`：最终候选未达到金标结果。"
                    + (f" {item.get('outcome_error')}" if item.get("outcome_error") else "")
                    for item in edit_outcome["failures"]
                )
            else:
                lines.append("- 无")
    probe_path = results_dir / "route-016-online-probe.json"
    if probe_path.exists():
        probe = json.loads(probe_path.read_text(encoding="utf-8"))
        lines.extend([
            "", "## route-016 在线行为探针", "",
            f"- 入口：`{probe['entry_route']}`；调用：`{', '.join(probe['predicted_tools'])}`。",
            f"- 回复先追问未明确的项目职责：{'是' if probe['clarification_question_detected'] else '否'}。",
            f"- 简历内容操作 {probe['resume_operations_count']} 条；独立排版操作 {probe['layout_operations_count']} 条。",
            f"- 参数 Schema：{'通过' if probe['schema_valid'] else '失败'}；操作可执行：{'是' if probe['executable'] else '否'}。",
        ])
    lines.extend([
        "", "## 可用于简历的表述草稿", "",
        f"构建 {total_count} 条版本化 Agent 核心评测集，覆盖 LangGraph 路由、Skill 选择与候选修改安全；实现离线可复现指标和在线对话模型评测，量化路由准确率、Skill Precision/Recall、修改可执行率与最终修改正确率，并通过失败归因完善 Agent 行为。",
    ])
    lines.extend([
        "", "## 说明", "",
        "所有指标均由实际运行结果计算；在线评测仅使用项目当前对话 API 配置，不读取或输出 API Key。",
        "失败案例不会因分数原因从数据集中删除。",
    ])
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "smoke", "online"), required=True)
    parser.add_argument("--dataset-version", choices=("total",), default="total")
    parser.add_argument(
        "--case-ids",
        default="",
        help="Comma-separated Skill case IDs for a targeted online rerun.",
    )
    parser.add_argument(
        "--merge-existing",
        action="store_true",
        help="Merge a targeted online rerun into the existing full result.",
    )
    args = parser.parse_args()
    dataset_dir = EVAL_ROOT / args.dataset_version
    results_dir = dataset_dir / "results"
    cases = _load_cases(dataset_dir / "cases.json")
    results_dir.mkdir(parents=True, exist_ok=True)
    if args.mode == "offline":
        route_rows, route_metrics = run_routing(cases["routing"])
        safety_rows, safe_metrics = await run_safety(cases["safety"])
        payload = {
            "dataset_id": cases["dataset_id"], "mode": "offline", "generated_at": _utc_now(),
            "dataset_case_counts": {category: len(cases[category]) for category in EXPECTED_COUNTS},
            "case_counts": {"routing": len(route_rows), "safety": len(safety_rows)},
            "metrics": {"routing": route_metrics, "safety": safe_metrics},
            "cases": {"routing": route_rows, "safety": safety_rows},
        }
        _write_json(results_dir / "offline-result.json", payload)
        online_path = results_dir / "online-result.json"
        online = json.loads(online_path.read_text(encoding="utf-8")) if online_path.exists() else None
        smoke_path = results_dir / "online-smoke-result.json"
        smoke = json.loads(smoke_path.read_text(encoding="utf-8")) if smoke_path.exists() else None
        (results_dir / "report.md").write_text(
            _report(payload, online, smoke, results_dir=results_dir), encoding="utf-8"
        )
        print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
        return

    requested_case_ids = [
        value.strip() for value in str(args.case_ids or "").split(",") if value.strip()
    ]
    if requested_case_ids and args.mode != "online":
        parser.error("--case-ids 仅支持 --mode online")
    if args.merge_existing and not requested_case_ids:
        parser.error("--merge-existing 必须与 --case-ids 一起使用")
    skill_cases = list(cases["skill"])
    selected_cases = skill_cases
    if requested_case_ids:
        requested = set(requested_case_ids)
        known = {case["id"] for case in skill_cases}
        missing = sorted(requested - known)
        if missing:
            parser.error(f"未知 Skill 案例：{', '.join(missing)}")
        selected_cases = [case for case in skill_cases if case["id"] in requested]

    rows, metrics = await run_skill(selected_cases, mode=args.mode)
    if args.merge_existing:
        existing_path = results_dir / "online-result.json"
        if not existing_path.exists():
            parser.error("定向合并需要已有 online-result.json")
        existing_payload = json.loads(existing_path.read_text(encoding="utf-8"))
        existing_rows = {
            row.get("id"): row for row in (existing_payload.get("cases") or [])
            if isinstance(row, dict) and row.get("id")
        }
        existing_rows.update({row["id"]: row for row in rows})
        ordered_ids = [case["id"] for case in skill_cases]
        missing_rows = [case_id for case_id in ordered_ids if case_id not in existing_rows]
        if missing_rows:
            parser.error(f"已有结果缺少案例，不能合并：{', '.join(missing_rows)}")
        rows = [existing_rows[case_id] for case_id in ordered_ids]
        rows = await _refresh_skill_rows(rows, skill_cases)
        metrics = skill_metrics(rows)
    payload = {
        "dataset_id": cases["dataset_id"], "mode": args.mode, "generated_at": _utc_now(),
        "dataset_case_counts": {category: len(cases[category]) for category in EXPECTED_COUNTS},
        "model": {"provider": LLM_PROVIDER, "model": LLM_MODEL},
        "case_count": len(rows), "metrics": {"skill": metrics}, "cases": rows,
    }
    if requested_case_ids:
        payload["run_scope"] = {
            "type": "targeted_rerun",
            "executed_case_count": len(selected_cases),
            "executed_case_ids": [case["id"] for case in selected_cases],
            "merged_with_existing": bool(args.merge_existing),
        }
    filename = "online-smoke-result.json" if args.mode == "smoke" else "online-result.json"
    _write_json(results_dir / filename, payload)
    offline_path = results_dir / "offline-result.json"
    offline = json.loads(offline_path.read_text(encoding="utf-8")) if offline_path.exists() else None
    report_online = payload if args.mode == "online" else None
    smoke_path = results_dir / "online-smoke-result.json"
    smoke = payload if args.mode == "smoke" else (
        json.loads(smoke_path.read_text(encoding="utf-8")) if smoke_path.exists() else None
    )
    (results_dir / "report.md").write_text(
        _report(offline, report_online, smoke, results_dir=results_dir), encoding="utf-8"
    )
    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
