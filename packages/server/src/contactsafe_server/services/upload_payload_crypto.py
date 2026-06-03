"""Encrypt uploaded file payloads at rest in Source.upload_payload JSONB."""

from __future__ import annotations

import base64
from contactsafe_server.services.crypto import TokenEncryptor

_PLAINTEXT_CONTENT_KEY: str = "content"
_ENCRYPTED_CONTENT_KEY: str = "content_encrypted"
_FILENAME_KEY: str = "filename"


def build_upload_payload(
    *,
    filename: str,
    content: str,
    encryptor: TokenEncryptor,
) -> dict[str, object]:
    ciphertext: bytes = encryptor.encrypt(content)
    encoded: str = base64.urlsafe_b64encode(ciphertext).decode("ascii")
    return {
        _FILENAME_KEY: filename,
        _ENCRYPTED_CONTENT_KEY: encoded,
    }


def read_upload_payload(
    payload: dict[str, object] | None,
    encryptor: TokenEncryptor,
) -> tuple[str, str]:
    if payload is None:
        raise ValueError("No upload payload stored for this source")

    filename: str = str(payload.get(_FILENAME_KEY, "upload.csv"))
    encrypted: object | None = payload.get(_ENCRYPTED_CONTENT_KEY)
    if isinstance(encrypted, str) and encrypted:
        raw: bytes = base64.urlsafe_b64decode(encrypted.encode("ascii"))
        content: str = encryptor.decrypt(raw)
        return filename, content

    legacy_content: object | None = payload.get(_PLAINTEXT_CONTENT_KEY)
    if isinstance(legacy_content, str) and legacy_content.strip():
        return filename, legacy_content

    raise ValueError("Upload payload is empty")
