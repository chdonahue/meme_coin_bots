"""Tests for performance routes."""

import pytest


class TestGetPerformance:
    """Test GET /strategies/{id}/performance."""

    def test_get_performance_nonexistent_strategy(self, client, auth_headers):
        """Missing strategy returns 404."""
        response = client.get("/strategies/99999/performance", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_performance_empty(self, client, auth_headers, db_session, test_user):
        """Strategy with no performance returns empty list."""
        from src.db.models import Strategy

        # Create a strategy
        strategy = Strategy(
            external_id="perf_test",
            creator_id=test_user.id,
            name="Perf Test",
            dsl_json={"id": "perf_test"},
            status="active",
        )
        db_session.add(strategy)
        await db_session.flush()

        response = client.get(f"/strategies/{strategy.id}/performance", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []
