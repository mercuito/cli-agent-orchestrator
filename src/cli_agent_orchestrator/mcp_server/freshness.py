"""Agent-visible MCP tool freshness descriptors for runtime freshness."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import textwrap
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Optional, cast

from fastmcp.tools.base import Tool

from cli_agent_orchestrator.agent import Agent
from cli_agent_orchestrator.services.baton_feature import BATON_MCP_TOOL_NAMES
from cli_agent_orchestrator.workspace_providers.tool_access import (
    ProviderMediatedToolRuntimeGenerationDescriptor,
    ProviderMediatedToolSurfaceDescriptor,
    ProviderToolAccessPolicy,
)

MCP_SURFACE_DESCRIPTOR_SCHEMA_VERSION = "cao-agent-mcp-surface.v1"
MCP_RUNTIME_GENERATION_DESCRIPTOR_SCHEMA_VERSION = "cao-agent-mcp-runtime-generation.v1"

PendingBuiltInMCPTool = tuple[str, Callable[..., Any], Mapping[str, Any]]


def build_agent_mcp_surface_descriptor(
    *,
    agent: Agent,
    built_in_tools: Iterable[PendingBuiltInMCPTool],
    built_in_tool_allowlist: Optional[Iterable[str]],
    provider_policies: Mapping[str, ProviderToolAccessPolicy],
    baton_enabled: bool,
) -> dict[str, Any]:
    """Build the stable MCP contract visible to one CAO agent."""
    built_ins = _visible_builtin_tool_entries(
        built_in_tools=built_in_tools,
        allowlist=built_in_tool_allowlist,
        baton_enabled=baton_enabled,
    )
    reserved_builtin_names = {tool_name for tool_name, _, _ in built_in_tools}
    provider_tools = _visible_provider_tool_entries(
        agent=agent,
        policies=provider_policies,
        reserved_tool_names=reserved_builtin_names,
    )
    descriptor = {
        "schema_version": MCP_SURFACE_DESCRIPTOR_SCHEMA_VERSION,
        "tools": sorted(
            [*built_ins, *provider_tools],
            key=lambda entry: (
                str(entry["source"]["kind"]),
                str(entry["source"]["name"]),
                str(entry["name"]),
            ),
        ),
    }
    return cast(dict[str, Any], _canonicalize(descriptor))


def fingerprint_agent_mcp_surface(descriptor: Mapping[str, Any]) -> str:
    """Return a deterministic hash of an MCP surface descriptor."""
    return hashlib.sha256(_canonical_json_bytes(descriptor)).hexdigest()


def build_agent_mcp_surface_fingerprint(
    *,
    agent: Agent,
    built_in_tools: Iterable[PendingBuiltInMCPTool],
    built_in_tool_allowlist: Optional[Iterable[str]],
    provider_policies: Mapping[str, ProviderToolAccessPolicy],
    baton_enabled: bool,
) -> str:
    """Build and fingerprint the stable MCP contract visible to one agent."""
    return fingerprint_agent_mcp_surface(
        build_agent_mcp_surface_descriptor(
            agent=agent,
            built_in_tools=built_in_tools,
            built_in_tool_allowlist=built_in_tool_allowlist,
            provider_policies=provider_policies,
            baton_enabled=baton_enabled,
        )
    )


def build_agent_mcp_runtime_generation_descriptor(
    *,
    agent: Agent,
    built_in_tools: Iterable[PendingBuiltInMCPTool],
    built_in_tool_allowlist: Optional[Iterable[str]],
    provider_policies: Mapping[str, ProviderToolAccessPolicy],
    baton_enabled: bool,
    built_in_runtime_generation: Mapping[str, Any],
) -> dict[str, Any]:
    """Build implementation/runtime material behind visible MCP tools."""
    built_ins = _visible_builtin_tool_entries(
        built_in_tools=built_in_tools,
        allowlist=built_in_tool_allowlist,
        baton_enabled=baton_enabled,
    )
    reserved_builtin_names = {tool_name for tool_name, _, _ in built_in_tools}
    provider_tools = _visible_provider_runtime_generation_entries(
        agent=agent,
        policies=provider_policies,
        reserved_tool_names=reserved_builtin_names,
    )
    descriptor = {
        "schema_version": MCP_RUNTIME_GENERATION_DESCRIPTOR_SCHEMA_VERSION,
        "tools": sorted(
            [
                *(
                    {
                        "source": entry["source"],
                        "name": entry["name"],
                        "runtime_generation": _runtime_generation_for_tool(
                            built_in_runtime_generation, str(entry["name"])
                        ),
                    }
                    for entry in built_ins
                ),
                *provider_tools,
            ],
            key=lambda entry: (
                str(entry["source"]["kind"]),
                str(entry["source"]["name"]),
                str(entry["name"]),
            ),
        ),
    }
    return cast(dict[str, Any], _canonicalize(descriptor))


def build_agent_mcp_runtime_generation_fingerprint(
    *,
    agent: Agent,
    built_in_tools: Iterable[PendingBuiltInMCPTool],
    built_in_tool_allowlist: Optional[Iterable[str]],
    provider_policies: Mapping[str, ProviderToolAccessPolicy],
    baton_enabled: bool,
    built_in_runtime_generation: Mapping[str, Any],
) -> str:
    """Build and fingerprint implementation/runtime material behind visible tools."""
    return fingerprint_agent_mcp_surface(
        build_agent_mcp_runtime_generation_descriptor(
            agent=agent,
            built_in_tools=built_in_tools,
            built_in_tool_allowlist=built_in_tool_allowlist,
            provider_policies=provider_policies,
            baton_enabled=baton_enabled,
            built_in_runtime_generation=built_in_runtime_generation,
        )
    )


def file_content_fingerprint(paths: Iterable[Path]) -> dict[str, Any]:
    """Return deterministic content hashes for existing files.

    The generation signal is content-based instead of mtime-based so a CAO
    restart after a code fix changes freshness only when relevant files changed.
    """
    entries = []
    for path in sorted({Path(item).resolve() for item in paths}, key=lambda item: str(item)):
        if not path.exists() or not path.is_file():
            continue
        entries.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema_version": "cao-file-content-fingerprint.v1",
        "files": entries,
    }


def callable_runtime_fingerprint(
    fn: Callable[..., Any],
    *,
    dependency_modules: Mapping[str, ModuleType] | None = None,
    max_depth: int = 3,
    follow_local_helpers: bool = True,
) -> dict[str, Any]:
    """Return stable source material for one callable and its local helpers.

    The traversal intentionally starts at a visible tool callable and follows
    local helper/query callables it references. That keeps hidden sibling tools
    from staling an agent while still catching ordinary wrapper/helper edits
    behind visible MCP tools.
    """
    dependency_modules = dependency_modules or {}
    entries: dict[str, dict[str, Any]] = {}
    _collect_callable_runtime_entries(
        fn,
        entries=entries,
        dependency_modules=dependency_modules,
        max_depth=max_depth,
        depth=0,
        follow_local_helpers=follow_local_helpers,
    )
    return {
        "schema_version": "cao-callable-runtime-fingerprint.v1",
        "entries": [entries[key] for key in sorted(entries)],
    }


def callable_source_fingerprint(fn: Callable[..., Any]) -> dict[str, Any]:
    """Return stable local source material for one callable."""
    target = getattr(fn, "__func__", fn)
    try:
        source = inspect.getsource(target)
    except (OSError, TypeError):
        source = repr(target)
    return {
        "schema_version": "cao-callable-source-fingerprint.v1",
        "module": getattr(target, "__module__", ""),
        "qualname": getattr(target, "__qualname__", repr(target)),
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }


def _collect_callable_runtime_entries(
    fn: Callable[..., Any],
    *,
    entries: dict[str, dict[str, Any]],
    dependency_modules: Mapping[str, ModuleType],
    max_depth: int,
    depth: int,
    follow_local_helpers: bool,
) -> None:
    target = getattr(fn, "__func__", fn)
    module = inspect.getmodule(target)
    entry = callable_source_fingerprint(target)
    key = f"{entry['module']}:{entry['qualname']}"
    if key in entries:
        return
    entries[key] = entry
    if depth >= max_depth:
        return
    references = _callable_source_references(target)
    if follow_local_helpers and module is not None:
        for name in references.names:
            if not name.startswith("_"):
                continue
            candidate = getattr(module, name, None)
            if inspect.isfunction(candidate) or inspect.ismethod(candidate):
                _collect_callable_runtime_entries(
                    candidate,
                    entries=entries,
                    dependency_modules=dependency_modules,
                    max_depth=max_depth,
                    depth=depth + 1,
                    follow_local_helpers=follow_local_helpers,
                )
    owner = getattr(target, "__qualname__", "").split(".")[0]
    owner_obj = getattr(module, owner, None) if module is not None else None
    if follow_local_helpers:
        for attr_name in references.attributes:
            if not attr_name.startswith("_"):
                continue
            candidate = getattr(owner_obj, attr_name, None)
            if inspect.isfunction(candidate) or inspect.ismethod(candidate):
                _collect_callable_runtime_entries(
                    candidate,
                    entries=entries,
                    dependency_modules=dependency_modules,
                    max_depth=max_depth,
                    depth=depth + 1,
                    follow_local_helpers=follow_local_helpers,
                )
    for module_alias, attr_names in references.module_attributes.items():
        dependency_module = dependency_modules.get(module_alias)
        if dependency_module is None:
            continue
        for attr_name in attr_names:
            candidate = getattr(dependency_module, attr_name, None)
            if inspect.isfunction(candidate) or inspect.ismethod(candidate):
                _collect_callable_runtime_entries(
                    candidate,
                    entries=entries,
                    dependency_modules=dependency_modules,
                    max_depth=max_depth,
                    depth=depth + 1,
                    follow_local_helpers=follow_local_helpers,
                )


class _CallableSourceReferences:
    def __init__(
        self,
        *,
        names: set[str],
        attributes: set[str],
        module_attributes: dict[str, set[str]],
    ) -> None:
        self.names = names
        self.attributes = attributes
        self.module_attributes = module_attributes


def _callable_source_references(fn: Callable[..., Any]) -> _CallableSourceReferences:
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return _CallableSourceReferences(names=set(), attributes=set(), module_attributes={})
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return _CallableSourceReferences(names=set(), attributes=set(), module_attributes={})
    names: set[str] = set()
    attributes: set[str] = set()
    module_attributes: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)
            if isinstance(node.value, ast.Name):
                module_attributes.setdefault(node.value.id, set()).add(node.attr)
    return _CallableSourceReferences(
        names=names,
        attributes=attributes,
        module_attributes=module_attributes,
    )


def _visible_builtin_tool_entries(
    *,
    built_in_tools: Iterable[PendingBuiltInMCPTool],
    allowlist: Optional[Iterable[str]],
    baton_enabled: bool,
) -> list[dict[str, Any]]:
    allowed = None if allowlist is None else set(allowlist)
    entries: list[dict[str, Any]] = []
    for tool_name, fn, tool_kwargs in built_in_tools:
        if tool_name in BATON_MCP_TOOL_NAMES and not baton_enabled:
            continue
        if allowed is not None and tool_name not in allowed:
            continue
        tool = Tool.from_function(fn, name=tool_name, **dict(tool_kwargs))
        entries.append(
            {
                "source": {"kind": "cao_builtin", "name": "cao"},
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.parameters,
            }
        )
    return sorted(entries, key=lambda entry: str(entry["name"]))


def _visible_provider_tool_entries(
    *,
    agent: Agent,
    policies: Mapping[str, ProviderToolAccessPolicy],
    reserved_tool_names: set[str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_provider_tool_names: set[str] = set()
    descriptors: list[ProviderMediatedToolSurfaceDescriptor] = []
    for provider_name in sorted(policies):
        descriptors.extend(policies[provider_name].surface_descriptors_for_agent(agent))

    for descriptor in sorted(descriptors, key=lambda item: (item.provider_name, item.name)):
        if descriptor.name in reserved_tool_names:
            continue
        if descriptor.name in seen_provider_tool_names:
            continue
        seen_provider_tool_names.add(descriptor.name)
        entries.append(
            {
                "source": {"kind": "provider", "name": descriptor.provider_name},
                "name": descriptor.name,
                "description": descriptor.description,
                "input_schema": descriptor.input_schema,
                "pre_hooks": descriptor.pre_hooks,
                "post_hooks": descriptor.post_hooks,
            }
        )
    return entries


def _visible_provider_runtime_generation_entries(
    *,
    agent: Agent,
    policies: Mapping[str, ProviderToolAccessPolicy],
    reserved_tool_names: set[str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_provider_tool_names: set[str] = set()
    descriptors: list[ProviderMediatedToolRuntimeGenerationDescriptor] = []
    for provider_name in sorted(policies):
        descriptors.extend(policies[provider_name].runtime_generation_descriptors_for_agent(agent))

    for descriptor in sorted(descriptors, key=lambda item: (item.provider_name, item.name)):
        if descriptor.name in reserved_tool_names:
            continue
        if descriptor.name in seen_provider_tool_names:
            continue
        seen_provider_tool_names.add(descriptor.name)
        entries.append(
            {
                "source": {"kind": "provider", "name": descriptor.provider_name},
                "name": descriptor.name,
                "runtime_generation": descriptor.runtime_generation,
            }
        )
    return entries


def _runtime_generation_for_tool(material: Mapping[str, Any], tool_name: str) -> Mapping[str, Any]:
    tools = material.get("tools")
    if isinstance(tools, Mapping):
        value = tools.get(tool_name)
        if isinstance(value, Mapping):
            return value
        return {}
    return material


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, set):
        return [_canonicalize(item) for item in sorted(value, key=repr)]
    return value


__all__ = [
    "MCP_RUNTIME_GENERATION_DESCRIPTOR_SCHEMA_VERSION",
    "MCP_SURFACE_DESCRIPTOR_SCHEMA_VERSION",
    "PendingBuiltInMCPTool",
    "build_agent_mcp_runtime_generation_descriptor",
    "build_agent_mcp_runtime_generation_fingerprint",
    "build_agent_mcp_surface_descriptor",
    "build_agent_mcp_surface_fingerprint",
    "callable_runtime_fingerprint",
    "callable_source_fingerprint",
    "file_content_fingerprint",
    "fingerprint_agent_mcp_surface",
]
