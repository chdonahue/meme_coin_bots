"""Repository for trading wallet operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TradingWallet
from src.wallets import encrypt_private_key


class WalletRepository:
    """CRUD operations for trading wallets."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        address: str,
        private_key_b58: str,
        label: str | None = None,
    ) -> TradingWallet:
        """Create a new trading wallet with encrypted key."""
        encrypted = encrypt_private_key(private_key_b58)
        wallet = TradingWallet(
            user_id=user_id,
            address=address,
            encrypted_private_key=encrypted,
            label=label,
        )
        self.session.add(wallet)
        await self.session.commit()
        await self.session.refresh(wallet)
        return wallet

    async def get_by_id(self, wallet_id: int) -> TradingWallet | None:
        """Get wallet by ID."""
        result = await self.session.execute(
            select(TradingWallet).where(TradingWallet.id == wallet_id)
        )
        return result.scalar_one_or_none()

    async def get_by_address(self, address: str) -> TradingWallet | None:
        """Get wallet by address."""
        result = await self.session.execute(
            select(TradingWallet).where(TradingWallet.address == address)
        )
        return result.scalar_one_or_none()

    async def get_user_wallets(self, user_id: int) -> list[TradingWallet]:
        """Get all wallets for a user."""
        result = await self.session.execute(
            select(TradingWallet).where(TradingWallet.user_id == user_id)
        )
        return list(result.scalars().all())
