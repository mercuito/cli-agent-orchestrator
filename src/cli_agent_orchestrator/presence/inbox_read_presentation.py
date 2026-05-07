"""Provider-authored presentation metadata for slim inbox reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

INBOX_READ_PRESENTATION_METADATA_KEY = "_cao_inbox_read_presentation"


@dataclass(frozen=True)
class InboxMessageReadPresentation:
    """Opaque provider-authored hints CAO may include when an inbox message is opened."""

    workspace: Optional[Mapping[str, Any]] = None
    source_label: Optional[str] = None
    context: Optional[Mapping[str, Any]] = None


def inbox_read_presentation_metadata(
    *,
    workspace: Optional[Mapping[str, Any]] = None,
    source_label: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the metadata fragment providers attach to persisted messages."""

    presentation: Dict[str, Any] = {}
    if workspace is not None:
        presentation["workspace"] = dict(workspace)
    if source_label:
        presentation["source_label"] = str(source_label)
    if context is not None:
        presentation["context"] = dict(context)
    return {INBOX_READ_PRESENTATION_METADATA_KEY: presentation} if presentation else {}
