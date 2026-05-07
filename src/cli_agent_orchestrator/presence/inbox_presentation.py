"""Provider-authored presentation metadata for slim inbox reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

INBOX_PRESENTATION_METADATA_KEY = "_cao_inbox_presentation"


@dataclass(frozen=True)
class InboxReadPresentation:
    """Opaque provider-authored hints CAO may include when an inbox message is opened."""

    workspace: Optional[Mapping[str, Any]] = None
    source_label: Optional[str] = None


def inbox_presentation_metadata(
    *,
    workspace: Optional[Mapping[str, Any]] = None,
    source_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the metadata fragment providers attach to persisted messages."""

    presentation: Dict[str, Any] = {}
    if workspace is not None:
        presentation["workspace"] = dict(workspace)
    if source_label:
        presentation["source_label"] = str(source_label)
    return {INBOX_PRESENTATION_METADATA_KEY: presentation} if presentation else {}
