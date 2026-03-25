"""Tests for UserRepository."""

import pytest
from src.db.models import User
from src.db.repositories.user_repository import UserRepository


class TestUserRepository:
    """Test user repository operations."""

    @pytest.mark.asyncio
    async def test_get_by_wallet(self, db_session, sample_user):
        """Get user by wallet address."""
        repo = UserRepository(db_session)

        result = await repo.get_by_wallet(sample_user.wallet_address)

        assert result is not None
        assert result.id == sample_user.id

    @pytest.mark.asyncio
    async def test_get_by_wallet_not_found(self, db_session):
        """Get by wallet returns None for unknown address."""
        repo = UserRepository(db_session)

        result = await repo.get_by_wallet("unknown_wallet")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_existing(self, db_session, sample_user):
        """Get or create returns existing user."""
        repo = UserRepository(db_session)

        result = await repo.get_or_create(sample_user.wallet_address)

        assert result.id == sample_user.id

    @pytest.mark.asyncio
    async def test_get_or_create_new(self, db_session):
        """Get or create creates new user."""
        repo = UserRepository(db_session)

        result = await repo.get_or_create("brand_new_wallet")

        assert result.id is not None
        assert result.wallet_address == "brand_new_wallet"

    @pytest.mark.asyncio
    async def test_get_or_create_with_username(self, db_session):
        """Get or create can set username for new user."""
        repo = UserRepository(db_session)

        result = await repo.get_or_create("wallet_with_name", username="trader123")

        assert result.username == "trader123"
