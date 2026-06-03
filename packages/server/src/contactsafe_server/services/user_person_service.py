"""Link a User to their own Person record in the graph."""

from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Person, User
from contactsafe_server.services.entity_resolution import EntityResolver


async def ensure_user_person(db: AsyncSession, user: User) -> Person:
    """Return the user's Person, creating one if necessary."""
    if user.person_id is not None:
        person: Person | None = await db.get(Person, user.person_id)
        if person is not None:
            return person

    display_name: str = user.display_name or user.google_profile_name or user.email
    resolver = EntityResolver(db)
    person = await resolver.resolve_person(
        emails=[user.email],
        display_name=display_name,
    )

    user.person_id = person.id
    await db.flush()
    return person
