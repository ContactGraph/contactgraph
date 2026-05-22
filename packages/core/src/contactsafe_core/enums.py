from enum import StrEnum


class SessionStatus(StrEnum):
    PENDING = "pending"
    CONNECTED = "connected"
    FAILED = "failed"


class OAuthProvider(StrEnum):
    GOOGLE = "google"


class SourceType(StrEnum):
    GOOGLE_MAIL = "google_mail"
    GOOGLE_CALENDAR = "google_calendar"
    LINKEDIN_CONNECTIONS_UPLOAD = "linkedin_connections_upload"
    PHONE_CONTACTS_UPLOAD = "phone_contacts_upload"


class SourceConnectionStatus(StrEnum):
    PENDING_OAUTH = "pending_oauth"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class SyncState(StrEnum):
    PENDING = "pending"
    SYNCING = "syncing"
    PARTIAL = "partial"
    COMPLETE = "complete"
    FAILED = "failed"
