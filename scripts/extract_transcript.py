#!/usr/bin/env python3
"""Extract conversation text from Claude Code session JSONL transcripts.

Outputs markdown with just user and assistant text. Drops tool calls,
tool results, thinking blocks, and other state events.

Usage:
    extract_transcript.py <session-uuid-or-path>   # print to stdout
    extract_transcript.py --dump [--force]         # mirror all sessions to ~/.claude/transcripts/
    extract_transcript.py --list                   # list sessions with first user message
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

CLAUDE_HOME = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_HOME / "projects"
TRANSCRIPTS_DIR = CLAUDE_HOME / "transcripts"


def iter_jsonl(path: Path):
    with path.open() as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"warn: {path}:{i}: {e}", file=sys.stderr)


def extract_text_blocks(content) -> list[str]:
    if isinstance(content, str):
        return [content] if content.strip() else []
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        bt = block.get("type")
        if bt == "text":
            text = block.get("text", "")
            if text.strip():
                out.append(text)
        elif bt == "image":
            out.append("_[image attached]_")
    return out


def render_transcript(path: Path, include_sidechains: bool = False) -> str:
    turns: list[tuple[str, str | None, str]] = []
    first_ts: str | None = None
    last_ts: str | None = None
    cwd: str | None = None
    git_branch: str | None = None

    for entry in iter_jsonl(path):
        etype = entry.get("type")
        if etype not in ("user", "assistant"):
            continue
        if entry.get("isSidechain") and not include_sidechains:
            continue
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        texts = extract_text_blocks(msg.get("content"))
        if not texts:
            continue
        ts = entry.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
        cwd = cwd or entry.get("cwd")
        git_branch = git_branch or entry.get("gitBranch")
        turns.append((etype, ts, "\n\n".join(texts)))

    lines: list[str] = []
    lines.append(f"# Session {path.stem}")
    lines.append("")
    if cwd:
        lines.append(f"- cwd: `{cwd}`")
    if git_branch:
        lines.append(f"- branch: `{git_branch}`")
    if first_ts:
        lines.append(f"- started: {first_ts}")
    if last_ts and last_ts != first_ts:
        lines.append(f"- ended: {last_ts}")
    lines.append(f"- turns: {len(turns)}")
    lines.append("")

    for role, ts, text in turns:
        heading = "User" if role == "user" else "Assistant"
        if ts:
            lines.append(f"## {heading} · {ts}")
        else:
            lines.append(f"## {heading}")
        lines.append("")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def find_session(query: str) -> Path | None:
    p = Path(query)
    if p.exists() and p.suffix == ".jsonl":
        return p
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        candidate = proj_dir / f"{query}.jsonl"
        if candidate.exists():
            return candidate
    return None


def dump_all(force: bool = False, include_sidechains: bool = False) -> None:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for proj_dir in sorted(PROJECTS_DIR.iterdir()):
        if not proj_dir.is_dir():
            continue
        out_dir = TRANSCRIPTS_DIR / proj_dir.name
        for jsonl in proj_dir.glob("*.jsonl"):
            out_path = out_dir / f"{jsonl.stem}.md"
            if (
                not force
                and out_path.exists()
                and out_path.stat().st_mtime >= jsonl.stat().st_mtime
            ):
                skipped += 1
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(render_transcript(jsonl, include_sidechains=include_sidechains))
            written += 1
    print(f"wrote {written}, skipped {skipped}", file=sys.stderr)


def list_sessions() -> None:
    rows: list[tuple[str, str, str, str, int]] = []
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        for jsonl in proj_dir.glob("*.jsonl"):
            first_user: str | None = None
            for entry in iter_jsonl(jsonl):
                if entry.get("type") == "user" and not entry.get("isSidechain"):
                    msg = entry.get("message")
                    if isinstance(msg, dict):
                        texts = extract_text_blocks(msg.get("content"))
                        if texts:
                            first_user = texts[0][:80].replace("\n", " ")
                            break
            mtime = datetime.fromtimestamp(jsonl.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size_kb = jsonl.stat().st_size // 1024
            rows.append((mtime, jsonl.stem[:8], proj_dir.name, first_user or "(no user text)", size_kb))
    rows.sort(reverse=True)
    for mtime, sid, proj, first, size_kb in rows:
        print(f"{mtime}  {sid}  {size_kb:>6}K  {proj[:40]:40s}  {first}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("session", nargs="?", help="Session UUID or path to .jsonl file")
    g.add_argument("--dump", action="store_true", help="Mirror all sessions to ~/.claude/transcripts/")
    g.add_argument("--list", action="store_true", help="List all sessions with first user message")
    ap.add_argument("--force", action="store_true", help="Re-dump even if up to date (with --dump)")
    ap.add_argument("--include-sidechains", action="store_true", help="Include subagent (sidechain) turns")
    args = ap.parse_args()

    if args.list:
        list_sessions()
        return 0
    if args.dump:
        dump_all(force=args.force, include_sidechains=args.include_sidechains)
        return 0
    if not args.session:
        ap.print_help()
        return 1

    path = find_session(args.session)
    if not path:
        print(f"session not found: {args.session}", file=sys.stderr)
        return 1
    print(render_transcript(path, include_sidechains=args.include_sidechains))
    return 0


if __name__ == "__main__":
    sys.exit(main())
