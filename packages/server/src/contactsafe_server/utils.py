import json
import uuid
from typing import cast


def _parse_uuid_from_json(raw: str, *keys: str) -> uuid.UUID:
    value: str = raw.strip()
    if value.startswith("{"):
        parsed: object = json.loads(value)
        if isinstance(parsed, dict):
            payload: dict[str, object] = cast(dict[str, object], parsed)
            for key in keys:
                nested_raw: object | None = payload.get(key)
                if nested_raw is not None:
                    value = str(nested_raw).strip()
                    break
    return uuid.UUID(value)


def parse_connect_session_id(raw: str) -> uuid.UUID:
    """Accept a bare UUID or JSON with connect_session_id (or legacy session_id key)."""
    return _parse_uuid_from_json(raw, "connect_session_id", "session_id")


def parse_source_id(raw: str) -> uuid.UUID:
    """Accept a bare UUID or JSON with source_id."""
    return _parse_uuid_from_json(raw, "source_id")
