"""Tests for trade routes."""

import pytest


class TestGetTrades:
    """Test GET /strategies/{id}/trades."""

    def test_get_trades_nonexistent_strategy(self, client, auth_headers):
        """Missing strategy returns 404."""
        response = client.get("/strategies/99999/trades", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_trades_empty(self, client, auth_headers, db_session, test_user):
        """Strategy with no trades returns empty paginated response."""
        from src.db.models import Strategy

        strategy = Strategy(
            external_id="trade_test",
            creator_id=test_user.id,
            name="Trade Test",
            dsl_json={"id": "trade_test"},
            status="active",
        )
        db_session.add(strategy)
        await db_session.flush()

        response = client.get(f"/strategies/{strategy.id}/trades", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
