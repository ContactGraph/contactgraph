import logging
from typing import cast

import httpx

from contactsafe_server.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings: Settings = settings or get_settings()

    async def embed_text(self, text: str) -> list[float] | None:
        if not self._settings.openai_api_key or not text.strip():
            return None
        payload: dict[str, object] = {
            "model": self._settings.openai_embedding_model,
            "input": text.strip(),
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                response = await http.post(
                    f"{self._settings.openai_base_url.rstrip('/')}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self._settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data: dict[str, object] = cast(dict[str, object], response.json())
        except Exception:
            logger.exception("Embedding request failed")
            return None

        data_list: object = data.get("data")
        if not isinstance(data_list, list) or not data_list:
            return None
        first: object = data_list[0]
        if not isinstance(first, dict):
            return None
        embedding_raw: object = first.get("embedding")
        if not isinstance(embedding_raw, list):
            return None
        return [float(x) for x in embedding_raw]
