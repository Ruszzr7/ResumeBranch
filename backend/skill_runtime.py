"""Discover and execute repository-local Agent Skills.

The Agent Skills format defines portable folders and progressive disclosure.
This module is the ResumeBranch client adapter: it scans trusted project
skills, validates their metadata, exposes model-facing tools, and invokes the
declared Python entrypoint with graph-owned runtime context.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import inspect
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

import yaml
from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, ConfigDict, Field


_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILLS_ROOT = PROJECT_ROOT / ".agents" / "skills"


class SkillDefinitionError(ValueError):
    """Raised when a bundled Agent Skill does not satisfy its contract."""


class SkillInvocationError(RuntimeError):
    """Raised when a discovered Agent Skill cannot be executed safely."""


class ActivateAgentSkillInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="要激活的 Agent Skill 名称，必须来自可用 Skill 目录。")


@dataclass(frozen=True)
class SkillPackage:
    name: str
    description: str
    root: Path
    skill_file: Path
    instructions: str
    metadata: dict[str, Any]
    entrypoint_file: Path
    entrypoint_symbol: str
    tool_name: str
    module: ModuleType
    tool_input_model: type[BaseModel]
    runtime_context_model: type[BaseModel]
    output_model: type[BaseModel]

    def model_tool(self) -> StructuredTool:
        """Return the structured model interface owned by this Skill package."""

        def requires_runtime_context(**_: Any) -> str:
            raise SkillInvocationError(
                f"Agent Skill {self.name} 必须通过 SkillRuntime 注入当前任务上下文"
            )

        return StructuredTool.from_function(
            func=requires_runtime_context,
            name=self.tool_name,
            description=self.description,
            args_schema=self.tool_input_model,
        )


def _parse_skill_file(path: Path) -> tuple[dict[str, Any], str]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        raise SkillDefinitionError(f"{path} 缺少 YAML frontmatter")
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillDefinitionError(f"{path} 的 YAML frontmatter 起始标记无效")
    try:
        closing = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise SkillDefinitionError(f"{path} 的 YAML frontmatter 未闭合") from exc
    try:
        frontmatter = yaml.safe_load("\n".join(lines[1:closing])) or {}
    except yaml.YAMLError as exc:
        raise SkillDefinitionError(f"{path} 的 YAML frontmatter 无法解析") from exc
    if not isinstance(frontmatter, dict):
        raise SkillDefinitionError(f"{path} 的 YAML frontmatter 必须是对象")
    return frontmatter, "\n".join(lines[closing + 1:]).strip()


def _resolve_inside(root: Path, relative_path: str, *, label: str) -> Path:
    candidate = (root / relative_path).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise SkillDefinitionError(f"{label} 不能指向 Skill 目录之外")
    return candidate


def _load_entrypoint(name: str, entrypoint_file: Path) -> ModuleType:
    module_name = f"resumebranch_agent_skill_{name.replace('-', '_')}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, entrypoint_file)
    if spec is None or spec.loader is None:
        raise SkillDefinitionError(f"无法加载 Skill 入口：{entrypoint_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _require_model(module: ModuleType, attribute: str, *, skill_name: str) -> type[BaseModel]:
    value = getattr(module, attribute, None)
    if not inspect.isclass(value) or not issubclass(value, BaseModel):
        raise SkillDefinitionError(f"Skill {skill_name} 缺少 {attribute} Pydantic 模型")
    return value


class SkillRuntime:
    """Repository-local Agent Skills client with progressive disclosure."""

    def __init__(self, skills_root: Path | None = None):
        self.skills_root = (skills_root or DEFAULT_SKILLS_ROOT).resolve()
        self._skills: dict[str, SkillPackage] | None = None

    def discover(self, *, refresh: bool = False) -> dict[str, SkillPackage]:
        if self._skills is not None and not refresh:
            return dict(self._skills)
        discovered: dict[str, SkillPackage] = {}
        if not self.skills_root.is_dir():
            self._skills = discovered
            return {}
        for skill_file in sorted(self.skills_root.glob("*/SKILL.md")):
            package = self._load_package(skill_file)
            if package.name in discovered:
                raise SkillDefinitionError(f"Agent Skill 名称重复：{package.name}")
            if package.tool_name in {item.tool_name for item in discovered.values()}:
                raise SkillDefinitionError(f"Agent Skill Tool 名称重复：{package.tool_name}")
            discovered[package.name] = package
        self._skills = discovered
        return dict(discovered)

    def _load_package(self, skill_file: Path) -> SkillPackage:
        root = skill_file.parent.resolve()
        frontmatter, instructions = _parse_skill_file(skill_file)
        name = str(frontmatter.get("name") or "").strip()
        description = str(frontmatter.get("description") or "").strip()
        if not name or len(name) > 64 or not _SKILL_NAME_RE.fullmatch(name):
            raise SkillDefinitionError(f"Agent Skill 名称无效：{name or '<empty>'}")
        if root.name != name:
            raise SkillDefinitionError(f"Agent Skill 名称必须与目录一致：{root.name} != {name}")
        if not description or len(description) > 1024:
            raise SkillDefinitionError(f"Agent Skill {name} 的 description 无效")
        if not instructions:
            raise SkillDefinitionError(f"Agent Skill {name} 缺少说明正文")
        metadata = frontmatter.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise SkillDefinitionError(f"Agent Skill {name} 的 metadata 必须是对象")
        raw_entrypoint = str(metadata.get("entrypoint") or "").strip()
        if ":" not in raw_entrypoint:
            raise SkillDefinitionError(f"Agent Skill {name} 缺少有效 entrypoint")
        entrypoint_path, entrypoint_symbol = raw_entrypoint.rsplit(":", 1)
        entrypoint_file = _resolve_inside(root, entrypoint_path, label="entrypoint")
        if not entrypoint_file.is_file() or not entrypoint_symbol.strip():
            raise SkillDefinitionError(f"Agent Skill {name} 的 entrypoint 不存在")
        tool_name = str(metadata.get("tool-name") or name.replace("-", "_")).strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", tool_name):
            raise SkillDefinitionError(f"Agent Skill {name} 的 tool-name 无效")
        for key in ("tool-input-schema", "runtime-context-schema", "output-schema"):
            schema_path = str(metadata.get(key) or "").strip()
            if not schema_path:
                raise SkillDefinitionError(f"Agent Skill {name} 缺少 {key}")
            if not _resolve_inside(root, schema_path, label=key).is_file():
                raise SkillDefinitionError(f"Agent Skill {name} 的 {key} 不存在")
        module = _load_entrypoint(name, entrypoint_file)
        entrypoint = getattr(module, entrypoint_symbol.strip(), None)
        if not callable(entrypoint):
            raise SkillDefinitionError(f"Agent Skill {name} 的入口函数不存在")
        return SkillPackage(
            name=name,
            description=description,
            root=root,
            skill_file=skill_file.resolve(),
            instructions=instructions,
            metadata=dict(metadata),
            entrypoint_file=entrypoint_file,
            entrypoint_symbol=entrypoint_symbol.strip(),
            tool_name=tool_name,
            module=module,
            tool_input_model=_require_model(module, "TOOL_INPUT_MODEL", skill_name=name),
            runtime_context_model=_require_model(module, "RUNTIME_CONTEXT_MODEL", skill_name=name),
            output_model=_require_model(module, "OUTPUT_MODEL", skill_name=name),
        )

    def get(self, name: str) -> SkillPackage:
        try:
            return self.discover()[name]
        except KeyError as exc:
            raise SkillDefinitionError(f"未发现 Agent Skill：{name}") from exc

    def get_by_tool_name(self, tool_name: str) -> SkillPackage:
        for package in self.discover().values():
            if package.tool_name == tool_name:
                return package
        raise SkillDefinitionError(f"未发现 Agent Skill Tool：{tool_name}")

    def catalog_context(self) -> str:
        rows = [
            f"- `{package.name}`：{package.description}"
            for package in self.discover().values()
        ]
        return (
            "\n\n【可用 Agent Skills】\n"
            "下面只提供用于发现的名称和描述。需要使用某项能力时，先调用 "
            "activate_agent_skill；激活前不得猜测其参数或调用其执行 Tool。\n"
            + "\n".join(rows)
        )

    def active_instructions_context(self, names: Iterable[str]) -> str:
        sections = []
        for name in dict.fromkeys(str(item) for item in names if item):
            package = self.get(name)
            sections.append(
                f"\n\n【已激活 Agent Skill：{package.name}】\n{package.instructions}"
            )
        return "".join(sections)

    def tools_for(self, names: Iterable[str]) -> list[StructuredTool]:
        return [
            self.get(name).model_tool()
            for name in dict.fromkeys(str(item) for item in names if item)
        ]

    async def invoke(self, name: str, arguments: dict, context: dict) -> Any:
        package = self.get(name)
        validated_arguments = package.tool_input_model.model_validate(arguments or {})
        validated_context = package.runtime_context_model.model_validate(context or {})
        entrypoint = getattr(package.module, package.entrypoint_symbol)
        result = entrypoint(validated_arguments, validated_context)
        if inspect.isawaitable(result):
            result = await result
        return package.output_model.model_validate(result, from_attributes=True)


skill_runtime = SkillRuntime()


@tool(args_schema=ActivateAgentSkillInput)
def activate_agent_skill(name: str) -> str:
    """激活一个已发现的 Agent Skill，以加载其完整说明和结构化执行工具。"""
    package = skill_runtime.get(name)
    return f"已激活 Agent Skill：{package.name}。请按照已加载说明继续处理当前请求。"


__all__ = [
    "DEFAULT_SKILLS_ROOT",
    "SkillDefinitionError",
    "SkillInvocationError",
    "SkillPackage",
    "SkillRuntime",
    "activate_agent_skill",
    "skill_runtime",
]
