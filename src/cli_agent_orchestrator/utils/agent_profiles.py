"""Agent profile utilities."""

from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional

import frontmatter

from cli_agent_orchestrator.constants import LOCAL_AGENT_STORE_DIR
from cli_agent_orchestrator.models.agent_profile import AgentProfile


def load_agent_profile(agent_name: str) -> AgentProfile:
    """Load agent profile from local or built-in agent store."""
    try:
        # Check local store first
        local_profile = LOCAL_AGENT_STORE_DIR / f"{agent_name}.md"
        if local_profile.exists():
            profile_data = frontmatter.loads(local_profile.read_text())
            profile_data.metadata["system_prompt"] = profile_data.content.strip()
            return AgentProfile(**profile_data.metadata)

        # Fall back to built-in store
        agent_store = resources.files("cli_agent_orchestrator.agent_store")
        profile_file = agent_store / f"{agent_name}.md"

        if not profile_file.is_file():
            raise FileNotFoundError(f"Agent profile not found: {agent_name}")

        # Parse frontmatter
        profile_data = frontmatter.loads(profile_file.read_text())

        # Add system_prompt from markdown content
        profile_data.metadata["system_prompt"] = profile_data.content.strip()

        # Let Pydantic handle the nested object parsing including mcpServers
        return AgentProfile(**profile_data.metadata)

    except Exception as e:
        raise RuntimeError(f"Failed to load agent profile '{agent_name}': {e}")


def _read_profile_metadata_from_text(text: str) -> Dict[str, Any]:
    profile_data = frontmatter.loads(text)
    metadata: Dict[str, Any] = dict(profile_data.metadata)
    # The markdown content becomes the system prompt in CAO's profile format.
    metadata["system_prompt"] = (profile_data.content or "").strip()
    return metadata


def _read_profile_metadata_from_file(path: Path) -> Dict[str, Any]:
    return _read_profile_metadata_from_text(path.read_text())


def list_agent_profiles() -> List[Dict[str, Any]]:
    """List available agent profiles from local + built-in stores.

    Returns a stable, name-sorted list. Local profiles override built-ins with the same name.
    """
    profiles_by_name: Dict[str, Dict[str, Any]] = {}

    # Built-in profiles
    agent_store = resources.files("cli_agent_orchestrator.agent_store")
    for entry in agent_store.iterdir():
        if not entry.is_file() or entry.name.startswith(".") or entry.suffix != ".md":
            continue
        metadata = _read_profile_metadata_from_text(entry.read_text())
        name = str(metadata.get("name") or entry.stem)
        profiles_by_name[name] = {
            "name": name,
            "description": metadata.get("description"),
            "model": metadata.get("model"),
            "provider": metadata.get("provider"),
            "role": metadata.get("role"),
            "tags": metadata.get("tags"),
            "reasoning_effort": metadata.get("reasoning_effort"),
            "source": "builtin",
        }

    # Local profiles (override built-in)
    if LOCAL_AGENT_STORE_DIR.exists():
        for path in sorted(LOCAL_AGENT_STORE_DIR.glob("*.md")):
            try:
                metadata = _read_profile_metadata_from_file(path)
            except Exception:
                # Skip malformed profiles; callers can use get_agent_profile to see errors.
                continue
            name = str(metadata.get("name") or path.stem)
            profiles_by_name[name] = {
                "name": name,
                "description": metadata.get("description"),
                "model": metadata.get("model"),
                "provider": metadata.get("provider"),
                "role": metadata.get("role"),
                "tags": metadata.get("tags"),
                "reasoning_effort": metadata.get("reasoning_effort"),
                "source": "local",
            }

    return [profiles_by_name[name] for name in sorted(profiles_by_name.keys())]


def get_agent_profile(agent_name: str, *, include_prompt: bool = False) -> Dict[str, Any]:
    """Get an agent profile by name.

    Args:
        agent_name: Profile name (stem of the `*.md` file)
        include_prompt: If true, include the profile's `system_prompt` content.
    """
    profile = load_agent_profile(agent_name)
    data: Dict[str, Any] = profile.model_dump(exclude_none=True, mode="json")
    if not include_prompt:
        data.pop("system_prompt", None)

    local_path = LOCAL_AGENT_STORE_DIR / f"{agent_name}.md"
    data["source"] = "local" if local_path.exists() else "builtin"
    return data
