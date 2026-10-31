import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.invite_service import unusable_password
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.users = UserRepository(db)

    async def create_user(self, data: UserCreate) -> User:
        if await self.users.email_taken(data.email):
            raise ConflictError("A user with this email already exists", "USER_EMAIL_TAKEN")
        user = User(
            email=data.email.lower(),
            password_hash=hash_password(data.password) if data.password else unusable_password(),
            full_name=data.full_name,
            role=data.role,
            job_title=(data.job_title or "").strip() or None,
        )
        return await self.users.create(user)

    async def list_users(self, offset: int = 0, limit: int = 50) -> list[User]:
        return await self.users.list_all(offset=offset, limit=limit)

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found", "USER_NOT_FOUND")
        return user

    async def update_user(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get_user(user_id)
        if data.full_name is not None:
            user.full_name = data.full_name
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.job_title is not None:
            user.job_title = data.job_title.strip() or None
        return await self.users.save(user)
