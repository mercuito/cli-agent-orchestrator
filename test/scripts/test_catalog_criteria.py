"""Tests for the criteria catalog helper script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "catalog_criteria.py"
SPEC = importlib.util.spec_from_file_location("catalog_criteria", SCRIPT_PATH)
assert SPEC is not None
catalog_criteria = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = catalog_criteria
SPEC.loader.exec_module(catalog_criteria)


def _write_criteria_file(path: Path, name: str, when: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n" f"name: {name}\n" f"when: {when}\n" "---\n\n" f"# {name}\n",
        encoding="utf-8",
    )


def test_discover_criteria_reads_name_when_kind_and_relative_path(tmp_path: Path) -> None:
    """Criteria entries should be read from both implementation and test catalogs."""
    _write_criteria_file(
        tmp_path / "docs" / "criteria" / "implementation" / "minimal.md",
        "minimal",
        "A task changes production code.",
    )
    _write_criteria_file(
        tmp_path / "docs" / "criteria" / "tests" / "given-when-then.md",
        "given-when-then",
        "Always.",
    )

    entries = catalog_criteria.discover_criteria(tmp_path)

    assert entries == [
        catalog_criteria.CriteriaEntry(
            kind="implementation",
            name="minimal",
            when="A task changes production code.",
            path="docs/criteria/implementation/minimal.md",
        ),
        catalog_criteria.CriteriaEntry(
            kind="tests",
            name="given-when-then",
            when="Always.",
            path="docs/criteria/tests/given-when-then.md",
        ),
    ]


def test_format_text_catalog_groups_entries_by_kind() -> None:
    """Text output should be easy for agents to scan before loading full files."""
    entries = [
        catalog_criteria.CriteriaEntry(
            kind="implementation",
            name="minimal",
            when="A task changes production code.",
            path="docs/criteria/implementation/minimal.md",
        ),
        catalog_criteria.CriteriaEntry(
            kind="tests",
            name="given-when-then",
            when="Always.",
            path="docs/criteria/tests/given-when-then.md",
        ),
    ]

    output = catalog_criteria.format_text_catalog(entries)

    assert output == (
        "implementation:\n"
        "- minimal\n"
        "  when: A task changes production code.\n"
        "  path: docs/criteria/implementation/minimal.md\n"
        "\n"
        "tests:\n"
        "- given-when-then\n"
        "  when: Always.\n"
        "  path: docs/criteria/tests/given-when-then.md"
    )


def test_discover_criteria_rejects_missing_required_frontmatter(tmp_path: Path) -> None:
    """Malformed criteria files should fail before an agent trusts the catalog."""
    criteria_file = tmp_path / "docs" / "criteria" / "implementation" / "broken.md"
    criteria_file.parent.mkdir(parents=True, exist_ok=True)
    criteria_file.write_text("---\nname: broken\n---\n\n# Broken\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required frontmatter field 'when'"):
        catalog_criteria.discover_criteria(tmp_path)
