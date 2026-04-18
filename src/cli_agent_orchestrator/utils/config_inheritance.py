"""Generic primitive for inheriting a CLI tool's global config into CAO.

When CAO spawns an agent inside a CLI tool that reads a global config file
(e.g. Codex's ``~/.codex/config.toml``), CAO needs to pick what from that
global config should carry over into the per-session environment it creates.
Cloning the whole config is unsafe — global configs contain relative
filesystem paths, user-level MCP registrations, user-installed plugins, and
other state that either breaks or bloats CAO sessions.

This module offers a data-first, format-neutral primitive:

- :class:`InheritPolicy` describes *what* to inherit (allowlist), *what* to
  suppress (plugins), and *what* to explicitly force (extra_overrides).
- :func:`apply_inherit_policy` applies a policy to a parsed config dict and
  returns a new dict ready to serialize into the per-session config file.

It operates on plain dicts, so callers are responsible for parsing (TOML,
JSON, YAML, ...) and for serialising the result. Today only the Codex
provider uses this; other providers either pass config via CLI flags or
manage per-agent config at install time rather than per-terminal.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping


@dataclass(frozen=True)
class InheritPolicy:
    """Describes how to inherit a CLI tool's global config into CAO sessions.

    Attributes:
        allowlist: Top-level keys to carry over from the global config as-is.
            Keys not in this set are dropped. Default-deny is the only safe
            posture because global configs can contain relative filesystem
            paths (e.g. ``[agents.*].config_file``) that silently break when
            the config is copied to a different directory.
        disable_plugins: When True, for each entry found under ``[plugins]``
            in the global config, emit an explicit ``enabled = false`` in the
            output. This overrides the CLI's plugin auto-discovery so globally
            enabled plugins don't bleed into CAO sessions (plugins can add
            tens of thousands of tokens of tool schemas per session). Has no
            effect if the global config has no ``[plugins]`` section.
        extra_overrides: Explicit values deep-merged into the output LAST, so
            they override both inherited values and plugin-disable entries.
            Use for per-session flags CAO wants to force regardless of user
            globals (e.g. disabling a CLI's own multi-agent feature when CAO
            itself is the orchestration layer).
    """

    allowlist: frozenset[str]
    disable_plugins: bool = False
    extra_overrides: Mapping[str, Any] = field(default_factory=dict)


def deep_merge(base: Dict[str, Any], updates: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``updates`` into ``base`` (mutates ``base``).

    When both sides hold a dict at the same key, their contents are merged
    recursively. When either side holds a non-dict, the update wins wholesale.
    Returns the mutated ``base`` for call-site convenience.
    """
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value if not isinstance(value, dict) else copy.deepcopy(value)
    return base


def apply_inherit_policy(
    global_config: Mapping[str, Any],
    policy: InheritPolicy,
) -> Dict[str, Any]:
    """Filter ``global_config`` through ``policy`` and return a new dict.

    Order of operations:
      1. Start empty.
      2. Copy every allowlisted top-level key from ``global_config``
         (deep-copied so callers can't mutate the source via the result).
      3. If ``disable_plugins`` is set, add ``enabled = false`` entries for
         every plugin found in ``global_config['plugins']``.
      4. Deep-merge ``extra_overrides`` on top (overrides win conflicts).

    Never mutates ``global_config``.
    """
    output: Dict[str, Any] = {}

    for key in policy.allowlist:
        if key in global_config:
            output[key] = copy.deepcopy(global_config[key])

    if policy.disable_plugins:
        plugins = global_config.get("plugins")
        if isinstance(plugins, dict) and plugins:
            disabled = {name: {"enabled": False} for name in plugins}
            output["plugins"] = deep_merge(output.get("plugins", {}), disabled)

    if policy.extra_overrides:
        deep_merge(output, policy.extra_overrides)

    return output
