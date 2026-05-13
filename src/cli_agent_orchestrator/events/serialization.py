"""Serialization registry for framework-wide typed CAO events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from importlib import import_module
from types import UnionType
from typing import Any, cast, get_args, get_origin, get_type_hints

from cli_agent_orchestrator.events import (
    AgentParticipant,
    CaoCausationId,
    CaoCorrelationId,
    CaoEvent,
    CaoEventId,
    CaoEventOccurredAt,
    CaoEventSourceId,
    CaoEventSourceRef,
    CaoEventSourceType,
    InvalidCaoEventError,
)


class CaoEventSerializerRegistry:
    """Registry that round-trips concrete CAO event dataclasses by type key."""

    def __init__(self) -> None:
        self._event_types_by_key: dict[str, type[CaoEvent]] = {}

    def register(self, event_types: tuple[type[CaoEvent], ...]) -> None:
        for event_type in event_types:
            if not is_dataclass(event_type):
                raise InvalidCaoEventError(
                    f"{event_type.__name__} must be a dataclass to be persisted"
                )
            type_key = event_type_key(event_type)
            existing = self._event_types_by_key.get(type_key)
            if existing is not None and existing is not event_type:
                raise InvalidCaoEventError(f"Duplicate CAO event type key: {type_key}")
            self._event_types_by_key[type_key] = event_type

    def serialize(self, event: CaoEvent) -> tuple[str, str]:
        event_type = type(event)
        self.register((event_type,))
        event_data = {
            field.name: _encode_value(getattr(event, field.name))
            for field in fields(cast(Any, event))
            if field.init
        }
        return event_type_key(event_type), _dumps(event_data)

    def deserialize(self, event_type_key_value: str, event_data_json: str) -> CaoEvent:
        event_type = self._event_types_by_key.get(event_type_key_value)
        if event_type is None:
            event_type = _import_event_type(event_type_key_value)
            self.register((event_type,))
        try:
            event_data = json.loads(event_data_json)
        except json.JSONDecodeError as exc:
            raise InvalidCaoEventError("Stored CAO event data is not valid JSON") from exc
        if not isinstance(event_data, Mapping):
            raise InvalidCaoEventError("Stored CAO event data must be a JSON object")

        type_hints = get_type_hints(event_type)
        kwargs = {}
        for field in fields(cast(Any, event_type)):
            if not field.init:
                continue
            if field.name not in event_data:
                raise InvalidCaoEventError(f"Stored CAO event data is missing field: {field.name}")
            kwargs[field.name] = _decode_value(event_data[field.name], type_hints[field.name])
        return event_type(**kwargs)


_DEFAULT_CAO_EVENT_SERIALIZER_REGISTRY = CaoEventSerializerRegistry()


def default_cao_event_serializer_registry() -> CaoEventSerializerRegistry:
    """Return CAO's process-local typed event serialization registry."""

    return _DEFAULT_CAO_EVENT_SERIALIZER_REGISTRY


def register_cao_event_serializers(event_types: tuple[type[CaoEvent], ...]) -> None:
    """Register concrete CAO event dataclasses for later reconstruction."""

    default_cao_event_serializer_registry().register(event_types)


def serialize_cao_event(event: CaoEvent) -> tuple[str, str]:
    """Serialize one typed event into its concrete type key and canonical JSON."""

    return default_cao_event_serializer_registry().serialize(event)


def deserialize_cao_event(event_type_key_value: str, event_data_json: str) -> CaoEvent:
    """Reconstruct one typed event from its registered type key and canonical JSON."""

    return default_cao_event_serializer_registry().deserialize(
        event_type_key_value,
        event_data_json,
    )


def event_type_key(event_type: type[CaoEvent]) -> str:
    """Return the stable discriminator for a concrete event class."""

    return f"{event_type.__module__}.{event_type.__qualname__}"


def _import_event_type(type_key: str) -> type[CaoEvent]:
    module_name, separator, qualified_name = type_key.rpartition(".")
    if not separator or not module_name or not qualified_name:
        raise InvalidCaoEventError(f"Unknown CAO event type key: {type_key}")
    try:
        value: object = import_module(module_name)
        for attribute in qualified_name.split("."):
            value = getattr(value, attribute)
    except (ImportError, AttributeError) as exc:
        raise InvalidCaoEventError(f"Unknown CAO event type key: {type_key}") from exc
    if not isinstance(value, type):
        raise InvalidCaoEventError(f"CAO event type key does not resolve to a class: {type_key}")
    return cast(type[CaoEvent], value)


def _dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _encode_value(value: object) -> object:
    if isinstance(value, CaoEventSourceRef):
        return {
            "source_type": str(value.source_type),
            "source_id": str(value.source_id),
        }
    if isinstance(value, AgentParticipant):
        return {
            "agent_identity_id": value.agent_identity_id,
            "role": value.role,
        }
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_encode_value(item) for item in value]
    if isinstance(value, list):
        return [_encode_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _encode_value(item) for key, item in value.items()}
    return value


def _decode_value(value: object, target_type: object) -> object:
    if value is None:
        return None
    if target_type is CaoEventSourceRef:
        if not isinstance(value, Mapping):
            raise InvalidCaoEventError("Stored source must be a JSON object")
        return CaoEventSourceRef(
            source_type=CaoEventSourceType(str(value["source_type"])),
            source_id=CaoEventSourceId(str(value["source_id"])),
        )
    if target_type is AgentParticipant:
        if not isinstance(value, Mapping):
            raise InvalidCaoEventError("Stored agent participant must be a JSON object")
        role = value.get("role")
        return AgentParticipant(
            agent_identity_id=str(value["agent_identity_id"]),
            role=str(role) if role is not None else None,
        )
    if target_type is CaoEventOccurredAt:
        if not isinstance(value, str):
            raise InvalidCaoEventError("Stored occurred_at must be a string")
        return CaoEventOccurredAt(datetime.fromisoformat(value))
    if target_type is CaoEventId:
        return CaoEventId(str(value))
    if target_type is CaoCorrelationId:
        return CaoCorrelationId(str(value))
    if target_type is CaoCausationId:
        return CaoCausationId(str(value))
    if target_type is CaoEventSourceType:
        return CaoEventSourceType(str(value))
    if target_type is CaoEventSourceId:
        return CaoEventSourceId(str(value))

    origin = get_origin(target_type)
    if origin is UnionType:
        non_none_args = [arg for arg in get_args(target_type) if arg is not type(None)]
        if len(non_none_args) == 1:
            return _decode_value(value, non_none_args[0])
    if origin is tuple:
        item_type = get_args(target_type)[0]
        if not isinstance(value, list):
            raise InvalidCaoEventError("Stored tuple field must be a JSON array")
        return tuple(_decode_value(item, item_type) for item in value)
    return value
