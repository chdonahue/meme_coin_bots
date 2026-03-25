"""Tests for StrategyRepository."""

import pytest
from src.db.models import Strategy
from src.db.repositories.strategy_repository import StrategyRepository


class TestStrategyRepository:
    """Test strategy repository operations."""

    @pytest.mark.asyncio
    async def test_get_by_external_id(self, db_session, sample_strategy):
        """Get strategy by external ID."""
        repo = StrategyRepository(db_session)

        result = await repo.get_by_external_id(sample_strategy.external_id)

        assert result is not None
        assert result.id == sample_strategy.id

    @pytest.mark.asyncio
    async def test_get_by_external_id_not_found(self, db_session):
        """Get by external ID returns None for unknown."""
        repo = StrategyRepository(db_session)

        result = await repo.get_by_external_id("unknown_id")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_user(self, db_session, sample_user, sample_strategy):
        """List strategies by user."""
        repo = StrategyRepository(db_session)

        result = await repo.list_by_user(sample_user.id)

        assert len(result) == 1
        assert result[0].id == sample_strategy.id

    @pytest.mark.asyncio
    async def test_list_by_user_empty(self, db_session, sample_user):
        """List by user returns empty for user with no strategies."""
        repo = StrategyRepository(db_session)

        # sample_user has no strategies yet (no sample_strategy fixture)
        result = await repo.list_by_user(sample_user.id)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_public(self, db_session, sample_strategy):
        """List public strategies."""
        repo = StrategyRepository(db_session)

        result = await repo.list_public(limit=10)

        assert len(result) == 1
        assert result[0].is_public is True

    @pytest.mark.asyncio
    async def test_save_dsl(self, db_session, sample_strategy):
        """Save updated DSL JSON."""
        repo = StrategyRepository(db_session)
        new_dsl = {"id": "test", "name": "Updated", "tokens": ["ETH"]}

        result = await repo.save_dsl(sample_strategy.id, new_dsl)

        assert result.dsl_json == new_dsl
