"""Structured, read-only resume interview coaching primitives.

This module owns business-memory validation and deterministic state transitions.
The LangGraph checkpointer stores only the small control projection returned by
``workflow_updates``; verified facts remain in ``AgentMemoryState``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..resume_data import normalize_resume_data
from ..prompt_contract import build_model_contract_context


INTERVIEW_SCHEMA_VERSION = 1
INTERVIEW_MODES = frozenset({"diagnosis", "coaching", "jd_review"})
INTERVIEW_ACTIONS = frozenset({"start", "answer", "pause", "resume", "end", "apply"})
ACTIVE_PHASES = frozenset({"diagnosing", "questioning", "synthesizing", "awaiting_apply"})


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def interview_feature_config(user_id: int, task_id: str) -> dict:
    """Return a stable rollout decision so one task never flips between paths."""
    enabled = _env_bool("INTERVIEW_HARNESS_ENABLED", True)
    try:
        rollout = max(0, min(100, int(os.getenv("INTERVIEW_HARNESS_ROLLOUT_PERCENT", "100"))))
    except ValueError:
        rollout = 100
    digest = hashlib.sha256(f"{int(user_id)}:{task_id}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % 100
    return {
        "enabled": bool(enabled and bucket < rollout),
        "shadow": _env_bool("INTERVIEW_HARNESS_SHADOW", False),
        "bucket": bucket,
        "rollout_percent": rollout,
    }


def empty_interview_memory(mode: str = "coaching") -> dict:
    return {
        "schema_version": INTERVIEW_SCHEMA_VERSION,
        "mode": mode if mode in INTERVIEW_MODES else "coaching",
        "verified_facts": [],
        "rejected_suggestions": [],
        "open_items": [],
        "latest_suggestion": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_interview_memory(value: Any, mode: str | None = None) -> dict:
    source = value if isinstance(value, dict) else {}
    normalized = empty_interview_memory(mode or str(source.get("mode", "coaching")))
    if mode in INTERVIEW_MODES:
        normalized["mode"] = mode
    for key, limit in (("verified_facts", 100), ("rejected_suggestions", 50), ("open_items", 30)):
        items = source.get(key, [])
        normalized[key] = [item for item in items if isinstance(item, (dict, str))][:limit]
    suggestion = source.get("latest_suggestion")
    normalized["latest_suggestion"] = suggestion if isinstance(suggestion, dict) else None
    normalized["updated_at"] = str(source.get("updated_at") or normalized["updated_at"])
    return normalized


def resolve_interview_action(action: str | None, workflow: dict, explicit_mode: str | None) -> str:
    requested = str(action or "").strip().lower()
    if requested in INTERVIEW_ACTIONS:
        return requested
    phase = str((workflow or {}).get("phase", "idle"))
    status = str((workflow or {}).get("status", "ready"))
    if explicit_mode in INTERVIEW_MODES or phase in {"idle", "completed"} or status == "ready":
        return "start"
    return "answer"


def is_active_interview_workflow(workflow: dict | None) -> bool:
    workflow = workflow or {}
    return (
        workflow.get("interaction_mode") in INTERVIEW_MODES
        and workflow.get("status") in {"active", "paused"}
        and workflow.get("phase") not in {"idle", "completed"}
    )


def _extract_json(content: Any) -> dict:
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("interview output must be a JSON object")
    return parsed


def _clean_text(value: Any, limit: int = 1000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _without_question_marks(value: Any, limit: int = 1000) -> str:
    return _clean_text(value, limit).replace("？", "").replace("?", "")


def _safe_question(value: Any, fallback: str) -> str:
    question = _without_question_marks(value or fallback, 500).rstrip("。.!！；;：:")
    return f"{question}？"


def _numeric_tokens(value: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", value or ""))


def validate_fact_candidates(candidates: Any, user_answer: str, request_id: str) -> list[dict]:
    """Accept only claims explicitly grounded in the current user answer."""
    answer = _clean_text(user_answer, 8000)
    compact_answer = re.sub(r"\s+", "", answer)
    accepted = []
    if not answer or not isinstance(candidates, list):
        return accepted
    for item in candidates[:12]:
        if not isinstance(item, dict):
            continue
        claim = _clean_text(item.get("claim"), 500)
        quote = _clean_text(item.get("source_quote"), 500)
        compact_quote = re.sub(r"\s+", "", quote)
        if not claim or len(compact_quote) < 2 or compact_quote not in compact_answer:
            continue
        if not _numeric_tokens(claim).issubset(_numeric_tokens(quote)):
            continue
        accepted.append({
            "id": hashlib.sha256(f"{request_id}:{claim}:{quote}".encode("utf-8")).hexdigest()[:16],
            # The canonical fact is the user's verbatim quote. Model-authored
            # paraphrases are never promoted to verified memory.
            "claim": quote,
            "section": _clean_text(item.get("section"), 64),
            "dimension": _clean_text(item.get("dimension"), 64),
            "source_type": "user_message",
            "source_quote": quote,
            "source_request_id": str(request_id or "")[:64],
            "verified_at": datetime.now(timezone.utc).isoformat(),
        })
    return accepted


def merge_verified_facts(existing: list, incoming: list) -> list[dict]:
    result = [item for item in existing if isinstance(item, dict)]
    fingerprints = {(item.get("claim"), item.get("source_quote")) for item in result}
    for item in incoming:
        fingerprint = (item.get("claim"), item.get("source_quote"))
        if fingerprint not in fingerprints:
            result.append(item)
            fingerprints.add(fingerprint)
    return result[-100:]


def _path_parts(path: str) -> list[str | int]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|\d+))*", path or ""):
        raise ValueError("invalid suggestion path")
    parts: list[str | int] = []
    for part in path.split("."):
        parts.append(int(part) if part.isdigit() else part)
    if not parts or parts[0] not in {
        "basics", "education", "research_interests", "honors", "work_experience",
        "project_experience", "custom_sections", "others", "self_evaluation",
    }:
        raise ValueError("unsupported suggestion root")
    return parts


def _value_at_path(payload: Any, parts: list[str | int]) -> Any:
    current = payload
    for part in parts:
        if isinstance(part, int):
            if not isinstance(current, list) or part < 0 or part >= len(current):
                raise ValueError("suggestion index out of range")
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                raise ValueError("suggestion field does not exist")
            current = current[part]
    return current


def validate_suggestion(raw: Any, resume_data: dict, verified_facts: list[dict]) -> dict | None:
    if not isinstance(raw, dict) or not verified_facts:
        return None
    path = _clean_text(raw.get("target_path"), 160)
    suggested = _clean_text(raw.get("suggested"), 1200)
    rationale = _clean_text(raw.get("rationale"), 600)
    if not path or not suggested:
        return None
    try:
        current = _value_at_path(resume_data, _path_parts(path))
    except ValueError:
        return None
    if not isinstance(current, str) or current == suggested:
        return None
    sourced_text = " ".join(
        f"{item.get('claim', '')} {item.get('source_quote', '')}" for item in verified_facts
    ) + f" {current}"
    if not _numeric_tokens(suggested).issubset(_numeric_tokens(sourced_text)):
        return None
    return {
        "target_path": path,
        "original": current,
        "suggested": suggested,
        "rationale": rationale or "基于本轮已核实信息，使表述更具体、可验证。",
    }


def apply_suggestion_candidate(resume_data: dict, suggestion: dict) -> dict:
    """Apply one already-validated suggestion to a copy; never persist it here."""
    candidate = deepcopy(normalize_resume_data(resume_data or {}))
    parts = _path_parts(str((suggestion or {}).get("target_path", "")))
    original = _value_at_path(candidate, parts)
    if not isinstance(original, str) or original != suggestion.get("original"):
        raise ValueError("简历已变化，建议需要重新生成")
    current: Any = candidate
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = str(suggestion.get("suggested", ""))
    return normalize_resume_data(candidate)


def _workflow_projection(mode: str, phase: str, question: str, focus: str, status: str = "active") -> dict:
    return {
        "interaction_mode": mode,
        "status": status,
        "phase": phase,
        "focus_section": _clean_text(focus, 64),
        "current_question": question[:1000],
        "last_node": "interview_coach",
    }


def workflow_public_state(state: dict | None, memory: dict | None = None) -> dict:
    state = state or {}
    memory = normalize_interview_memory(memory or {}, str(state.get("interaction_mode") or "coaching"))
    return {
        "interaction_mode": str(state.get("interaction_mode", "chat")),
        "status": str(state.get("status", "ready")),
        "phase": str(state.get("phase", "idle")),
        "focus_section": str(state.get("focus_section", "")),
        "current_question": str(state.get("current_question", "")),
        "turn_count": int(state.get("turn_count", 0) or 0),
        "fact_count": len(memory.get("verified_facts", [])),
        "has_suggestion": bool(memory.get("latest_suggestion")),
        "updated_at": str(state.get("updated_at", "")),
    }


def handle_control_action(action: str, mode: str, workflow: dict, memory: dict) -> dict | None:
    if action == "pause":
        if workflow.get("status") != "active":
            return {
                "content": "当前深度打磨不在进行中，无需暂停。",
                "memory": memory,
                "workflow_updates": _workflow_projection(
                    mode, str(workflow.get("phase") or "idle"),
                    str(workflow.get("current_question") or ""),
                    str(workflow.get("focus_section") or ""),
                    str(workflow.get("status") or "ready"),
                ),
            }
        return {
            "content": "本轮深度打磨已暂停。已核实的信息会保留，继续后会从当前问题接上。",
            "memory": memory,
            "workflow_updates": _workflow_projection(
                mode, str(workflow.get("phase") or "questioning"),
                str(workflow.get("current_question") or ""), str(workflow.get("focus_section") or ""), "paused",
            ),
        }
    if action == "end":
        if workflow.get("status") == "completed":
            return {
                "content": "本轮深度打磨已经结束。",
                "memory": memory,
                "workflow_updates": _workflow_projection(mode, "completed", "", "", "completed"),
            }
        return {
            "content": "本轮深度打磨已结束。已核实的信息仍会保留，之后可以重新诊断或继续完善。",
            "memory": memory,
            "workflow_updates": _workflow_projection(mode, "completed", "", "", "completed"),
        }
    if action == "resume" and workflow.get("status") == "paused":
        question = _safe_question(
            workflow.get("current_question"), "请继续回答暂停前的这个问题",
        )
        return {
            "content": f"已继续本轮深度打磨。\n\n{question}",
            "memory": memory,
            "workflow_updates": _workflow_projection(
                mode, str(workflow.get("phase") or "questioning"), question,
                str(workflow.get("focus_section") or ""), "active",
            ),
        }
    if action == "resume":
        return {
            "content": "当前深度打磨并未暂停。",
            "memory": memory,
            "workflow_updates": _workflow_projection(
                mode, str(workflow.get("phase") or "questioning"),
                str(workflow.get("current_question") or ""),
                str(workflow.get("focus_section") or ""),
                str(workflow.get("status") or "active"),
            ),
        }
    return None


async def run_interview_turn(
    *, llm, action: str, mode: str, user_text: str, resume_data: dict,
    jd_data: dict, memory: dict, workflow: dict, request_id: str,
    layout_data: dict | None = None,
) -> dict:
    """Run one structured coaching turn and return validated state changes."""
    mode = mode if mode in INTERVIEW_MODES else "coaching"
    memory = normalize_interview_memory(memory, mode)
    control = handle_control_action(action, mode, workflow, memory)
    if control:
        return control
    if workflow.get("status") == "paused" and action not in {"resume", "end"}:
        return handle_control_action("pause", mode, workflow, memory)
    if workflow.get("status") == "completed" and action != "start":
        return handle_control_action("end", mode, workflow, memory)

    prompt = f"""你是严格但尊重事实的简历面试教练。输出且只输出一个 JSON 对象。

模式：{mode}
动作：{action}
本轮用户原话：{user_text}

当前简历（只读）：
{json.dumps(normalize_resume_data(resume_data or {}), ensure_ascii=False)}

当前排版与经历内容契约（只读）：
{build_model_contract_context(layout_data)}

目标岗位 JD（只读，可能为空）：
{json.dumps(jd_data or {}, ensure_ascii=False)}

此前已核实事实（每条都带用户原话来源）：
{json.dumps(memory.get('verified_facts', []), ensure_ascii=False)}

严格规则：
1. 不得修改简历，不得声称已经保存；不得把推断当成用户事实。
2. 每轮最多问一个问题。question 必须只含一个聚焦问题。
3. action=start 时先诊断；action=answer 时只从“本轮用户原话”提取 fact_candidates。
4. 每个 fact_candidate 必须包含 claim、source_quote、section、dimension；source_quote 必须逐字摘自本轮用户原话。
5. 不得补造数字。claim 中的每个数字必须在 source_quote 中出现。
6. 信息足够时可给 suggestion，包含 target_path、suggested、rationale。target_path 必须指向当前简历中一个既有字符串字段，例如 work_experience.0.content_blocks.0.items.0；建议只能使用已核实事实。
7. 如果给出 suggestion，将 phase 设为 awaiting_apply；否则为 questioning。
8. diagnosis_summary、strengths、gaps、acknowledgement 均应简洁；不要在这些字段中提问。

JSON 结构：
{{"diagnosis_summary":"", "strengths":[""], "gaps":[""], "acknowledgement":"", "focus_section":"", "dimension":"", "question":"", "phase":"questioning", "fact_candidates":[{{"claim":"", "source_quote":"", "section":"", "dimension":""}}], "open_items":[""], "rejected_suggestions":[""], "suggestion":null}}
"""
    response = await llm.ainvoke([
        SystemMessage(content="只输出合法 JSON；你无权修改或保存简历。"),
        HumanMessage(content=prompt),
    ])
    parsed = _extract_json(getattr(response, "content", response))

    incoming = validate_fact_candidates(
        parsed.get("fact_candidates"), user_text if action == "answer" else "", request_id,
    )
    facts = merge_verified_facts(memory.get("verified_facts", []), incoming)
    memory["verified_facts"] = facts
    memory["open_items"] = [
        _without_question_marks(item, 240) for item in parsed.get("open_items", []) if _clean_text(item)
    ][:30]
    rejected = [
        _without_question_marks(item, 300) for item in parsed.get("rejected_suggestions", []) if _clean_text(item)
    ]
    memory["rejected_suggestions"] = (memory.get("rejected_suggestions", []) + rejected)[-50:]
    suggestion = validate_suggestion(parsed.get("suggestion"), normalize_resume_data(resume_data or {}), facts)
    memory["latest_suggestion"] = suggestion
    memory["updated_at"] = datetime.now(timezone.utc).isoformat()

    fallback_question = {
        "diagnosis": "你最希望这份简历优先解决哪一个求职障碍",
        "jd_review": "这个岗位最看重、但简历里还没有证据的一项能力是什么",
        "coaching": "这段经历中最能证明你贡献的一个具体结果是什么",
    }[mode]
    question = _safe_question(parsed.get("question"), fallback_question)
    phase = "awaiting_apply" if suggestion else "questioning"
    focus = _clean_text(parsed.get("focus_section"), 64)

    sections = []
    summary = _without_question_marks(parsed.get("diagnosis_summary"), 800)
    acknowledgement = _without_question_marks(parsed.get("acknowledgement"), 500)
    if action == "start" and summary:
        sections.append(summary)
    if acknowledgement:
        sections.append(acknowledgement)
    strengths = [_without_question_marks(item, 300) for item in parsed.get("strengths", []) if _clean_text(item)][:3]
    gaps = [_without_question_marks(item, 300) for item in parsed.get("gaps", []) if _clean_text(item)][:5]
    if strengths:
        sections.append("已体现的优势：\n" + "\n".join(f"- {item}" for item in strengths))
    if gaps:
        sections.append("优先补强项：\n" + "\n".join(f"- {item}" for item in gaps))
    if suggestion:
        sections.append(
            "可应用的改写建议：\n"
            f"- 原文：{_without_question_marks(suggestion['original'], 1200)}\n"
            f"- 建议：{_without_question_marks(suggestion['suggested'], 1200)}\n"
            f"- 理由：{_without_question_marks(suggestion['rationale'], 600)}\n"
            "如需写入，请点击“应用建议”，系统仍会先展示修改预览。"
        )
    sections.append(question)
    return {
        "content": "\n\n".join(item for item in sections if item),
        "memory": memory,
        "workflow_updates": _workflow_projection(mode, phase, question, focus, "active"),
    }
