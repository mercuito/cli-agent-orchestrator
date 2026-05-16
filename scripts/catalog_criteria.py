#!/usr/bin/env python3
"""Print a compact catalog of planning criteria from docs/criteria."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import frontmatter

CRITERIA_KINDS = ("implementation", "tests")


@dataclass(frozen=True)
class CriteriaEntry:
    """A criteria file's planning metadata."""

    kind: str
    name: str
    when: str
    path: str


def _load_criteria_entry(criteria_file: Path, repo_root: Path) -> CriteriaEntry:
    post = frontmatter.load(criteria_file)
    metadata = dict(post.metadata)

    kind = criteria_file.parent.name
    if kind not in CRITERIA_KINDS:
        raise ValueError(f"{criteria_file} is under unsupported criteria kind '{kind}'")

    name = metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{criteria_file} is missing required frontmatter field 'name'")

    when = metadata.get("when")
    if not isinstance(when, str) or not when.strip():
        raise ValueError(f"{criteria_file} is missing required frontmatter field 'when'")

    return CriteriaEntry(
        kind=kind,
        name=name.strip(),
        when=when.strip(),
        path=criteria_file.relative_to(repo_root).as_posix(),
    )


def discover_criteria(repo_root: Path, kind: str | None = None) -> list[CriteriaEntry]:
    """Return criteria catalog entries sorted by kind and file path."""
    root = repo_root / "docs" / "criteria"
    kinds = (kind,) if kind else CRITERIA_KINDS
    entries: list[CriteriaEntry] = []

    for criteria_kind in kinds:
        if criteria_kind not in CRITERIA_KINDS:
            raise ValueError(f"Unsupported criteria kind '{criteria_kind}'")

        criteria_dir = root / criteria_kind
        if not criteria_dir.exists():
            continue

        for criteria_file in sorted(criteria_dir.glob("*.md")):
            entries.append(_load_criteria_entry(criteria_file, repo_root))

    return entries


def format_text_catalog(entries: Sequence[CriteriaEntry]) -> str:
    """Format entries as grouped plain text for quick agent scanning."""
    lines: list[str] = []
    for kind in CRITERIA_KINDS:
        kind_entries = [entry for entry in entries if entry.kind == kind]
        if not kind_entries:
            continue

        if lines:
            lines.append("")
        lines.append(f"{kind}:")
        for entry in kind_entries:
            lines.extend(
                [
                    f"- {entry.name}",
                    f"  when: {entry.when}",
                    f"  path: {entry.path}",
                ]
            )

    return "\n".join(lines)


def format_json_catalog(entries: Iterable[CriteriaEntry]) -> str:
    """Format entries as stable JSON for tooling."""
    return json.dumps([asdict(entry) for entry in entries], indent=2)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print criteria names and 'when' clauses from docs/criteria.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing docs/criteria. Defaults to the current directory.",
    )
    parser.add_argument(
        "--kind",
        choices=CRITERIA_KINDS,
        help="Limit output to one criteria kind.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Defaults to text.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.root.resolve()
    entries = discover_criteria(repo_root, kind=args.kind)

    if args.format == "json":
        print(format_json_catalog(entries))
    else:
        print(format_text_catalog(entries))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
