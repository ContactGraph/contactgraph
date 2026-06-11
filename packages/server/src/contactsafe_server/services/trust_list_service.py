"""Service for managing trust list memberships and invites."""

import secrets
import uuid
from datetime import UTC, datetime

from contactsafe_core.enums import (
    ContactPrivacyLabel,
    TrustListInviteStatus,
    TrustListMembershipStatus,
)
from contactsafe_core.schemas import (
    EditTrustedUsersResult,
    PendingInboundInvite,
    TrustListInviteSummary,
    TrustListMemberSummary,
    ViewTrustedUsersResult,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    ContactPrivacyLabelRow,
    TrustListInvite,
    TrustListMembership,
    User,
    UserIdentity,
)

MAX_TRUST_LIST_MEMBERS: int = 20


class TrustListService:
    def __init__(self, db: AsyncSession, base_url: str) -> None:
        self._db: AsyncSession = db
        self._base_url: str = base_url.rstrip("/")

    async def view(self, user_id: uuid.UUID) -> ViewTrustedUsersResult:
        members: list[TrustListMemberSummary] = await self._get_active_members(user_id)
        outbound: list[TrustListInviteSummary] = await self._get_outbound_invites(user_id)
        inbound: list[PendingInboundInvite] = await self._get_inbound_invites(user_id)
        system_messages: list[str] = await self.get_system_messages(user_id)

        count: int = len(members)
        message: str = (
            f"You have {count} trusted connection(s) (max {MAX_TRUST_LIST_MEMBERS})."
        )
        if inbound:
            message += f" You have {len(inbound)} pending invite(s) to review."

        return ViewTrustedUsersResult(
            members=members,
            outbound_invites=outbound,
            inbound_invites=inbound,
            max_members=MAX_TRUST_LIST_MEMBERS,
            message=message,
            system_messages=system_messages,
        )

    async def edit(
        self,
        user_id: uuid.UUID,
        *,
        add: list[str] | None = None,
        remove: list[str] | None = None,
        accept: list[str] | None = None,
        decline: list[str] | None = None,
        set_privacy: list[dict[str, str]] | None = None,
    ) -> EditTrustedUsersResult:
        added: list[str] = []
        removed: list[str] = []
        accepted: list[str] = []
        declined: list[str] = []
        privacy_updated: list[str] = []
        invite_copy: str | None = None
        messages: list[str] = []
        not_on_platform: list[str] = []

        referral_codes: list[str] = []
        already_on_platform: list[str] = []

        if add:
            current_count: int = await self._active_membership_count(user_id)
            for email in add:
                normalized: str = email.strip().lower()
                if current_count >= MAX_TRUST_LIST_MEMBERS:
                    messages.append(
                        f"Cannot add {normalized}: trust list is full "
                        f"({MAX_TRUST_LIST_MEMBERS} max). Remove someone first."
                    )
                    break

                target_user_id: uuid.UUID | None = await self._resolve_user_by_email(normalized)
                if target_user_id is not None and target_user_id != user_id:
                    existing = await self._get_membership(user_id, target_user_id)
                    if existing is not None:
                        messages.append(f"{normalized} is already in your trust list.")
                        continue
                    await self._create_invite(user_id, normalized)
                    added.append(normalized)
                    already_on_platform.append(normalized)
                    current_count += 1
                elif target_user_id == user_id:
                    messages.append("You cannot add yourself to your trust list.")
                else:
                    invite: TrustListInvite = await self._create_invite(user_id, normalized)
                    referral_codes.append(invite.referral_code)
                    not_on_platform.append(normalized)
                    added.append(normalized)

        if not_on_platform:
            invite_copy = self._generate_invite_copy_new_user(
                referral_codes[0] if referral_codes else None
            )
        elif already_on_platform:
            invite_copy = self._generate_invite_copy_existing_user()

        if remove:
            for target in remove:
                normalized = target.strip().lower()
                revoked: bool = await self._remove_member(user_id, normalized)
                if revoked:
                    removed.append(normalized)
                else:
                    messages.append(f"{normalized} not found in your trust list.")

        if accept:
            for invite_id_str in accept:
                invite_id: uuid.UUID = uuid.UUID(invite_id_str)
                result_email: str | None = await self._accept_invite(user_id, invite_id)
                if result_email:
                    accepted.append(result_email)
                else:
                    messages.append(f"Invite {invite_id_str} not found or already processed.")

        if decline:
            for invite_id_str in decline:
                invite_id = uuid.UUID(invite_id_str)
                result_email = await self._decline_invite(user_id, invite_id)
                if result_email:
                    declined.append(result_email)

        if set_privacy:
            for item in set_privacy:
                person_id: uuid.UUID = uuid.UUID(item["person_id"])
                label: str = item["label"]
                await self._set_privacy_label(user_id, person_id, label)
                privacy_updated.append(str(person_id))

        summary_parts: list[str] = []
        if added:
            summary_parts.append(f"Added: {', '.join(added)}")
        if removed:
            summary_parts.append(f"Removed: {', '.join(removed)}")
        if accepted:
            summary_parts.append(f"Accepted: {', '.join(accepted)}")
        if declined:
            summary_parts.append(f"Declined: {', '.join(declined)}")
        if privacy_updated:
            summary_parts.append(f"Privacy updated for {len(privacy_updated)} contact(s)")
        if messages:
            summary_parts.extend(messages)

        system_messages: list[str] = await self.get_system_messages(user_id)

        return EditTrustedUsersResult(
            added=added,
            removed=removed,
            accepted=accepted,
            declined=declined,
            privacy_updated=privacy_updated,
            invite_copy=invite_copy,
            message="; ".join(summary_parts) if summary_parts else "No changes made.",
            system_messages=system_messages,
        )

    async def get_trust_member_user_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Return user_ids of all active trust list members for a given user."""
        stmt = select(TrustListMembership).where(
            TrustListMembership.status == TrustListMembershipStatus.ACTIVE,
            or_(
                TrustListMembership.user_a_id == user_id,
                TrustListMembership.user_b_id == user_id,
            ),
        )
        result = await self._db.execute(stmt)
        memberships: list[TrustListMembership] = list(result.scalars().all())
        member_ids: list[uuid.UUID] = []
        for m in memberships:
            other: uuid.UUID = m.user_b_id if m.user_a_id == user_id else m.user_a_id
            member_ids.append(other)
        return member_ids

    async def get_private_person_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        """Return person_ids that this user has marked private."""
        stmt = select(ContactPrivacyLabelRow.person_id).where(
            ContactPrivacyLabelRow.user_id == user_id,
            ContactPrivacyLabelRow.label == ContactPrivacyLabel.PRIVATE,
        )
        result = await self._db.execute(stmt)
        return set(result.scalars().all())

    async def get_system_messages(self, user_id: uuid.UUID) -> list[str]:
        """Generate system messages for pending invites and recent activity."""
        messages: list[str] = []
        inbound: list[PendingInboundInvite] = await self._get_inbound_invites(user_id)
        for inv in inbound:
            name: str = inv.inviter_name or inv.inviter_email
            messages.append(
                f"You have a pending trust list invite from {name}. "
                f"Use edit_trusted_users(accept=[\"{inv.invite_id}\"]) to accept."
            )
        return messages

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_active_members(self, user_id: uuid.UUID) -> list[TrustListMemberSummary]:
        stmt = select(TrustListMembership).where(
            TrustListMembership.status == TrustListMembershipStatus.ACTIVE,
            or_(
                TrustListMembership.user_a_id == user_id,
                TrustListMembership.user_b_id == user_id,
            ),
        )
        result = await self._db.execute(stmt)
        memberships: list[TrustListMembership] = list(result.scalars().all())

        summaries: list[TrustListMemberSummary] = []
        for m in memberships:
            other_id: uuid.UUID = m.user_b_id if m.user_a_id == user_id else m.user_a_id
            other_user: User | None = await self._db.get(User, other_id)
            if other_user is None:
                continue
            summaries.append(TrustListMemberSummary(
                membership_id=m.id,
                user_id=other_id,
                email=other_user.email,
                name=other_user.google_profile_name,
                status=TrustListMembershipStatus(m.status),
                established_at=m.established_at,
            ))
        return summaries

    async def _get_outbound_invites(self, user_id: uuid.UUID) -> list[TrustListInviteSummary]:
        stmt = select(TrustListInvite).where(
            TrustListInvite.inviter_user_id == user_id,
            TrustListInvite.status == TrustListInviteStatus.PENDING,
        )
        result = await self._db.execute(stmt)
        invites: list[TrustListInvite] = list(result.scalars().all())
        return [
            TrustListInviteSummary(
                invite_id=inv.id,
                invitee_email=inv.invitee_email,
                status=TrustListInviteStatus(inv.status),
                created_at=inv.created_at,
            )
            for inv in invites
        ]

    async def _get_inbound_invites(self, user_id: uuid.UUID) -> list[PendingInboundInvite]:
        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return []

        emails_stmt = select(UserIdentity.value).where(
            UserIdentity.user_id == user_id,
            UserIdentity.kind == "email",
        )
        emails_result = await self._db.execute(emails_stmt)
        user_emails: list[str] = [user.email] + list(emails_result.scalars().all())
        user_emails = list(set(e.lower() for e in user_emails))

        stmt = select(TrustListInvite).where(
            TrustListInvite.invitee_email.in_(user_emails),
            TrustListInvite.status == TrustListInviteStatus.PENDING,
        )
        result = await self._db.execute(stmt)
        invites: list[TrustListInvite] = list(result.scalars().all())

        pending: list[PendingInboundInvite] = []
        for inv in invites:
            inviter: User | None = await self._db.get(User, inv.inviter_user_id)
            pending.append(PendingInboundInvite(
                invite_id=inv.id,
                inviter_email=inviter.email if inviter else "unknown",
                inviter_name=inviter.google_profile_name if inviter else None,
                created_at=inv.created_at,
            ))
        return pending

    async def _active_membership_count(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(TrustListMembership).where(
            TrustListMembership.status == TrustListMembershipStatus.ACTIVE,
            or_(
                TrustListMembership.user_a_id == user_id,
                TrustListMembership.user_b_id == user_id,
            ),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def _resolve_user_by_email(self, email: str) -> uuid.UUID | None:
        stmt = select(User.id).where(func.lower(User.email) == email.lower())
        result = await self._db.execute(stmt)
        user_id: uuid.UUID | None = result.scalar_one_or_none()
        if user_id:
            return user_id
        identity_stmt = select(UserIdentity.user_id).where(
            UserIdentity.kind == "email",
            func.lower(UserIdentity.value) == email.lower(),
        )
        identity_result = await self._db.execute(identity_stmt)
        return identity_result.scalar_one_or_none()

    async def _get_membership(
        self, user_id: uuid.UUID, other_id: uuid.UUID
    ) -> TrustListMembership | None:
        a_id, b_id = sorted([user_id, other_id])
        stmt = select(TrustListMembership).where(
            TrustListMembership.user_a_id == a_id,
            TrustListMembership.user_b_id == b_id,
            TrustListMembership.status == TrustListMembershipStatus.ACTIVE,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _create_invite(self, inviter_id: uuid.UUID, invitee_email: str) -> TrustListInvite:
        existing_stmt = select(TrustListInvite).where(
            TrustListInvite.inviter_user_id == inviter_id,
            TrustListInvite.invitee_email == invitee_email.lower(),
            TrustListInvite.status == TrustListInviteStatus.PENDING,
        )
        existing_result = await self._db.execute(existing_stmt)
        existing: TrustListInvite | None = existing_result.scalar_one_or_none()
        if existing:
            return existing

        invite = TrustListInvite(
            inviter_user_id=inviter_id,
            invitee_email=invitee_email.lower(),
            referral_code=secrets.token_urlsafe(16),
            status=TrustListInviteStatus.PENDING,
        )
        self._db.add(invite)
        await self._db.flush()
        return invite

    async def _accept_invite(self, user_id: uuid.UUID, invite_id: uuid.UUID) -> str | None:
        invite: TrustListInvite | None = await self._db.get(TrustListInvite, invite_id)
        if invite is None or invite.status != TrustListInviteStatus.PENDING:
            return None

        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return None
        user_emails: set[str] = {user.email.lower()}
        id_stmt = select(UserIdentity.value).where(
            UserIdentity.user_id == user_id, UserIdentity.kind == "email"
        )
        id_result = await self._db.execute(id_stmt)
        user_emails.update(e.lower() for e in id_result.scalars().all())

        if invite.invitee_email.lower() not in user_emails:
            return None

        invite.status = TrustListInviteStatus.ACCEPTED
        invite.accepted_at = datetime.now(UTC)

        a_id, b_id = sorted([invite.inviter_user_id, user_id])
        membership = TrustListMembership(
            user_a_id=a_id,
            user_b_id=b_id,
            status=TrustListMembershipStatus.ACTIVE,
        )
        self._db.add(membership)
        await self._db.flush()

        inviter: User | None = await self._db.get(User, invite.inviter_user_id)
        return inviter.email if inviter else invite.invitee_email

    async def _decline_invite(self, user_id: uuid.UUID, invite_id: uuid.UUID) -> str | None:
        invite: TrustListInvite | None = await self._db.get(TrustListInvite, invite_id)
        if invite is None or invite.status != TrustListInviteStatus.PENDING:
            return None

        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return None
        user_emails: set[str] = {user.email.lower()}
        id_stmt = select(UserIdentity.value).where(
            UserIdentity.user_id == user_id, UserIdentity.kind == "email"
        )
        id_result = await self._db.execute(id_stmt)
        user_emails.update(e.lower() for e in id_result.scalars().all())

        if invite.invitee_email.lower() not in user_emails:
            return None

        invite.status = TrustListInviteStatus.DECLINED
        await self._db.flush()
        inviter: User | None = await self._db.get(User, invite.inviter_user_id)
        return inviter.email if inviter else invite.invitee_email

    async def _remove_member(self, user_id: uuid.UUID, email: str) -> bool:
        target_id: uuid.UUID | None = await self._resolve_user_by_email(email)
        if target_id is None:
            return False
        membership: TrustListMembership | None = await self._get_membership(user_id, target_id)
        if membership is None:
            return False
        membership.status = TrustListMembershipStatus.REVOKED
        await self._db.flush()
        return True

    async def _set_privacy_label(
        self, user_id: uuid.UUID, person_id: uuid.UUID, label: str
    ) -> None:
        stmt = select(ContactPrivacyLabelRow).where(
            ContactPrivacyLabelRow.user_id == user_id,
            ContactPrivacyLabelRow.person_id == person_id,
        )
        result = await self._db.execute(stmt)
        existing: ContactPrivacyLabelRow | None = result.scalar_one_or_none()

        if label == ContactPrivacyLabel.STANDARD and existing is not None:
            await self._db.delete(existing)
        elif existing is not None:
            existing.label = label
        elif label != ContactPrivacyLabel.STANDARD:
            row = ContactPrivacyLabelRow(
                user_id=user_id,
                person_id=person_id,
                label=label,
            )
            self._db.add(row)
        await self._db.flush()

    def _generate_invite_copy_new_user(self, referral_code: str | None) -> str:
        """Invite copy for someone who doesn't have a ContactGraph account yet."""
        if referral_code:
            invite_url: str = f"{self._base_url}/join?ref={referral_code}"
        else:
            invite_url = f"{self._base_url}/join"
        return (
            f"I use ContactGraph to keep track of who I know professionally. "
            f"If you sign up, we can see each other's contacts (names and roles "
            f"only — no emails shared without asking).\n\n"
            f"Join here: {invite_url}"
        )

    def _generate_invite_copy_existing_user(self) -> str:
        """Invite copy for someone who already has a ContactGraph account."""
        sharing_url: str = f"{self._base_url}/sharing"
        return (
            f"I just invited you to share networks on ContactGraph! "
            f"You should have a pending invite waiting for you.\n\n"
            f"Accept it here: {sharing_url}"
        )
