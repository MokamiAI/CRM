import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.invite_service import unusable_password
from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import UserRole
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
        # The owner stays an active admin until they hand the account over.
        if user.is_account_owner and ((data.role is not None and data.role != UserRole.ADMIN) or data.is_active is False):
            raise ConflictError("Hand the account to another admin before changing the owner's role or switching them off", "OWNER_LOCKED")
        if data.full_name is not None:
            user.full_name = data.full_name
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.job_title is not None:
            user.job_title = data.job_title.strip() or None
        return await self.users.save(user)

    async def set_cost_access(self, user_id: uuid.UUID, access: str) -> User:
        user = await self.get_user(user_id)
        if user.is_account_owner:
            raise ConflictError("The account owner always sees and manages costs", "OWNER_ALWAYS_HAS_COSTS")
        if access == "manage" and user.role == UserRole.VIEWER:
            raise ConflictError("A viewer can be given view access only", "VIEWER_VIEW_ONLY")
        user.cost_access = access
        return await self.users.save(user)

    async def hand_over(self, owner: User, user_id: uuid.UUID) -> User:
        """Makes another active admin the account owner; the former owner
        keeps managing costs."""
        new_owner = await self.get_user(user_id)
        if new_owner.id == owner.id:
            return new_owner
        if new_owner.role != UserRole.ADMIN or not new_owner.is_active:
            raise ConflictError("Only an active admin can become the account owner", "OWNER_MUST_BE_ADMIN")
        owner.is_account_owner, owner.cost_access = False, "manage"
        await self.db.flush()  # one owner at a time (a unique index)
        new_owner.is_account_owner = True
        return await self.users.save(new_owner)
