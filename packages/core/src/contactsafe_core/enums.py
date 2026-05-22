from enum import StrEnum


class SessionStatus(StrEnum):
    PENDING = "pending"
    CONNECTED = "connected"
    FAILED = "failed"


class OAuthProvider(StrEnum):
    GOOGLE = "google"


class ImportState(StrEnum):
    """Import pipeline states (Phase 2+). Phase 1 maps CONNECTED only."""

    PENDING = "pending"
    IMPORTING = "importing"
    PARTIAL = "partial"
    COMPLETE = "complete"
