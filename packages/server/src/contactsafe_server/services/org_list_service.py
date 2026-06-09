"""Service for user-scoped organization lists."""

from __future__ import annotations

import uuid

from contactsafe_core.contact_schemas import (
    CreateOrgListResult,
    DeleteOrgListResult,
    ListOrgListsResult,
    ModifyOrgListMembershipResult,
    OrgListSummary,
    RenameOrgListResult,
)
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Org, OrgList, OrgListMembership


class OrgListService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def list_org_lists(self, user_id: uuid.UUID) -> ListOrgListsResult:
        result = await self._db.execute(
            select(OrgList)
            .where(OrgList.user_id == user_id)
            .order_by(OrgList.name.asc()),
        )
        lists: list[OrgList] = list(result.scalars().all())
        summaries: list[OrgListSummary] = []
        for org_list in lists:
            membership_result = await self._db.execute(
                select(OrgListMembership.org_id).where(
                    OrgListMembership.org_list_id == org_list.id,
                ),
            )
            org_ids: list[uuid.UUID] = list(membership_result.scalars().all())
            summaries.append(
                OrgListSummary(
                    list_id=org_list.id,
                    name=org_list.name,
                    org_count=len(org_ids),
                    org_ids=org_ids,
                ),
            )
        count: int = len(summaries)
        message: str = (
            f"{count} organization list(s)."
            if count > 0
            else "No organization lists yet."
        )
        return ListOrgListsResult(lists=summaries, message=message)

    async def create_org_list(
        self,
        user_id: uuid.UUID,
        *,
        name: str,
    ) -> CreateOrgListResult:
        normalized: str = name.strip()
        if not normalized:
            raise ValueError("List name is required.")
        existing = await self._db.execute(
            select(OrgList.id).where(
                OrgList.user_id == user_id,
                func.lower(OrgList.name) == normalized.lower(),
            ),
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"A list named \"{normalized}\" already exists.")
        org_list = OrgList(user_id=user_id, name=normalized)
        self._db.add(org_list)
        await self._db.flush()
        return CreateOrgListResult(
            list_id=org_list.id,
            name=org_list.name,
            message=f"Created list \"{org_list.name}\".",
        )

    async def rename_org_list(
        self,
        user_id: uuid.UUID,
        *,
        list_id: uuid.UUID,
        name: str,
    ) -> RenameOrgListResult:
        normalized: str = name.strip()
        if not normalized:
            raise ValueError("List name is required.")
        org_list: OrgList | None = await self._get_owned_list(user_id, list_id)
        if org_list is None:
            raise ValueError("Organization list not found.")
        duplicate = await self._db.execute(
            select(OrgList.id).where(
                OrgList.user_id == user_id,
                func.lower(OrgList.name) == normalized.lower(),
                OrgList.id != list_id,
            ),
        )
        if duplicate.scalar_one_or_none() is not None:
            raise ValueError(f"A list named \"{normalized}\" already exists.")
        org_list.name = normalized
        await self._db.flush()
        return RenameOrgListResult(
            list_id=org_list.id,
            name=org_list.name,
            message=f"Renamed list to \"{org_list.name}\".",
        )

    async def delete_org_list(
        self,
        user_id: uuid.UUID,
        *,
        list_id: uuid.UUID,
    ) -> DeleteOrgListResult:
        org_list: OrgList | None = await self._get_owned_list(user_id, list_id)
        if org_list is None:
            raise ValueError("Organization list not found.")
        list_name: str = org_list.name
        await self._db.delete(org_list)
        await self._db.flush()
        return DeleteOrgListResult(
            deleted=True,
            message=f"Deleted list \"{list_name}\".",
        )

    async def add_orgs_to_list(
        self,
        user_id: uuid.UUID,
        *,
        list_id: uuid.UUID,
        org_ids: list[uuid.UUID],
    ) -> ModifyOrgListMembershipResult:
        org_list: OrgList | None = await self._get_owned_list(user_id, list_id)
        if org_list is None:
            raise ValueError("Organization list not found.")
        unique_org_ids: list[uuid.UUID] = list(dict.fromkeys(org_ids))
        if not unique_org_ids:
            return ModifyOrgListMembershipResult(
                list_id=list_id,
                affected_count=0,
                message="No organizations selected.",
            )
        valid_org_ids: list[uuid.UUID] = await self._filter_existing_org_ids(unique_org_ids)
        if not valid_org_ids:
            return ModifyOrgListMembershipResult(
                list_id=list_id,
                affected_count=0,
                message="No valid organizations to add.",
            )
        existing_result = await self._db.execute(
            select(OrgListMembership.org_id).where(
                OrgListMembership.org_list_id == list_id,
                OrgListMembership.org_id.in_(valid_org_ids),
            ),
        )
        existing_ids: set[uuid.UUID] = set(existing_result.scalars().all())
        new_org_ids: list[uuid.UUID] = [
            org_id for org_id in valid_org_ids if org_id not in existing_ids
        ]
        if new_org_ids:
            rows: list[dict[str, uuid.UUID]] = [
                {"org_list_id": list_id, "org_id": org_id}
                for org_id in new_org_ids
            ]
            await self._db.execute(insert(OrgListMembership).values(rows))
            await self._db.flush()
        return ModifyOrgListMembershipResult(
            list_id=list_id,
            affected_count=len(new_org_ids),
            message=(
                f"Added {len(new_org_ids)} organization(s) to \"{org_list.name}\"."
                if new_org_ids
                else f"All selected organizations are already in \"{org_list.name}\"."
            ),
        )

    async def remove_orgs_from_list(
        self,
        user_id: uuid.UUID,
        *,
        list_id: uuid.UUID,
        org_ids: list[uuid.UUID],
    ) -> ModifyOrgListMembershipResult:
        org_list: OrgList | None = await self._get_owned_list(user_id, list_id)
        if org_list is None:
            raise ValueError("Organization list not found.")
        unique_org_ids: list[uuid.UUID] = list(dict.fromkeys(org_ids))
        if not unique_org_ids:
            return ModifyOrgListMembershipResult(
                list_id=list_id,
                affected_count=0,
                message="No organizations selected.",
            )
        result = await self._db.execute(
            delete(OrgListMembership).where(
                OrgListMembership.org_list_id == list_id,
                OrgListMembership.org_id.in_(unique_org_ids),
            ),
        )
        affected_count: int = result.rowcount if result.rowcount is not None else 0
        return ModifyOrgListMembershipResult(
            list_id=list_id,
            affected_count=affected_count,
            message=f"Removed {affected_count} organization(s) from \"{org_list.name}\".",
        )

    async def _get_owned_list(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
    ) -> OrgList | None:
        result = await self._db.execute(
            select(OrgList).where(
                OrgList.id == list_id,
                OrgList.user_id == user_id,
            ),
        )
        return result.scalar_one_or_none()

    async def _filter_existing_org_ids(
        self,
        org_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        result = await self._db.execute(
            select(Org.id).where(Org.id.in_(org_ids)),
        )
        return list(result.scalars().all())
