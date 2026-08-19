"""Persist only workflow-control state through a LangGraph checkpointer."""

from __future__ import annotations

import asyncio
import os
import threading
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph


WORKFLOW_SCHEMA_VERSION = 1
DEFAULT_CHECKPOINT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "langgraph_checkpoints.sqlite"
)


class WorkflowState(TypedDict, total=False):
    """Small, durable control plane; business payloads never belong here."""

    schema_version: int
    user_id: int
    task_id: str
    session_id: str
    interaction_mode: str
    status: str
    phase: str
    focus_section: str
    current_question: str
    last_node: str
    last_request_id: str
    turn_count: int
    updated_at: str


WORKFLOW_STATE_KEYS = frozenset(WorkflowState.__annotations__)
WORKFLOW_UPDATE_KEYS = WORKFLOW_STATE_KEYS - {
    "schema_version",
    "user_id",
    "task_id",
    "turn_count",
    "updated_at",
}
WORKFLOW_MODES = frozenset({"chat", "diagnosis", "coaching", "jd_review", "interview"})
WORKFLOW_STATUSES = frozenset({
    "ready",
    "active",
    "paused",
    "awaiting_confirmation",
    "completed",
    "error",
})


def build_workflow_thread_id(user_id: int, task_id: str, context_id: str | None = None) -> str:
    """Build a checkpoint key isolated by resume task and optional mission."""
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        raise ValueError("task_id is required for workflow checkpoint isolation")
    normalized_context_id = str(context_id or "").strip()
    if normalized_context_id:
        return f"user:{int(user_id)}:task:{normalized_task_id}:context:{normalized_context_id}"
    return f"user:{int(user_id)}:task:{normalized_task_id}"


def workflow_config(user_id: int, task_id: str, context_id: str | None = None) -> dict:
    return {
        "configurable": {
            "thread_id": build_workflow_thread_id(user_id, task_id, context_id),
        }
    }


def _checkpoint_node(_state: WorkflowState) -> dict:
    """The graph boundary itself is intentional; state updates arrive as input."""
    return {}


def build_workflow_graph(checkpointer):
    builder = StateGraph(WorkflowState)
    builder.add_node("checkpoint_workflow", _checkpoint_node)
    builder.add_edge(START, "checkpoint_workflow")
    builder.add_edge("checkpoint_workflow", END)
    return builder.compile(checkpointer=checkpointer)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _normalize_updates(updates: dict) -> dict:
    unknown = set(updates) - WORKFLOW_UPDATE_KEYS
    if unknown:
        raise ValueError(f"unsupported workflow state fields: {sorted(unknown)}")
    normalized = dict(updates)
    if "interaction_mode" in normalized:
        mode = _bounded_text(normalized["interaction_mode"], 32) or "chat"
        if mode not in WORKFLOW_MODES:
            raise ValueError(f"unsupported interaction_mode: {mode}")
        normalized["interaction_mode"] = mode
    if "status" in normalized:
        status = _bounded_text(normalized["status"], 32) or "ready"
        if status not in WORKFLOW_STATUSES:
            raise ValueError(f"unsupported workflow status: {status}")
        normalized["status"] = status
    for key, limit in {
        "session_id": 36,
        "phase": 64,
        "focus_section": 64,
        "current_question": 1000,
        "last_node": 64,
        "last_request_id": 64,
    }.items():
        if key in normalized:
            normalized[key] = _bounded_text(normalized[key], limit)
    return normalized


def _base_payload(current: dict, user_id: int, task_id: str) -> WorkflowState:
    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "user_id": int(user_id),
        "task_id": str(task_id),
        "session_id": str(current.get("session_id", "") or ""),
        "interaction_mode": str(current.get("interaction_mode", "chat") or "chat"),
        "status": str(current.get("status", "ready") or "ready"),
        "phase": str(current.get("phase", "idle") or "idle"),
        "focus_section": str(current.get("focus_section", "") or ""),
        "current_question": str(current.get("current_question", "") or ""),
        "last_node": str(current.get("last_node", "") or ""),
        "last_request_id": str(current.get("last_request_id", "") or ""),
        "turn_count": int(current.get("turn_count", 0) or 0),
        "updated_at": _now_iso(),
    }


class WorkflowCheckpointManager:
    """Thread-safe SQLite workflow checkpointer with an async application API."""

    def __init__(self, path: str | os.PathLike | None = None, *, enabled: bool | None = None):
        if enabled is None:
            enabled = os.getenv("AGENT_CHECKPOINTER_ENABLED", "true").lower() not in {
                "0", "false", "no", "off",
            }
        self.enabled = bool(enabled)
        self.path = str(path or os.getenv("AGENT_CHECKPOINT_DB_PATH") or DEFAULT_CHECKPOINT_PATH)
        self._lock = threading.RLock()
        self._context: AbstractContextManager | None = None
        self._saver = None
        self._graph = None

    def start_sync(self):
        if not self.enabled:
            return self
        with self._lock:
            if self._graph is not None:
                return self
            if self.path != ":memory:":
                Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            self._context = SqliteSaver.from_conn_string(self.path)
            self._saver = self._context.__enter__()
            self._saver.setup()
            self._graph = build_workflow_graph(self._saver)
        return self

    async def start(self):
        return await asyncio.to_thread(self.start_sync)

    def close_sync(self):
        with self._lock:
            context = self._context
            self._context = None
            self._saver = None
            self._graph = None
            if context is not None:
                context.__exit__(None, None, None)

    async def close(self):
        await asyncio.to_thread(self.close_sync)

    def _ensure_started(self):
        if self.enabled and self._graph is None:
            self.start_sync()

    def load_state_sync(self, user_id: int, task_id: str, context_id: str | None = None) -> WorkflowState:
        if not self.enabled:
            return {}
        self._ensure_started()
        with self._lock:
            snapshot = self._graph.get_state(workflow_config(user_id, task_id, context_id))
            return dict(snapshot.values or {})

    async def load_state(self, user_id: int, task_id: str, context_id: str | None = None) -> WorkflowState:
        return await asyncio.to_thread(self.load_state_sync, user_id, task_id, context_id)

    def update_state_sync(
        self, user_id: int, task_id: str, *, context_id: str | None = None, **updates
    ) -> WorkflowState:
        if not self.enabled:
            return {}
        self._ensure_started()
        normalized = _normalize_updates(updates)
        config = workflow_config(user_id, task_id, context_id)
        with self._lock:
            current = dict(self._graph.get_state(config).values or {})
            payload = _base_payload(current, user_id, task_id)
            payload.update(normalized)
            result = self._graph.invoke(payload, config=config)
            return dict(result)

    async def update_state(self, user_id: int, task_id: str, *, context_id: str | None = None, **updates) -> WorkflowState:
        return await asyncio.to_thread(self.update_state_sync, user_id, task_id, context_id=context_id, **updates)

    def record_turn_sync(
        self,
        user_id: int,
        task_id: str,
        *,
        session_id: str,
        request_id: str,
        interaction_mode: str | None = None,
        context_id: str | None = None,
    ) -> WorkflowState:
        if not self.enabled:
            return {}
        self._ensure_started()
        config = workflow_config(user_id, task_id, context_id)
        with self._lock:
            current = dict(self._graph.get_state(config).values or {})
            if request_id and current.get("last_request_id") == request_id:
                return current
            updates = _normalize_updates({
                "session_id": session_id,
                "last_request_id": request_id,
                **({"interaction_mode": interaction_mode} if interaction_mode else {}),
                **({
                    "status": "active" if interaction_mode != "chat" else "ready",
                } if interaction_mode else {}),
            })
            payload = _base_payload(current, user_id, task_id)
            payload.update(updates)
            payload["turn_count"] = int(current.get("turn_count", 0) or 0) + 1
            return dict(self._graph.invoke(payload, config=config))

    async def record_turn(self, user_id: int, task_id: str, **kwargs) -> WorkflowState:
        return await asyncio.to_thread(self.record_turn_sync, user_id, task_id, **kwargs)

    def pause_sync(self, user_id: int, task_id: str, context_id: str | None = None) -> WorkflowState:
        return self.update_state_sync(user_id, task_id, context_id=context_id, status="paused")

    def resume_sync(self, user_id: int, task_id: str, context_id: str | None = None) -> WorkflowState:
        return self.update_state_sync(user_id, task_id, context_id=context_id, status="active")

    def delete_thread_sync(self, user_id: int, task_id: str, context_id: str | None = None):
        if not self.enabled:
            return
        self._ensure_started()
        with self._lock:
            self._saver.delete_thread(build_workflow_thread_id(user_id, task_id, context_id))

    def cleanup_stale_sync(
        self,
        retention_days: int | None = None,
        *,
        now: datetime | None = None,
    ) -> int:
        """Delete whole stale control threads; business memory is untouched."""
        if not self.enabled:
            return 0
        self._ensure_started()
        if retention_days is None:
            try:
                retention_days = int(os.getenv("AGENT_CHECKPOINT_RETENTION_DAYS", "30"))
            except ValueError:
                retention_days = 30
        if retention_days < 0:
            return 0
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        stale_thread_ids = []
        seen = set()
        with self._lock:
            for item in self._saver.list(None):
                thread_id = str(item.config.get("configurable", {}).get("thread_id", ""))
                if not thread_id or thread_id in seen:
                    continue
                seen.add(thread_id)
                values = item.checkpoint.get("channel_values", {})
                raw_updated_at = str(values.get("updated_at", "") or "")
                try:
                    updated_at = datetime.fromisoformat(raw_updated_at.replace("Z", "+00:00"))
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if updated_at < cutoff:
                    stale_thread_ids.append(thread_id)
            for thread_id in stale_thread_ids:
                self._saver.delete_thread(thread_id)
        return len(stale_thread_ids)

    async def cleanup_stale(self, retention_days: int | None = None) -> int:
        return await asyncio.to_thread(self.cleanup_stale_sync, retention_days)

    async def delete_thread(self, user_id: int, task_id: str, context_id: str | None = None):
        await asyncio.to_thread(self.delete_thread_sync, user_id, task_id, context_id)
