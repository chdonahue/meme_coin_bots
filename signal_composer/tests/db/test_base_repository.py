"""Tests for BaseRepository."""

import pytest
from src.db.models import User
from src.db.repositories.base import BaseRepository


class TestBaseRepository:
    """Test base repository CRUD operations."""

    @pytest.mark.asyncio
    async def test_create(self, db_session):
        """Create adds entity to database."""
        repo = BaseRepository(db_session, User)
        user = User(wallet_address="new_wallet_123")

        result = await repo.create(user)

        assert result.id is not None
        assert result.wallet_address == "new_wallet_123"

    @pytest.mark.asyncio
    async def test_get_by_id(self, db_session, sample_user):
        """Get by ID returns entity."""
        repo = BaseRepository(db_session, User)

        result = await repo.get_by_id(sample_user.id)

        assert result is not None
        assert result.id == sample_user.id
        assert result.wallet_address == sample_user.wallet_address

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session):
        """Get by ID returns None for missing entity."""
        repo = BaseRepository(db_session, User)

        result = await repo.get_by_id(99999)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, db_session, sample_user):
        """Delete removes entity."""
        repo = BaseRepository(db_session, User)

        result = await repo.delete(sample_user.id)

        assert result is True
        assert await repo.get_by_id(sample_user.id) is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db_session):
        """Delete returns False for missing entity."""
        repo = BaseRepository(db_session, User)

        result = await repo.delete(99999)

        assert result is False
