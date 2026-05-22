import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Org


class OrgService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def resolve_org(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        org_name_hint: str | None,
    ) -> Org | None:
        _local, domain = email.rsplit("@", 1)
        domain_lower: str = domain.lower()
        canonical: str = (org_name_hint or domain_lower.split(".")[0]).strip()
        if len(canonical) < 2:
            return None

        result = await self._db.execute(
            select(Org).where(Org.user_id == user_id, Org.domain == domain_lower)
        )
        existing: Org | None = result.scalar_one_or_none()
        if existing is not None:
            return existing

        org = Org(
            user_id=user_id,
            canonical_name=canonical.title() if org_name_hint is None else org_name_hint,
            domain=domain_lower,
            aliases=[canonical.lower()],
        )
        self._db.add(org)
        await self._db.flush()
        return org
