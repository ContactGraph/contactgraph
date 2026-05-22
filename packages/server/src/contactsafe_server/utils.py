import json
import uuid
from typing import cast


def parse_session_id(raw: str) -> uuid.UUID:
    """Accept a bare UUID or JSON like {"session_id": "..."} from MCP clients."""
    value: str = raw.strip()
    if value.startswith("{"):
        parsed: object = json.loads(value)
        if isinstance(parsed, dict):
            payload: dict[str, object] = cast(dict[str, object], parsed)
            nested_raw: object | None = payload.get("session_id")
            if nested_raw is not None:
                value = str(nested_raw).strip()
    return uuid.UUID(value)
