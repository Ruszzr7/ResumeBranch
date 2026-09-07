"""Shared structured operation contract for resume-edit capable Skills."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResumeEditOperation(BaseModel):
    """模型提供的一条标准化修改操作。"""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set", "replace", "append", "insert", "remove", "move"] = Field(
        description="操作类型。"
    )
    path: str = Field(min_length=1, description="契约定义的最小可写路径。")
    value: Any | None = Field(default=None, description="set、replace、append 或 insert 的目标值。")
    index: int | None = Field(default=None, description="insert 或列表 remove 的目标索引。")
    from_index: int | None = Field(default=None, description="move 的原始索引。")
    to_index: int | None = Field(default=None, description="move 的目标索引。")
    target_semantic_role: Literal[
        "tech_stack", "introduction", "responsibilities", "generic"
    ] | None = Field(default=None, description="内容块的稳定语义角色，仅用于 content_blocks。")

    @model_validator(mode="after")
    def validate_operation_fields(self):
        if self.op in {"set", "replace", "append", "insert"} and self.value is None:
            raise ValueError(f"{self.op} 操作必须提供 value")
        if self.op == "insert" and self.index is None:
            raise ValueError("insert 操作必须提供 index")
        if self.op == "move" and (self.from_index is None or self.to_index is None):
            raise ValueError("move 操作必须提供 from_index 和 to_index")
        return self


__all__ = ["ResumeEditOperation"]
