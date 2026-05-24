import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from contactsafe_server.config import Settings
from contactsafe_server.db.models import InteractionExcerpt, Person, PersonEdge
from contactsafe_server.services.embedding_service import EmbeddingService


class InteractionExcerptService:
    """Seed lightweight excerpts for semantic search (expanded in later ingest phases)."""

    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._embedder: EmbeddingService = EmbeddingService(settings)

    async def seed_excerpts_for_user(self, user_id: uuid.UUID) -> None:
        if not self._settings.openai_api_key:
            return

        await self._db.execute(
            delete(InteractionExcerpt).where(InteractionExcerpt.user_id == user_id)
        )

        result = await self._db.execute(
            select(Person)
            .join(PersonEdge, PersonEdge.person_id == Person.id)
            .options(selectinload(Person.edge))
            .where(
                Person.user_id == user_id,
                PersonEdge.is_human.is_(True),
                PersonEdge.is_automated.is_(False),
            )
            .order_by(PersonEdge.tie_strength_score.desc())
            .limit(50)
        )
        people: list[Person] = list(result.scalars().unique().all())

        for person in people:
            parts: list[str] = [f"Contact: {person.canonical_name}"]
            if person.current_role:
                parts.append(f"Role: {person.current_role}")
            if person.current_org_name:
                parts.append(f"Organization: {person.current_org_name}")
            if person.inferred_categories:
                parts.append(f"Categories: {', '.join(person.inferred_categories)}")
            excerpt_text: str = ". ".join(parts)
            embedding: list[float] | None = await self._embedder.embed_text(excerpt_text)
            self._db.add(
                InteractionExcerpt(
                    user_id=user_id,
                    person_id=person.id,
                    excerpt_text=excerpt_text,
                    embedding=embedding,
                    occurred_at=person.last_seen_in_email,
                )
            )
        await self._db.flush()
