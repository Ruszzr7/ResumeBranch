"""Deterministic resume translation with field-level translation memory."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .database import TranslationMemory, get_translation_memory, save_translation_memory
from .llm_gateway import parse_json_output
from .llm_providers import active_profile
from .resume_agent import create_llm_for_config, normalize_and_validate_resume


_CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
_NON_TRANSLATABLE_FIELDS = {
    "photo", "phone", "email", "birth_date", "graduation_date",
    "date_range", "start_date", "end_date", "gpa", "gpa_scale",
    "type", "label_bold",
}
_BATCH_SIZE = 40


@dataclass(frozen=True)
class TranslationItem:
    path: tuple[Any, ...]
    context_key: str
    source_text: str
    source_hash: str
    memory_id: str


def _context_key(path: tuple[Any, ...]) -> str:
    named = [str(part) for part in path if not isinstance(part, int)]
    return ".".join(named[-2:])[:120]


def _translation_identity(
    user_id: int,
    source_language: str,
    target_language: str,
    context_key: str,
    source_text: str,
) -> tuple[str, str]:
    source_payload = "\0".join((source_language, target_language, context_key, source_text))
    source_hash = hashlib.sha256(source_payload.encode("utf-8")).hexdigest()
    memory_id = hashlib.sha256(f"{user_id}\0{source_hash}".encode("utf-8")).hexdigest()
    return source_hash, memory_id


def _collect_items(
    value: Any,
    *,
    user_id: int,
    source_language: str,
    target_language: str,
    path: tuple[Any, ...] = (),
) -> list[TranslationItem]:
    if isinstance(value, dict):
        result: list[TranslationItem] = []
        for key, child in value.items():
            result.extend(_collect_items(
                child,
                user_id=user_id,
                source_language=source_language,
                target_language=target_language,
                path=path + (key,),
            ))
        return result
    if isinstance(value, list):
        result = []
        for index, child in enumerate(value):
            result.extend(_collect_items(
                child,
                user_id=user_id,
                source_language=source_language,
                target_language=target_language,
                path=path + (index,),
            ))
        return result
    if not isinstance(value, str) or not value.strip():
        return []
    field_name = next((str(part) for part in reversed(path) if not isinstance(part, int)), "")
    if field_name in _NON_TRANSLATABLE_FIELDS or not _CHINESE_RE.search(value):
        return []
    context_key = _context_key(path)
    source_hash, memory_id = _translation_identity(
        user_id, source_language, target_language, context_key, value,
    )
    return [TranslationItem(path, context_key, value, source_hash, memory_id)]


def _set_path(data: Any, path: tuple[Any, ...], value: str) -> None:
    target = data
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text", "")) if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content or "")


def _parse_translations(raw: str, expected_ids: list[str]) -> dict[str, str]:
    payload = parse_json_output(raw)
    values = payload.get("translations") if isinstance(payload, dict) else None
    if isinstance(values, list):
        values = {
            str(item.get("id")): item.get("text")
            for item in values if isinstance(item, dict)
        }
    if not isinstance(values, dict):
        raise ValueError("翻译 API 未返回约定的结构化结果")
    result = {str(key): value.strip() for key, value in values.items() if isinstance(value, str)}
    missing = [item_id for item_id in expected_ids if not result.get(item_id)]
    if missing:
        raise ValueError(f"翻译 API 遗漏了 {len(missing)} 项内容")
    return result


def _build_model():
    provider, profile = active_profile("chat")
    if not profile.get("api_key") or not profile.get("base_url") or not profile.get("model"):
        raise ValueError("请先配置并测试对话 API")
    return create_llm_for_config(
        api_key=profile["api_key"],
        base_url=profile["base_url"],
        model=profile["model"],
        temperature=0.0,
        provider=provider,
    )


async def translate_resume(
    db,
    user_id: int,
    resume_data: dict,
    *,
    source_language: str = "zh",
    target_language: str = "en",
    model=None,
) -> dict[str, Any]:
    """Translate textual values while preserving the canonical resume structure."""
    if source_language != "zh" or target_language != "en":
        raise ValueError("当前仅支持将中文简历翻译为英文")

    source = normalize_and_validate_resume(resume_data, include_defaults=True)
    translated = deepcopy(source)
    items = _collect_items(
        source,
        user_id=user_id,
        source_language=source_language,
        target_language=target_language,
    )
    by_memory_id = {item.memory_id: item for item in items}
    cached = get_translation_memory(db, user_id, list(by_memory_id))
    resolved: dict[str, str] = dict(cached)
    missing = [item for item in by_memory_id.values() if item.memory_id not in cached]

    if missing:
        llm = model or _build_model()
        system_prompt = (
            "You are a professional resume translator. Translate each Chinese resume text into concise, "
            "natural English suitable for a job application. Preserve every fact, number, date, proper noun, "
            "technical term, numbering marker, and Markdown emphasis. Do not add, omit, summarize, or invent "
            "content. Return only JSON in the form {\"translations\": {\"0\": \"...\"}} and include every id."
        )
        for start in range(0, len(missing), _BATCH_SIZE):
            batch = missing[start:start + _BATCH_SIZE]
            entries = [
                {"id": str(index), "field": item.context_key, "text": item.source_text}
                for index, item in enumerate(batch)
            ]
            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=json.dumps(entries, ensure_ascii=False)),
            ])
            batch_values = _parse_translations(
                _message_text(response.content),
                [str(index) for index in range(len(batch))],
            )
            for index, item in enumerate(batch):
                translated_text = batch_values[str(index)]
                resolved[item.memory_id] = translated_text
                save_translation_memory(
                    db,
                    user_id,
                    memory_id=item.memory_id,
                    source_language=source_language,
                    target_language=target_language,
                    context_key=item.context_key,
                    source_hash=item.source_hash,
                    source_text=item.source_text,
                    translated_text=translated_text,
                )

    for item in items:
        _set_path(translated, item.path, resolved[item.memory_id])

    db.commit()
    return {
        "resume_data": normalize_and_validate_resume(translated, include_defaults=True),
        "cache_hits": len(cached),
        "new_translations": len(missing),
        "total_translatable": len(by_memory_id),
    }


def restore_from_translation_memory(db, user_id: int, translated_data: dict) -> dict[str, Any]:
    """Rebuild a source snapshot for translations created before durable snapshots existed."""
    rows = db.query(TranslationMemory).filter(
        TranslationMemory.user_id == user_id,
    ).order_by(TranslationMemory.updated_at.desc()).all()
    lookup: dict[tuple[str, str], str] = {}
    for row in rows:
        lookup.setdefault((row.context_key, row.translated_text), row.source_text)

    restored = deepcopy(translated_data)
    restored_count = 0

    def walk(value: Any, path: tuple[Any, ...] = ()) -> None:
        nonlocal restored_count
        if isinstance(value, dict):
            for key, child in list(value.items()):
                child_path = path + (key,)
                if isinstance(child, str):
                    source = lookup.get((_context_key(child_path), child))
                    if source is not None:
                        value[key] = source
                        restored_count += 1
                else:
                    walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(list(value)):
                child_path = path + (index,)
                if isinstance(child, str):
                    source = lookup.get((_context_key(child_path), child))
                    if source is not None:
                        value[index] = source
                        restored_count += 1
                else:
                    walk(child, child_path)

    walk(restored)
    return {
        "resume_data": normalize_and_validate_resume(restored, include_defaults=True),
        "restored_fields": restored_count,
    }
