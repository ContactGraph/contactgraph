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
    GOOGLE_CONTACTS = "google_contacts"
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


class IdentityKind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    GOOGLE_SUB = "google_sub"


class TrustListInviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class TrustListMembershipStatus(StrEnum):
    ACTIVE = "active"
    MUTED_BY_A = "muted_by_a"
    MUTED_BY_B = "muted_by_b"
    REVOKED = "revoked"


class ContactPrivacyLabel(StrEnum):
    STANDARD = "standard"
    PRIVATE = "private"
