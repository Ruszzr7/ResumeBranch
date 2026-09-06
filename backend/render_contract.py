"""Renderer-facing semantic content helpers.

PDF and DOCX remain different output engines, but they must receive the same
canonical blocks and flow descriptors before applying engine-specific markup.
"""

from __future__ import annotations

from typing import Any, Iterator

from .layout_config import ordered_experience_content_blocks, resolve_content_block_flow
from .resume_contract import normalize_content_block, normalize_content_blocks


def iter_experience_content_blocks(
    item: dict[str, Any] | None,
    *,
    experience_kind: str = "project",
    layout_config: dict | None = None,
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Yield ``(canonical_block, flow)`` pairs in configured display order."""
    item = item if isinstance(item, dict) else {}
    blocks = ordered_experience_content_blocks(item, layout_config, experience_kind=experience_kind)
    for raw in blocks:
        block = normalize_content_block(raw)
        if block is None:
            continue
        flow = resolve_content_block_flow(block)
        if flow["visible"]:
            yield block, flow
