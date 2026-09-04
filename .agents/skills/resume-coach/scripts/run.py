"""Deterministic state and provenance boundary for the resume-coach Skill."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    resume_operations: list[dict[str, Any]]


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    claim: str
    source_quote: str
    section: str = ""
    dimension: str = ""
    source_request_id: str
    verified_at: str


class PreviewOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str
    summary: str
    resume_operations: list[dict[str, Any]]
    source_content_digest: str
    status: Literal["offered", "authorized"]


class CoachIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem: str = ""
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
    updated_at: str = ""


class ResumeCoachToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal[
        "start", "update", "offer_preview", "handoff_to_edit", "complete_issue", "exit"
    ]
    issue_id: str = ""
    problem: str = ""
    evidence_candidates: list[EvidenceCandidate] = Field(default_factory=list)
    conclusions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    proposal: CoachProposal | None = None
    approval_quote: str = ""
    result: str = ""
    reason: str = ""


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
    resume_operations: list[dict[str, Any]]


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
            "evidence": [item for item in raw_issue.get("evidence", []) if isinstance(item, dict)][-MAX_EVIDENCE_PER_ISSUE:],
            "conclusions": [_clean(item, 600) for item in raw_issue.get("conclusions", []) if _clean(item, 600)][:30],
            "open_questions": [_clean(item, 500) for item in raw_issue.get("open_questions", []) if _clean(item, 500)][:30],
            "pending_preview_offer": raw_issue.get("pending_preview_offer") if isinstance(raw_issue.get("pending_preview_offer"), dict) else None,
            "result": _clean(raw_issue.get("result"), 1000),
        }
    result["issues"] = normalized_issues
    current = _clean(source.get("current_issue_id"), 64)
    result["current_issue_id"] = current if current in normalized_issues else ""
    result["updated_at"] = _clean(source.get("updated_at"), 64) or result["updated_at"]
    return result


def _issue_id(arguments: ResumeCoachToolInput, context: ResumeCoachRuntimeContext) -> str:
    requested = _clean(arguments.issue_id, 64)
    if requested:
        return requested
    seed = f"{context.request_id}:{arguments.problem}:{len(context.coach_state.issues)}"
    return "issue-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _ensure_issue(state: dict[str, Any], issue_id: str, problem: str = "") -> dict[str, Any]:
    issues = state["issues"]
    if issue_id not in issues:
        if len(issues) >= MAX_ISSUES:
            raise ValueError("当前深度打磨已达到问题数量上限，请先结束本次会话")
        issues[issue_id] = {
            "problem": _clean(problem, 1000),
            "evidence": [],
            "conclusions": [],
            "open_questions": [],
            "pending_preview_offer": None,
            "result": "",
        }
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


def _update_issue(issue: dict[str, Any], arguments: ResumeCoachToolInput, context: ResumeCoachRuntimeContext) -> None:
    _merge_evidence(issue, arguments.evidence_candidates, context)
    if arguments.conclusions:
        issue["conclusions"] = [_clean(item, 600) for item in arguments.conclusions if _clean(item, 600)][:30]
    if arguments.open_questions:
        issue["open_questions"] = [_clean(item, 500) for item in arguments.open_questions if _clean(item, 500)][:30]


def run(arguments: ResumeCoachToolInput, context: ResumeCoachRuntimeContext) -> ResumeCoachOutput:
    state = normalize_coach_state(deepcopy(context.coach_state.model_dump()))
    operation = arguments.operation
    handoff = None

    if operation == "start":
        state["active"] = True
        state["entry"] = "explicit_command" if context.explicit_command else "explicit_request"
        issue_id = _issue_id(arguments, context)
        issue = _ensure_issue(state, issue_id, arguments.problem)
        _update_issue(issue, arguments, context)
    elif operation == "exit":
        state["active"] = False
    else:
        if not state["active"]:
            raise ValueError("当前没有启用中的深度打磨，请先征得用户同意后开始")
        issue_id = _clean(arguments.issue_id, 64) or state["current_issue_id"]
        if not issue_id:
            raise ValueError("当前深度打磨尚未确定问题")
        issue = _ensure_issue(state, issue_id, arguments.problem)
        _update_issue(issue, arguments, context)

        if operation == "offer_preview":
            if arguments.proposal is None or not arguments.proposal.resume_operations:
                raise ValueError("请求生成预览授权前必须提供具体修改建议")
            offer_seed = f"{context.request_id}:{issue_id}:{arguments.proposal.model_dump_json()}:{context.source_content_digest}"
            offer_id = hashlib.sha256(offer_seed.encode("utf-8")).hexdigest()[:20]
            issue["pending_preview_offer"] = {
                "offer_id": offer_id,
                "summary": _clean(arguments.proposal.summary, 1000),
                "resume_operations": deepcopy(arguments.proposal.resume_operations),
                "source_content_digest": context.source_content_digest,
                "status": "offered",
            }
        elif operation == "handoff_to_edit":
            offer = issue.get("pending_preview_offer")
            approval = _clean(arguments.approval_quote, 500)
            if not isinstance(offer, dict) or offer.get("status") != "offered":
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
            issue["result"] = _clean(arguments.result or arguments.reason or "已结束", 1000)
            issue["pending_preview_offer"] = None

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
    "CoachIssue", "CoachProposal", "CoachState", "EditHandoff", "EvidenceCandidate", "EvidenceRecord", "PreviewOffer", "OUTPUT_MODEL",
    "RUNTIME_CONTEXT_MODEL", "ResumeCoachOutput", "ResumeCoachRuntimeContext",
    "ResumeCoachToolInput", "TOOL_INPUT_MODEL", "empty_coach_state",
    "normalize_coach_state", "run", "export_schemas",
]
