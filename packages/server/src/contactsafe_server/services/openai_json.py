import json
from typing import cast


def content_from_chat_completion(data: dict[str, object]) -> str:
    choices_raw: object = data.get("choices")
    if not isinstance(choices_raw, list) or not choices_raw:
        raise ValueError("OpenAI response missing choices")
    first_raw: object = choices_raw[0]
    if not isinstance(first_raw, dict):
        raise ValueError("Invalid choice shape")
    first: dict[str, object] = cast(dict[str, object], first_raw)
    message_raw: object = first.get("message")
    if not isinstance(message_raw, dict):
        raise ValueError("Invalid message shape")
    message: dict[str, object] = cast(dict[str, object], message_raw)
    content_raw: object = message.get("content")
    if not isinstance(content_raw, str):
        raise ValueError("Invalid content shape")
    return content_raw


def parse_json_object(content: str) -> dict[str, object]:
    parsed: object = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object")
    return cast(dict[str, object], parsed)
