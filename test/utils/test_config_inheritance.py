"""Tests for the generic config-inheritance primitive.

Covers the allowlist filter, plugin-disable behaviour, override merging, and
defensive handling of malformed global configs. Any provider that needs to
inherit a filtered slice of its CLI tool's global config file should use
this primitive; today only Codex does.
"""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.utils.config_inheritance import (
    InheritPolicy,
    apply_inherit_policy,
    deep_merge,
)


class TestApplyInheritPolicyAllowlist:
    def test_copies_allowlisted_top_level_keys(self):
        policy = InheritPolicy(allowlist=frozenset({"model", "reasoning"}))
        result = apply_inherit_policy(
            {"model": "gpt-5.4", "reasoning": "high", "other": "dropped"},
            policy,
        )
        assert result == {"model": "gpt-5.4", "reasoning": "high"}

    def test_drops_non_allowlisted_keys_including_nested_tables(self):
        policy = InheritPolicy(allowlist=frozenset({"model"}))
        result = apply_inherit_policy(
            {
                "model": "gpt-5.4",
                "mcp_servers": {"github": {"command": "gh"}},
                "agents": {"impl": {"config_file": "agents/impl.toml"}},
                "plugins": {"github@openai-curated": {"enabled": True}},
            },
            policy,
        )
        assert result == {"model": "gpt-5.4"}

    def test_empty_global_config_returns_empty_dict(self):
        policy = InheritPolicy(allowlist=frozenset({"model"}))
        assert apply_inherit_policy({}, policy) == {}

    def test_allowlist_entries_missing_from_global_are_silently_omitted(self):
        policy = InheritPolicy(allowlist=frozenset({"model", "reasoning"}))
        result = apply_inherit_policy({"model": "gpt-5.4"}, policy)
        assert result == {"model": "gpt-5.4"}
        assert "reasoning" not in result

    def test_empty_allowlist_drops_everything(self):
        policy = InheritPolicy(allowlist=frozenset())
        assert apply_inherit_policy({"model": "x", "other": "y"}, policy) == {}

    def test_allowlisted_nested_tables_are_deep_copied(self):
        """Returned dict must not share mutable references with the input."""
        policy = InheritPolicy(allowlist=frozenset({"notice"}))
        original = {"notice": {"hide_warning": True, "nested": {"k": "v"}}}
        result = apply_inherit_policy(original, policy)
        # Mutating result should not affect the source.
        result["notice"]["hide_warning"] = False
        result["notice"]["nested"]["k"] = "mutated"
        assert original["notice"]["hide_warning"] is True
        assert original["notice"]["nested"]["k"] == "v"


class TestApplyInheritPolicyDisablePlugins:
    def test_writes_enabled_false_for_every_global_plugin(self):
        policy = InheritPolicy(allowlist=frozenset(), disable_plugins=True)
        result = apply_inherit_policy(
            {
                "plugins": {
                    "github@openai-curated": {"enabled": True},
                    "other-plugin": {"enabled": True, "extra": "ignored"},
                }
            },
            policy,
        )
        assert result["plugins"] == {
            "github@openai-curated": {"enabled": False},
            "other-plugin": {"enabled": False},
        }

    def test_disable_plugins_false_does_not_touch_plugins(self):
        policy = InheritPolicy(allowlist=frozenset(), disable_plugins=False)
        result = apply_inherit_policy(
            {"plugins": {"github@openai-curated": {"enabled": True}}},
            policy,
        )
        assert "plugins" not in result

    def test_disable_plugins_with_no_plugins_section_is_noop(self):
        policy = InheritPolicy(allowlist=frozenset(), disable_plugins=True)
        result = apply_inherit_policy({"model": "x"}, policy)
        assert "plugins" not in result

    def test_disable_plugins_with_empty_plugins_dict(self):
        policy = InheritPolicy(allowlist=frozenset(), disable_plugins=True)
        result = apply_inherit_policy({"plugins": {}}, policy)
        # No plugins to disable — no plugins key emitted.
        assert "plugins" not in result

    def test_disable_plugins_ignores_malformed_plugins_section(self):
        """If [plugins] is somehow not a table, degrade gracefully."""
        policy = InheritPolicy(allowlist=frozenset(), disable_plugins=True)
        result = apply_inherit_policy({"plugins": "this-should-be-a-table"}, policy)
        assert "plugins" not in result

    def test_disable_plugins_coexists_with_allowlist(self):
        policy = InheritPolicy(
            allowlist=frozenset({"model"}), disable_plugins=True
        )
        result = apply_inherit_policy(
            {
                "model": "gpt-5.4",
                "plugins": {"github@openai-curated": {"enabled": True}},
            },
            policy,
        )
        assert result == {
            "model": "gpt-5.4",
            "plugins": {"github@openai-curated": {"enabled": False}},
        }


class TestApplyInheritPolicyOverrides:
    def test_overrides_are_merged_after_allowlist(self):
        policy = InheritPolicy(
            allowlist=frozenset({"model"}),
            extra_overrides={"features": {"multi_agent": False}},
        )
        result = apply_inherit_policy({"model": "gpt-5.4"}, policy)
        assert result == {
            "model": "gpt-5.4",
            "features": {"multi_agent": False},
        }

    def test_overrides_win_conflicts_with_inherited_values(self):
        policy = InheritPolicy(
            allowlist=frozenset({"model"}),
            extra_overrides={"model": "cao-override"},
        )
        result = apply_inherit_policy({"model": "gpt-5.4"}, policy)
        assert result == {"model": "cao-override"}

    def test_overrides_deep_merge_with_inherited_nested_tables(self):
        policy = InheritPolicy(
            allowlist=frozenset({"notice"}),
            extra_overrides={"notice": {"hide_warning": False}},
        )
        result = apply_inherit_policy(
            {"notice": {"hide_warning": True, "model_migrations": {"a": "b"}}},
            policy,
        )
        assert result == {
            "notice": {
                "hide_warning": False,
                "model_migrations": {"a": "b"},
            }
        }

    def test_overrides_win_over_plugin_disable_for_same_plugin(self):
        """If an explicit override re-enables a plugin, the override wins."""
        policy = InheritPolicy(
            allowlist=frozenset(),
            disable_plugins=True,
            extra_overrides={
                "plugins": {"github@openai-curated": {"enabled": True}}
            },
        )
        result = apply_inherit_policy(
            {"plugins": {"github@openai-curated": {"enabled": True}}},
            policy,
        )
        assert result["plugins"]["github@openai-curated"]["enabled"] is True

    def test_overrides_do_not_mutate_the_policy(self):
        """extra_overrides is a mapping; the policy must be effectively immutable."""
        overrides = {"features": {"multi_agent": False}}
        policy = InheritPolicy(
            allowlist=frozenset({"model"}), extra_overrides=overrides
        )
        apply_inherit_policy({"model": "x"}, policy)
        apply_inherit_policy({"model": "y"}, policy)
        assert overrides == {"features": {"multi_agent": False}}


class TestApplyInheritPolicyInputSafety:
    def test_does_not_mutate_the_global_config(self):
        policy = InheritPolicy(
            allowlist=frozenset({"notice"}),
            disable_plugins=True,
            extra_overrides={"features": {"multi_agent": False}},
        )
        original = {
            "notice": {"hide_warning": True},
            "plugins": {"github@openai-curated": {"enabled": True}},
            "dropped": "value",
        }
        snapshot = {
            "notice": {"hide_warning": True},
            "plugins": {"github@openai-curated": {"enabled": True}},
            "dropped": "value",
        }
        apply_inherit_policy(original, policy)
        assert original == snapshot


class TestInheritPolicyIsFrozen:
    def test_cannot_mutate_fields(self):
        policy = InheritPolicy(allowlist=frozenset({"model"}))
        with pytest.raises((AttributeError, TypeError)):
            policy.allowlist = frozenset({"other"})  # type: ignore[misc]


class TestDeepMerge:
    """The helper ``deep_merge`` must behave the same way the private
    ``_merge_into`` did in ``codex_home.py`` (it replaces that function)."""

    def test_merges_scalar_into_empty_base(self):
        base = {}
        deep_merge(base, {"model": "gpt-5.4"})
        assert base == {"model": "gpt-5.4"}

    def test_updates_override_base_for_same_key(self):
        base = {"model": "old"}
        deep_merge(base, {"model": "new"})
        assert base == {"model": "new"}

    def test_recursively_merges_nested_dicts(self):
        base = {"a": {"b": 1, "c": 2}}
        deep_merge(base, {"a": {"c": 20, "d": 30}})
        assert base == {"a": {"b": 1, "c": 20, "d": 30}}

    def test_scalar_update_replaces_base_dict_wholesale(self):
        """When types disagree (dict ↔ scalar), the update wins (no deep merge)."""
        base = {"features": {"multi_agent": True}}
        deep_merge(base, {"features": "disabled"})
        assert base == {"features": "disabled"}

    def test_dict_update_replaces_base_scalar(self):
        base = {"features": "enabled"}
        deep_merge(base, {"features": {"multi_agent": False}})
        assert base == {"features": {"multi_agent": False}}

    def test_returns_the_mutated_base(self):
        base = {"a": 1}
        result = deep_merge(base, {"b": 2})
        assert result is base
