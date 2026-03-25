"""User repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, User)

    async def get_by_wallet(self, wallet_address: str) -> User | None:
        """Get user by wallet address."""
        stmt = select(User).where(User.wallet_address == wallet_address)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, wallet_address: str, username: str | None = None) -> User:
        """Get existing user or create new one."""
        user = await self.get_by_wallet(wallet_address)
        if user:
            return user

        user = User(wallet_address=wallet_address, username=username)
        return await self.create(user)
