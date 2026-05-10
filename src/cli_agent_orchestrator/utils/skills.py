"""Skill loading and validation utilities."""

import logging
import shutil
from hashlib import sha256
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import frontmatter
from pydantic import ValidationError

from cli_agent_orchestrator.constants import SKILLS_DIR
from cli_agent_orchestrator.models.skill import SkillMetadata

logger = logging.getLogger(__name__)

SKILL_CATALOG_INSTRUCTION = (
    "The following skills are CAO-neutral source artifacts. Runtime providers may "
    "materialize profile-selected skills into their native skill storage."
)


class SkillNameError(ValueError):
    """Raised when a skill name is empty or unsafe to resolve on disk."""


def validate_skill_name(skill_name: str) -> str:
    """Reject skill names that could cause path traversal."""
    normalized_name = skill_name.strip()
    if not normalized_name:
        raise SkillNameError("Skill name must not be empty")
    if "/" in normalized_name or "\\" in normalized_name or ".." in normalized_name:
        raise SkillNameError(
            f"Invalid skill name '{skill_name}': must not contain '/', '\\', or '..'"
        )
    return normalized_name


def _parse_skill_file(skill_file: Any) -> Tuple[SkillMetadata, str]:
    """Parse a skill file and return validated metadata plus Markdown content."""
    try:
        parsed_skill = frontmatter.loads(skill_file.read_text())
    except Exception as exc:
        raise ValueError(f"Failed to parse skill file '{skill_file}': {exc}") from exc

    try:
        metadata = SkillMetadata(**parsed_skill.metadata)
    except ValidationError as exc:
        raise ValueError(f"Invalid skill metadata in '{skill_file}': {exc}") from exc

    return metadata, parsed_skill.content.strip()


def _packaged_skill_root(skill_name: str) -> Any | None:
    try:
        candidate = resources.files("cli_agent_orchestrator.skills") / skill_name
    except (FileNotFoundError, ModuleNotFoundError):
        return None
    return candidate if candidate.is_dir() else None


def resolve_skill_root(name: str) -> Any:
    """Resolve a CAO-neutral skill folder from local store or packaged built-ins."""
    skill_name = validate_skill_name(name)
    local = SKILLS_DIR / skill_name
    if local.is_dir():
        return local
    packaged = _packaged_skill_root(skill_name)
    if packaged is not None:
        return packaged
    raise FileNotFoundError(f"Skill folder does not exist: {local}")


def _load_skill_folder(skill_path: Any) -> Tuple[SkillMetadata, str]:
    """Load and validate a skill folder from the filesystem."""
    if isinstance(skill_path, Path):
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill folder does not exist: {skill_path}")
        if not skill_path.is_dir():
            raise ValueError(f"Skill path is not a directory: {skill_path}")
    if not skill_path.is_dir():
        raise FileNotFoundError(f"Skill folder does not exist: {skill_path}")

    skill_file = skill_path / "SKILL.md"
    if not skill_file.is_file():
        raise FileNotFoundError(f"Missing SKILL.md in skill folder: {skill_path}")

    metadata, content = _parse_skill_file(skill_file)
    if skill_path.name != metadata.name:
        raise ValueError(
            f"Skill folder name '{skill_path.name}' does not match skill name '{metadata.name}'"
        )

    return metadata, content


def load_skill_metadata(name: str) -> SkillMetadata:
    """Load validated metadata for a single installed skill."""
    metadata, _ = _load_skill_folder(resolve_skill_root(name))
    return metadata


def load_skill_content(name: str) -> str:
    """Load the Markdown body content for a single installed skill."""
    _, content = _load_skill_folder(resolve_skill_root(name))
    return content


def iter_skill_files(name: str) -> Iterable[tuple[str, bytes]]:
    """Yield relative file paths and bytes for one resolved CAO-neutral skill."""

    def walk(source: Any, prefix: str = "") -> Iterable[tuple[str, bytes]]:
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            relative = f"{prefix}{child.name}"
            if child.is_dir():
                yield from walk(child, f"{relative}/")
                continue
            if child.is_file():
                yield relative, child.read_bytes()

    yield from walk(resolve_skill_root(name))


def skill_file_fingerprints(name: str) -> Dict[str, str]:
    """Return stable content fingerprints for all files in one CAO-neutral skill."""
    files = {
        relative_path: sha256(contents).hexdigest()
        for relative_path, contents in iter_skill_files(name)
    }
    if "SKILL.md" not in files:
        raise FileNotFoundError(f"Skill '{validate_skill_name(name)}' is missing SKILL.md")
    return files


def materialize_skill(name: str, destination: Path) -> None:
    """Copy one CAO-neutral skill folder to a provider-owned destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for relative_path, contents in iter_skill_files(name):
        output_path = destination / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(contents)


def list_skills() -> List[SkillMetadata]:
    """Return all valid skills from the local skill store sorted by name."""
    if not SKILLS_DIR.exists():
        return []

    skills: List[SkillMetadata] = []
    for item in SKILLS_DIR.iterdir():
        if not item.is_dir():
            continue

        try:
            skills.append(load_skill_metadata(item.name))
        except Exception as exc:
            logger.warning("Skipping invalid skill folder '%s': %s", item, exc)

    return sorted(skills, key=lambda skill: skill.name)


def build_skill_catalog() -> str:
    """Build the injected skill catalog block for all installed skills."""
    skills = list_skills()
    if not skills:
        return ""

    skill_lines = [f"- **{skill.name}**: {skill.description}" for skill in skills]

    return "\n".join(
        [
            "## Available Skills",
            "",
            SKILL_CATALOG_INSTRUCTION,
            "",
            *skill_lines,
        ]
    )


def validate_skill_folder(path: Path) -> SkillMetadata:
    """Validate a skill folder at an arbitrary filesystem path."""
    metadata, _ = _load_skill_folder(path)
    return metadata
