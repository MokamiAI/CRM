import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import ALL_TENANTS
from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def email_taken(self, email: str) -> bool:
        """Emails sign in to exactly one company, so this checks them all."""
        query = select(User.id).where(func.lower(User.email) == email.lower()).limit(1)
        return (await self.db.execute(query, execution_options={ALL_TENANTS: True})).first() is not None

    async def get_by_email(self, email: str) -> User | None:
        # Ignoring case: phones often capitalise the first letter of an email.
        result = await self.db.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
        return result.scalar_one_or_none()

    async def list_all(self, offset: int = 0, limit: int = 50) -> list[User]:
        result = await self.db.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, user: User) -> User:
        self.db.add(user)
        await self.db.flush()
        return user

    async def save(self, user: User) -> User:
        await self.db.flush()
        return user
