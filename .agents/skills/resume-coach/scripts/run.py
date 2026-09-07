"""Deterministic state and provenance boundary for the resume-coach Skill."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.resume_edit_contract import ResumeEditOperation


MAX_EVIDENCE_PER_ISSUE = 100
MAX_ISSUES = 30


class EvidenceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    source_quote: str
    section: str = ""
    dimension: str = ""


class CoachProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    resume_operations: list[ResumeEditOperation]


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    claim: str
    source_quote: str
    section: str = ""
    dimension: str = ""
    source_request_id: str
    verified_at: str
    status: Literal["active", "superseded"] = "active"
    superseded_by_request_id: str = ""


class PreviewOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str
    summary: str
    resume_operations: list[ResumeEditOperation]
    source_content_digest: str
    status: Literal[
        "offered",
        "authorized",
        "preview_generated",
        "noop",
        "applied",
        "partially_applied",
        "rejected",
        "invalidated",
        "undone",
    ]
    revision_id: str = ""
    applied_at: str = ""


class StartOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str
    problem: str
    source_request_id: str
    status: Literal["offered"]


class CoachIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem: str = ""
    status: Literal["active", "completed", "skipped"] = "active"
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    conclusions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    pending_preview_offer: PreviewOffer | None = None
    result: str = ""


class CoachState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    active: bool = False
    entry: Literal["", "explicit_command", "explicit_request", "accepted_offer"] = ""
    agenda: list[str] = Field(default_factory=list)
    current_issue_id: str = ""
    issues: dict[str, CoachIssue] = Field(default_factory=dict)
    pending_start_offer: StartOffer | None = None
    updated_at: str = ""


class ResumeCoachToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal[
        "offer_start",
        "dismiss_start",
        "start",
        "update",
        "offer_preview",
        "handoff_to_edit",
        "complete_issue",
        "exit",
    ]
    issue_id: str = ""
    problem: str = ""
    entry: Literal["", "explicit_request", "accepted_offer"] = ""
    offer_id: str = ""
    evidence_candidates: list[EvidenceCandidate] = Field(default_factory=list)
    supersede_evidence_ids: list[str] = Field(default_factory=list)
    conclusions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    proposal: CoachProposal | None = None
    approval_quote: str = ""
    result: str = ""
    reason: str = ""
    completion_status: Literal["completed", "skipped"] = "completed"
    next_issue_id: str = ""
    next_problem: str = ""


class ResumeCoachRuntimeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_data: dict[str, Any]
    source_content_digest: str
    latest_user_message: str
    request_id: str
    context_type: str = "main"
    explicit_command: bool = False
    coach_state: CoachState = Field(default_factory=CoachState)


class EditHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str
    summary: str
    resume_operations: list[ResumeEditOperation]


class ResumeCoachOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str
    coach_state: CoachState
    active: bool
    edit_handoff: EditHandoff | None = None


TOOL_INPUT_MODEL = ResumeCoachToolInput
RUNTIME_CONTEXT_MODEL = ResumeCoachRuntimeContext
OUTPUT_MODEL = ResumeCoachOutput


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _numbers(value: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", value or ""))


def empty_coach_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "active": False,
        "entry": "",
        "agenda": [],
        "current_issue_id": "",
        "issues": {},
        "pending_start_offer": None,
        "updated_at": _now(),
    }


def normalize_coach_state(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result = empty_coach_state()
    result["active"] = bool(source.get("active"))
    entry = _clean(source.get("entry"), 32)
    result["entry"] = entry if entry in {"explicit_command", "explicit_request", "accepted_offer"} else ""
    result["agenda"] = [_clean(item, 120) for item in source.get("agenda", []) if _clean(item, 120)][:MAX_ISSUES]
    issues = source.get("issues") if isinstance(source.get("issues"), dict) else {}
    normalized_issues: dict[str, dict[str, Any]] = {}
    for raw_id, raw_issue in list(issues.items())[-MAX_ISSUES:]:
        if not isinstance(raw_issue, dict):
            continue
        issue_id = _clean(raw_id, 64)
        if not issue_id:
            continue
        normalized_issues[issue_id] = {
            "problem": _clean(raw_issue.get("problem"), 1000),
            "status": (
                raw_issue.get("status")
                if raw_issue.get("status") in {"active", "completed", "skipped"}
                else "active"
            ),
            "evidence": [item for item in raw_issue.get("evidence", []) if isinstance(item, dict)][-MAX_EVIDENCE_PER_ISSUE:],
            "conclusions": [_clean(item, 600) for item in raw_issue.get("conclusions", []) if _clean(item, 600)][:30],
            "open_questions": [_clean(item, 500) for item in raw_issue.get("open_questions", []) if _clean(item, 500)][:30],
            "pending_preview_offer": raw_issue.get("pending_preview_offer") if isinstance(raw_issue.get("pending_preview_offer"), dict) else None,
            "result": _clean(raw_issue.get("result"), 1000),
        }
    result["issues"] = normalized_issues
    pending_offer = source.get("pending_start_offer")
    result["pending_start_offer"] = (
        {
            "offer_id": _clean(pending_offer.get("offer_id"), 80),
            "problem": _clean(pending_offer.get("problem"), 1000),
            "source_request_id": _clean(pending_offer.get("source_request_id"), 80),
            "status": "offered",
        }
        if isinstance(pending_offer, dict)
        and _clean(pending_offer.get("offer_id"), 80)
        and _clean(pending_offer.get("problem"), 1000)
        else None
    )
    current = _clean(source.get("current_issue_id"), 64)
    result["current_issue_id"] = current if current in normalized_issues else ""
    result["updated_at"] = _clean(source.get("updated_at"), 64) or result["updated_at"]
    return result


def _issue_id(
    arguments: ResumeCoachToolInput,
    context: ResumeCoachRuntimeContext,
    problem: str = "",
) -> str:
    requested = _clean(arguments.issue_id, 64)
    if requested:
        return requested
    seed = f"{context.request_id}:{problem or arguments.problem}:{len(context.coach_state.issues)}"
    return "issue-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _ensure_issue(state: dict[str, Any], issue_id: str, problem: str = "") -> dict[str, Any]:
    issues = state["issues"]
    if issue_id not in issues:
        if len(issues) >= MAX_ISSUES:
            raise ValueError("当前深度打磨已达到问题数量上限，请先结束本次会话")
        issues[issue_id] = {
            "problem": _clean(problem, 1000),
            "status": "active",
            "evidence": [],
            "conclusions": [],
            "open_questions": [],
            "pending_preview_offer": None,
            "result": "",
        }
    elif issues[issue_id].get("status") != "active":
        raise ValueError("已完成或跳过的问题不能被隐式重新激活")
    elif problem:
        issues[issue_id]["problem"] = _clean(problem, 1000)
    state["current_issue_id"] = issue_id
    title = issues[issue_id]["problem"] or issue_id
    if title not in state["agenda"]:
        state["agenda"] = (state["agenda"] + [title])[-MAX_ISSUES:]
    return issues[issue_id]


def _merge_evidence(issue: dict[str, Any], candidates: list[EvidenceCandidate], context: ResumeCoachRuntimeContext) -> None:
    latest = _clean(context.latest_user_message, 12000)
    compact_latest = re.sub(r"\s+", "", latest)
    evidence = list(issue.get("evidence", []))
    fingerprints = {(item.get("source_quote"), item.get("claim")) for item in evidence if isinstance(item, dict)}
    for candidate in candidates[:12]:
        claim = _clean(candidate.claim, 500)
        quote = _clean(candidate.source_quote, 500)
        if not claim or len(re.sub(r"\s+", "", quote)) < 2:
            continue
        if re.sub(r"\s+", "", quote) not in compact_latest:
            continue
        if not _numbers(claim).issubset(_numbers(quote)):
            continue
        fingerprint = (quote, claim)
        if fingerprint in fingerprints:
            continue
        evidence.append({
            "id": hashlib.sha256(f"{context.request_id}:{claim}:{quote}".encode("utf-8")).hexdigest()[:16],
            "claim": claim,
            "source_quote": quote,
            "section": _clean(candidate.section, 64),
            "dimension": _clean(candidate.dimension, 64),
            "source_request_id": _clean(context.request_id, 64),
            "verified_at": _now(),
        })
        fingerprints.add(fingerprint)
    issue["evidence"] = evidence[-MAX_EVIDENCE_PER_ISSUE:]


def _supersede_evidence(
    issue: dict[str, Any],
    evidence_ids: list[str],
    context: ResumeCoachRuntimeContext,
) -> None:
    requested = {_clean(item, 64) for item in evidence_ids if _clean(item, 64)}
    if not requested:
        return
    evidence = [item for item in issue.get("evidence", []) if isinstance(item, dict)]
    known = {str(item.get("id") or "") for item in evidence}
    unknown = requested - known
    if unknown:
        raise ValueError("要更正的证据不属于当前问题")
    request_id = _clean(context.request_id, 64)
    for item in evidence:
        if str(item.get("id") or "") in requested:
            item["status"] = "superseded"
            item["superseded_by_request_id"] = request_id


def _update_issue(issue: dict[str, Any], arguments: ResumeCoachToolInput, context: ResumeCoachRuntimeContext) -> None:
    _supersede_evidence(issue, arguments.supersede_evidence_ids, context)
    _merge_evidence(issue, arguments.evidence_candidates, context)
    # These fields are authoritative snapshots when explicitly supplied.
    # An empty list resolves stale state; omission preserves the previous value.
    fields_set = arguments.model_fields_set
    if "conclusions" in fields_set:
        issue["conclusions"] = [_clean(item, 600) for item in arguments.conclusions if _clean(item, 600)][:30]
    if "open_questions" in fields_set:
        issue["open_questions"] = [_clean(item, 500) for item in arguments.open_questions if _clean(item, 500)][:30]


def _issue_reasoning_snapshot(issue: dict[str, Any]) -> dict[str, Any]:
    return deepcopy({
        "evidence": issue.get("evidence", []),
        "conclusions": issue.get("conclusions", []),
        "open_questions": issue.get("open_questions", []),
    })


def run(arguments: ResumeCoachToolInput, context: ResumeCoachRuntimeContext) -> ResumeCoachOutput:
    state = normalize_coach_state(deepcopy(context.coach_state.model_dump()))
    operation = arguments.operation
    handoff = None

    if operation == "offer_start":
        if state["active"]:
            raise ValueError("当前已经在进行深度打磨，不能重复发起进入邀请")
        if state.get("pending_start_offer"):
            raise ValueError("当前已有等待用户确认的教练模式邀请")
        problem = _clean(arguments.problem, 1000)
        if not problem:
            raise ValueError("发起深度打磨邀请时必须说明要处理的问题")
        offer_seed = f"start:{context.request_id}:{problem}"
        state["pending_start_offer"] = {
            "offer_id": hashlib.sha256(offer_seed.encode("utf-8")).hexdigest()[:20],
            "problem": problem,
            "source_request_id": _clean(context.request_id, 80),
            "status": "offered",
        }
    elif operation == "dismiss_start":
        if state["active"]:
            raise ValueError("当前已经在进行深度打磨，请使用退出或结束问题操作")
        pending = state.get("pending_start_offer")
        requested_offer_id = _clean(arguments.offer_id, 80)
        if (
            isinstance(pending, dict)
            and requested_offer_id
            and str(pending.get("offer_id")) != requested_offer_id
        ):
            raise ValueError("要清除的教练模式邀请与当前邀请不匹配")
        state["pending_start_offer"] = None
    elif operation == "start":
        if state["active"]:
            raise ValueError("当前已经在进行深度打磨，不能重复启动")
        requested_entry = arguments.entry or (
            "explicit_command" if context.explicit_command else "explicit_request"
        )
        if context.explicit_command:
            requested_entry = "explicit_command"
        elif state.get("pending_start_offer") and requested_entry != "accepted_offer":
            raise ValueError("当前邀请必须明确接受或拒绝，不能改用其他启动来源")
        problem = _clean(arguments.problem, 1000)
        if requested_entry == "accepted_offer":
            pending = state.get("pending_start_offer")
            approval = _clean(arguments.approval_quote, 500)
            if (
                not isinstance(pending, dict)
                or pending.get("status") != "offered"
                or not arguments.offer_id
                or str(pending.get("offer_id")) != _clean(arguments.offer_id, 80)
            ):
                raise ValueError("当前没有等待用户确认的教练模式邀请")
            if not approval or re.sub(r"\s+", "", approval) not in re.sub(
                r"\s+", "", context.latest_user_message
            ):
                raise ValueError("进入教练模式必须引用用户本轮的明确同意")
            problem = _clean(pending.get("problem"), 1000)
        elif requested_entry == "explicit_request":
            authorization = _clean(arguments.approval_quote, 500)
            if not authorization or re.sub(r"\s+", "", authorization) not in re.sub(
                r"\s+", "", context.latest_user_message
            ):
                raise ValueError("启动依据必须引用用户本轮原话")
        if not problem:
            raise ValueError("启动深度打磨时必须确定一个具体问题")
        state["pending_start_offer"] = None
        state["active"] = True
        state["entry"] = requested_entry
        issue_id = _issue_id(arguments, context, problem)
        issue = _ensure_issue(state, issue_id, problem)
        _update_issue(issue, arguments, context)
    elif operation == "exit":
        current_issue_id = _clean(state.get("current_issue_id"), 64)
        current_issue = state["issues"].get(current_issue_id)
        if isinstance(current_issue, dict) and current_issue.get("status") == "active":
            current_issue["status"] = "skipped"
            current_issue["result"] = _clean(
                arguments.reason or arguments.result or "已退出深度打磨",
                1000,
            )
        state["active"] = False
        state["current_issue_id"] = ""
        state["pending_start_offer"] = None
        for issue in state["issues"].values():
            if not isinstance(issue, dict):
                continue
            offer = issue.get("pending_preview_offer")
            if isinstance(offer, dict) and offer.get("status") in {
                "offered", "authorized", "preview_generated"
            }:
                offer["status"] = "invalidated"
    else:
        if not state["active"]:
            raise ValueError("当前没有启用中的深度打磨，请先征得用户同意后开始")
        current_issue_id = _clean(state.get("current_issue_id"), 64)
        requested_issue_id = _clean(arguments.issue_id, 64)
        if not current_issue_id:
            raise ValueError("当前深度打磨尚未确定问题")
        if requested_issue_id and requested_issue_id != current_issue_id:
            raise ValueError("本轮只能处理当前活动问题")
        issue_id = current_issue_id
        issue = state["issues"].get(issue_id)
        if not isinstance(issue, dict) or issue.get("status") != "active":
            raise ValueError("当前问题不是可继续处理的活动问题")
        requested_problem = _clean(arguments.problem, 1000)
        if requested_problem and requested_problem != issue.get("problem"):
            raise ValueError("活动问题不能在处理中被替换")
        existing_offer = issue.get("pending_preview_offer")
        existing_offer_status = (
            str(existing_offer.get("status") or "")
            if isinstance(existing_offer, dict)
            else ""
        )
        if operation == "offer_preview" and existing_offer_status in {
            "offered", "authorized", "preview_generated", "undone"
        }:
            raise ValueError(
                "当前已有等待处理的修改建议，不能重复创建或覆盖；"
                "请根据用户本轮回复处理现有建议"
            )
        reasoning_before_update = _issue_reasoning_snapshot(issue)
        _update_issue(issue, arguments, context)
        if operation == "update" and existing_offer_status in {
            "offered", "authorized", "undone"
        }:
            if _issue_reasoning_snapshot(issue) == reasoning_before_update:
                raise ValueError(
                    "当前已有等待处理的修改建议；本轮没有提供新的事实或问题，"
                    "不能用普通更新代替对现有建议的处理"
                )
            existing_offer["status"] = "invalidated"

        if operation == "offer_preview":
            if arguments.proposal is None or not arguments.proposal.resume_operations:
                raise ValueError("请求生成预览授权前必须提供具体修改建议")
            summary = _clean(arguments.proposal.summary, 1000)
            if not summary:
                raise ValueError("请求生成预览授权前必须说明具体修改内容")
            offer_seed = f"{context.request_id}:{issue_id}:{arguments.proposal.model_dump_json()}:{context.source_content_digest}"
            offer_id = hashlib.sha256(offer_seed.encode("utf-8")).hexdigest()[:20]
            issue["pending_preview_offer"] = {
                "offer_id": offer_id,
                "summary": summary,
                "resume_operations": [
                    item.model_dump(exclude_none=True)
                    for item in arguments.proposal.resume_operations
                ],
                "source_content_digest": context.source_content_digest,
                "status": "offered",
            }
        elif operation == "handoff_to_edit":
            offer = issue.get("pending_preview_offer")
            approval = _clean(arguments.approval_quote, 500)
            if not isinstance(offer, dict) or offer.get("status") not in {
                "offered", "authorized", "undone"
            }:
                raise ValueError("当前没有等待用户批准的修改预览提议")
            if not approval or re.sub(r"\s+", "", approval) not in re.sub(r"\s+", "", context.latest_user_message):
                raise ValueError("预览授权必须引用本轮用户的明确回复")
            if offer.get("source_content_digest") != context.source_content_digest:
                raise ValueError("简历已经变化，请根据当前版本重新提出修改预览")
            offer["status"] = "authorized"
            handoff = EditHandoff(
                offer_id=str(offer["offer_id"]),
                summary=str(offer["summary"]),
                resume_operations=deepcopy(offer["resume_operations"]),
            )
        elif operation == "complete_issue":
            pending_offer = issue.get("pending_preview_offer")
            pending_offer_status = (
                str(pending_offer.get("status") or "")
                if isinstance(pending_offer, dict)
                else ""
            )
            if (
                arguments.completion_status == "completed"
                and pending_offer_status
                and pending_offer_status != "applied"
            ):
                raise ValueError(
                    "当前问题的修改建议尚未完整应用或已被撤回；"
                    "请继续处理当前问题，或由用户明确选择跳过"
                )
            issue["result"] = _clean(arguments.result or arguments.reason or "已结束", 1000)
            if isinstance(pending_offer, dict) and pending_offer.get("status") in {
                "offered", "authorized"
            }:
                pending_offer["status"] = "invalidated"
            issue["status"] = arguments.completion_status
            state["current_issue_id"] = ""
            next_problem = _clean(arguments.next_problem, 1000)
            next_issue_id = _clean(arguments.next_issue_id, 64)
            if next_issue_id and not next_problem:
                raise ValueError("继续处理下一个问题时必须说明具体问题")
            if next_problem:
                next_issue_id = next_issue_id or (
                    "issue-"
                    + hashlib.sha256(
                        f"{context.request_id}:{next_problem}:{len(state['issues'])}".encode(
                            "utf-8"
                        )
                    ).hexdigest()[:12]
                )
                if next_issue_id in state["issues"]:
                    raise ValueError("下一个问题必须使用新的问题标识")
                _ensure_issue(state, next_issue_id, next_problem)
                state["active"] = True
            else:
                state["active"] = False

    state["updated_at"] = _now()
    return ResumeCoachOutput(
        operation=operation,
        coach_state=state,
        active=bool(state["active"]),
        edit_handoff=handoff,
    )


def export_schemas() -> dict[str, dict[str, Any]]:
    return {
        "tool-input.schema.json": TOOL_INPUT_MODEL.model_json_schema(),
        "runtime-context.schema.json": RUNTIME_CONTEXT_MODEL.model_json_schema(),
        "output.schema.json": OUTPUT_MODEL.model_json_schema(),
        "coach-memory.schema.json": CoachState.model_json_schema(),
    }


__all__ = [
    "CoachIssue", "CoachProposal", "CoachState", "EditHandoff", "EvidenceCandidate", "EvidenceRecord", "PreviewOffer", "StartOffer", "OUTPUT_MODEL",
    "RUNTIME_CONTEXT_MODEL", "ResumeCoachOutput", "ResumeCoachRuntimeContext",
    "ResumeCoachToolInput", "TOOL_INPUT_MODEL", "empty_coach_state",
    "normalize_coach_state", "run", "export_schemas",
]
