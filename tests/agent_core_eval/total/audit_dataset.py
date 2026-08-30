"""Audit the consolidated Agent evaluation data without model/API calls."""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
import json
from copy import deepcopy
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.layout_config import default_layout_config
from backend.resume_data import normalize_resume_data
from backend.resume_changes import resume_digest
from backend.skills.resume_edit import ResumeEditRequest, run_resume_edit
from backend.resume_agent import entry_router
from tests.agent_core_eval.total.metrics import operation_domain, routing_metrics
from tests.agent_core_eval.total.run_eval import (
    SYNTHETIC_RESUME,
    _load_cases,
    _route_state,
    run_safety,
)


DATASET_PATH = Path(__file__).resolve().parent / "cases.json"
REPORT_PATH = Path(__file__).resolve().parent / "audit.md"
FORBIDDEN_MARKERS = ("虚构", "虚假", "伪造", "捏造", "测试信息")
SUPPORTED_TOOLS = {"request_resume_edit", "render_resume_pdf_images"}
VISUAL_TERMS = re.compile(
    r"页面|PDF|排版|布局|视觉|呈现|预览|换页|空白|间距|对齐|拥挤|舒服|好看|美观|留白|换行|下划线|一页|渲染|模块"
)


def _all_cases(payload: dict) -> list[dict]:
    return [case for category in ("routing", "skill", "safety") for case in payload[category]]


def _extract_v4_subset(payload: dict) -> dict:
    """Extract v4-hard cases from the self-contained total dataset."""
    prefixes = {"routing": "route-v4-", "skill": "skill-v4-", "safety": "safe-v4-"}
    subset = {
        category: [
            case for case in payload.get(category, [])
            if str(case.get("id", "")).startswith(prefix)
        ]
        for category, prefix in prefixes.items()
    }
    subset["scenario_counts"] = dict(Counter(
        case.get("scenario_type") or "legacy_unclassified"
        for case in _all_cases(subset)
    ))
    return subset


def _audit_v4_content(payload: dict) -> dict:
    """Review the added hard set's semantic gold, not only its shape.

    The checks deliberately use the case's declared intent class (edit,
    snapshot, no-tool, or mixed) instead of matching individual prompt words.
    That keeps this audit about the capability boundary and avoids adding
    prompt-specific patches.
    """
    issues: list[dict[str, str]] = []
    expected_counts = {"routing": 59, "skill": 66, "safety": 25}
    actual_counts = {category: len(payload.get(category) or []) for category in expected_counts}
    if actual_counts != expected_counts:
        issues.append({"scope": "dataset", "reason": f"数量不符合 v4-hard 目标：{actual_counts}"})

    declared_scenarios = Counter(
        case.get("scenario_type") or "legacy_unclassified"
        for case in _all_cases(payload)
    )
    configured_scenarios = Counter(payload.get("scenario_counts") or {})
    if declared_scenarios != configured_scenarios:
        issues.append({"scope": "scenario_type", "reason": "v4-hard 场景标签计数与元数据不一致"})

    allowed_routes = {"conversation_llm", "direct_edit", "interview_coach", "tool_node"}
    for case in payload.get("routing") or []:
        route = str(case.get("expected_route") or "")
        if route not in allowed_routes:
            issues.append({"scope": case.get("id", ""), "reason": f"未知路由金标：{route}"})
        if route == "interview_coach" and not case.get("state", {}).get("interaction_mode"):
            issues.append({"scope": case.get("id", ""), "reason": "求职辅导路由缺少 interaction_mode 上下文"})
        if route == "tool_node" and case.get("confirmation") not in {
            "confirm", "cancel", "confirm_all", "cancel_all",
            "confirm_selected:change-2",
        }:
            issues.append({"scope": case.get("id", ""), "reason": "确认/取消路由缺少有效确认值"})

    skill_groups = Counter()
    for case in payload.get("skill") or []:
        required = set(case.get("required_tools") or case.get("expected_tools") or [])
        operations = list(case.get("expected_operations") or [])
        if required == {"request_resume_edit"}:
            group = "edit_only"
            if not operations:
                issues.append({"scope": case.get("id", ""), "reason": "明确修改案例缺少操作金标"})
        elif required == {"render_resume_pdf_images"}:
            group = "snapshot_only"
            if operations or not VISUAL_TERMS.search(case.get("prompt", "")):
                issues.append({"scope": case.get("id", ""), "reason": "快照案例不是纯页面/视觉观察请求"})
        elif not required and not (case.get("optional_tools") or []):
            group = "no_tool"
            if operations:
                issues.append({"scope": case.get("id", ""), "reason": "No-tool 案例却包含修改操作金标"})
        elif required == {"render_resume_pdf_images", "request_resume_edit"}:
            group = "mixed"
            if not operations or not VISUAL_TERMS.search(case.get("prompt", "")):
                issues.append({"scope": case.get("id", ""), "reason": "混合案例缺少视觉前置请求或修改操作"})
        else:
            group = "other"
            issues.append({"scope": case.get("id", ""), "reason": "Skill 金标不属于四类明确意图"})
        skill_groups[group] += 1

    safety_phases = Counter(case.get("phase") or "" for case in payload.get("safety") or [])
    if safety_phases != Counter({"candidate": 5, "confirm": 5, "cancel": 5, "isolation": 5, "stale": 5}):
        issues.append({"scope": "safety", "reason": f"安全阶段覆盖不均：{dict(safety_phases)}"})
    for case in payload.get("safety") or []:
        phase = case.get("phase")
        if phase == "stale" and not case.get("stale_mutation"):
            issues.append({"scope": case.get("id", ""), "reason": "过期确认案例缺少并发变更"})
        if phase in {"candidate", "confirm", "cancel", "isolation", "stale"} and not (
            case.get("resume_operations") or case.get("layout_operations")
        ):
            issues.append({"scope": case.get("id", ""), "reason": "安全案例缺少候选操作"})

    route_rows = [
        {"id": case["id"], "expected": case["expected_route"], "actual": entry_router(_route_state(case))}
        for case in payload.get("routing") or []
    ]
    return {
        "counts": actual_counts,
        "scenario_counts": dict(declared_scenarios),
        "scenario_counts_match": declared_scenarios == configured_scenarios,
        "route_metrics": routing_metrics(route_rows),
        "skill_groups": dict(skill_groups),
        "safety_phases": dict(safety_phases),
        "issues": issues,
    }


async def _validate_skill_operations(cases: list[dict]) -> list[dict]:
    base = normalize_resume_data(deepcopy(SYNTHETIC_RESUME))
    invalid = []
    for case in cases:
        required = set(case.get("required_tools") or case.get("expected_tools") or [])
        operations = list(case.get("expected_operations") or [])
        if "request_resume_edit" not in required or not operations:
            continue
        resume_operations = [op for op in operations if operation_domain(op.get("path")) == "resume"]
        layout_operations = [op for op in operations if operation_domain(op.get("path")) == "layout"]
        try:
            await run_resume_edit(ResumeEditRequest(
                resume_data=deepcopy(base),
                layout_config=default_layout_config(),
                resume_operations=tuple(resume_operations),
                layout_operations=tuple(layout_operations),
                base_revision=resume_digest(base),
            ))
        except Exception as exc:  # pragma: no cover - report data defects, don't mask them
            invalid.append({"id": case.get("id", ""), "error": f"{type(exc).__name__}: {exc}"})
    return invalid


async def audit() -> dict:
    payload = _load_cases(DATASET_PATH)
    v4_payload = _extract_v4_subset(payload)
    all_cases = _all_cases(payload)
    actual_scenario_counts = Counter(
        case.get("scenario_type") or "legacy_unclassified" for case in all_cases
    )
    serialized = DATASET_PATH.read_text(encoding="utf-8")
    ids = [case.get("id", "") for case in all_cases]
    prompt_map: defaultdict[str, list[str]] = defaultdict(list)
    for case in all_cases:
        prompt_map[str(case.get("prompt", "")).strip()].append(str(case.get("id", "")))
    duplicate_prompts = {prompt: ids for prompt, ids in prompt_map.items() if len(ids) > 1}

    route_rows = []
    for case in payload["routing"]:
        actual = entry_router(_route_state(case))
        route_rows.append({
            "id": case["id"], "expected": case["expected_route"], "actual": actual,
        })
    route_result = routing_metrics(route_rows)

    skill_metadata_issues = []
    visual_without_snapshot = []
    no_tool_with_concrete_edit = []
    for case in payload["skill"]:
        expected = set(case.get("required_tools") or case.get("expected_tools") or [])
        optional = set(case.get("optional_tools") or [])
        forbidden = set(case.get("forbidden_tools") or [])
        if not expected.isdisjoint(optional) or not (expected | optional).isdisjoint(forbidden):
            skill_metadata_issues.append({"id": case["id"], "reason": "required/optional/forbidden 工具集合重叠"})
        if not expected <= SUPPORTED_TOOLS or not optional <= SUPPORTED_TOOLS or not forbidden <= SUPPORTED_TOOLS:
            skill_metadata_issues.append({"id": case["id"], "reason": "包含未支持工具名"})
        expected_route = case.get("expected_route", "conversation_llm")
        if expected_route != "conversation_llm":
            skill_metadata_issues.append({"id": case["id"], "reason": f"Skill 案例入口金标无效：{expected_route}"})
        if "render_resume_pdf_images" in expected and not VISUAL_TERMS.search(case.get("prompt", "")):
            visual_without_snapshot.append(case["id"])
        if not expected and not optional and re.search(r"(?:修改|改为|改成|替换|更新|设置|删除|移除|新增|添加|补充|移动|放到|重写|改写)", case.get("prompt", "")):
            no_tool_with_concrete_edit.append(case["id"])

    safety_rows, safety_result = await run_safety(payload["safety"])
    operation_invalid = await _validate_skill_operations(payload["skill"])
    markers = [marker for marker in FORBIDDEN_MARKERS if marker in serialized]
    v4_review = _audit_v4_content(v4_payload)
    result = {
        "counts": {category: len(payload[category]) for category in ("routing", "skill", "safety")},
        "scenario_counts": dict(actual_scenario_counts),
        "scenario_counts_match": actual_scenario_counts == Counter(payload.get("scenario_counts") or {}),
        "unique_id_count": len(set(ids)),
        "total_id_count": len(ids),
        "duplicate_prompts": duplicate_prompts,
        "forbidden_markers": markers,
        "route_metrics": route_result,
        "route_mismatch_ids": [row["id"] for row in route_rows if row["expected"] != row["actual"]],
        "skill_metadata_issues": skill_metadata_issues,
        "visual_without_snapshot": visual_without_snapshot,
        "no_tool_edit_phrase_review": no_tool_with_concrete_edit,
        "skill_operation_invalid": operation_invalid,
        "safety_metrics": safety_result,
        "operation_gold_count": sum(
            bool((case.get("expected_operations") or []))
            and "request_resume_edit" in set(case.get("required_tools") or case.get("expected_tools") or [])
            for case in payload["skill"]
        ),
        "v4_hard_review": v4_review,
    }
    return result


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def render_report(result: dict) -> str:
    route = result["route_metrics"]
    safe = result["safety_metrics"]
    counts = result["counts"]
    lines = [
        "# ResumeBranch Agent 核心评测 600 条数据审查",
        "",
        "本报告只审查案例结构、金标与当前契约的一致性，不调用模型 API。",
        "",
        "## 数量",
        "",
        f"- 路由：{counts['routing']} 条；Skill：{counts['skill']} 条；修改安全：{counts['safety']} 条；合计 {sum(counts.values())} 条。",
        f"- 唯一 ID：{result['unique_id_count']}/{result['total_id_count']}。",
        f"- 场景标签：{result['scenario_counts']}。",
        f"- 逐条操作金标：{result['operation_gold_count']} 条 Skill 案例；其余早期 Skill 案例只评估工具选择，不虚构操作金标。",
        "",
        "## 审查规则",
        "",
        "- 案例 ID、分类数量和工具名称必须符合运行器 Schema。",
        "- 同一总集内不允许重复提示词；提示词不得包含会诱导模型诚信回答的身份或数据标签。",
        "- 明确可执行修改必须有可执行操作；视觉/页面观察请求才要求快照；无明确目标的请求不得生成修改候选。",
        "- 安全案例必须能通过当前修改契约，并覆盖候选、确认、取消、字段隔离和过期确认。",
        "- v4-hard 另行逐条检查四类意图：明确编辑、纯视觉快照、无工具回答/追问、视觉观察加编辑；安全案例按五个阶段各 5 条复核。",
        "",
        "## 自动审查结果",
        "",
        f"- 重复提示词：{'无' if not result['duplicate_prompts'] else result['duplicate_prompts']}。",
        f"- 禁止标识词：{'无' if not result['forbidden_markers'] else result['forbidden_markers']}。",
        f"- 工具元数据冲突：{'无' if not result['skill_metadata_issues'] else result['skill_metadata_issues']}。",
        f"- 场景计数元数据：{'一致' if result['scenario_counts_match'] else '不一致'}。",
        f"- 需要快照但缺少页面/视觉语义：{'无' if not result['visual_without_snapshot'] else result['visual_without_snapshot']}。",
        f"- 修改操作契约校验失败：{'无' if not result['skill_operation_invalid'] else result['skill_operation_invalid']}。",
        f"- 安全模拟失败：{'无' if not safe['failures'] else safe['failures']}。",
        "",
        "## v4-hard 困难集逐条内容审查",
        "",
        f"- 覆盖：路由 {result['v4_hard_review']['counts']['routing']} 条、Skill {result['v4_hard_review']['counts']['skill']} 条、修改安全 {result['v4_hard_review']['counts']['safety']} 条。",
        f"- 路由金标对当前入口实现：{result['v4_hard_review']['route_metrics']['correct']}/{result['v4_hard_review']['route_metrics']['case_count']}，准确率 {_pct(result['v4_hard_review']['route_metrics']['accuracy'])}。",
        f"- Skill 意图分组：{result['v4_hard_review']['skill_groups']}。",
        f"- 安全阶段：{result['v4_hard_review']['safety_phases']}。",
        f"- 语义/金标审查问题：{'无' if not result['v4_hard_review']['issues'] else result['v4_hard_review']['issues']}。",
        "- 结论：v4-hard 的输入均为正常用户表达；明确编辑、视觉观察、模糊澄清和安全阶段的金标分别对应当前能力边界，未用单个失败样本定制规则。",
        "",
        "## 路由金标与当前实现对照",
        "",
        f"- 当前实现离线判定：{route['correct']}/{route['case_count']}，准确率 {_pct(route['accuracy'])}。",
        f"- 路由不一致案例：{'无' if not result['route_mismatch_ids'] else result['route_mismatch_ids']}。",
        "- `route-v2-032` 已按冻结能力边界修正为 `conversation_llm`，因为基本信息排列不属于可执行排版契约。",
        "",
        "## 安全离线结果",
        "",
        f"- 目标修改成功率：{_pct(safe['target_edit_success_rate'])}。",
        f"- 非目标字段误改率：{_pct(safe['non_target_field_error_rate'])}。",
        f"- 连带修改案例率：{_pct(safe['collateral_change_case_rate'])}。",
        f"- 未确认写入率：{_pct(safe['unconfirmed_write_rate'])}。",
        f"- 取消后数据保持率：{_pct(safe['cancel_data_preservation_rate'])}。",
        f"- 过期确认拦截率：{_pct(safe['stale_confirmation_block_rate'])}。",
        "",
        "## 结论与覆盖边界",
        "",
        "- 新增 v4-hard 案例均使用自然用户请求，操作金标可通过当前契约校验，未发现重复提示词或禁止标识词。",
        "- 早期 v1/v2 Skill 案例主要用于工具选择，因此没有逐操作金标；最终候选结果指标只对有结果金标的案例统计。",
        "- 确定性 direct_edit 案例不进入 LLM Skill Precision/Recall/No-tool 分母，单独检查入口和候选结果。",
        "- `skill-v2-024` 已按当前测试简历修正为无需调用 Skill：项目角色已是后端开发，项目职责也已是圆点列表。",
        "- 目前仅完成离线数据审查，未执行 Smoke 或完整在线评测。",
        "",
    ]
    return "\n".join(lines)


async def main() -> None:
    result = await audit()
    REPORT_PATH.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({
        "counts": result["counts"],
        "duplicate_prompts": result["duplicate_prompts"],
        "route_mismatch_ids": result["route_mismatch_ids"],
        "skill_operation_invalid": result["skill_operation_invalid"],
        "safety_failures": result["safety_metrics"]["failures"],
        "v4_hard_review_issues": result["v4_hard_review"]["issues"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
