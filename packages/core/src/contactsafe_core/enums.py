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
    LINKEDIN_PROFILE_UPLOAD = "linkedin_profile_upload"
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


class EnrichmentRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class EnrichmentQueueStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    DEFERRED = "deferred"


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


class JobDigestFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    OFF = "off"


class JobInterest(StrEnum):
    INTERESTED = "interested"
    DISMISSED = "dismissed"


class UserTaskKind(StrEnum):
    UPLOAD_PHONE = "upload_phone"
    UPLOAD_LINKEDIN = "upload_linkedin"
    UPLOAD_PROFILE = "upload_profile"
    SET_JOB_CRITERIA = "set_job_criteria"
    REVIEW_JOBS = "review_jobs"
    JOB_OUTREACH = "job_outreach"


class UserTaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    SKIPPED = "skipped"


class OutreachChannel(StrEnum):
    """How the user actually reached the person.

    Recording the channel is the point: which channel was used carries as much signal as
    whether a reply came back, and it is the one thing that is impossible to reconstruct
    later.
    """

    EMAIL = "email"
    TEXT_SMS = "text_sms"
    DM_INSTAGRAM = "dm_instagram"
    DM_LINKEDIN = "dm_linkedin"
    DM_X = "dm_x"
    DM_BLUESKY = "dm_bluesky"
    PHONE_CALL = "phone_call"
    IN_PERSON = "in_person"
    OTHER = "other"


class OutreachStatus(StrEnum):
    """Outcome of a single attempt.

    NO_RESPONSE is set deliberately by the user, never inferred from elapsed time — an
    unanswered message is not the same fact as one the user has decided went unanswered.
    """

    SENT = "sent"
    REPLIED = "replied"
    NO_RESPONSE = "no_response"
    MEETING_BOOKED = "meeting_booked"
    DECLINED = "declined"
    BOUNCED = "bounced"


class OutreachQueueFilter(StrEnum):
    """Which slice of the network to surface for outreach."""

    UNCONTACTED = "uncontacted"
    AWAITING_REPLY = "awaiting_reply"
    STALE = "stale"
    DUE = "due"
