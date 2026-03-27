"""Tests for strategy routes."""

import pytest


class TestCreateStrategy:
    """Test POST /strategies."""

    @pytest.mark.asyncio
    async def test_create_strategy_success(self, client, auth_headers):
        """Create strategy with valid DSL."""
        dsl = {
            "id": "test_strategy",
            "name": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [],
            "triggers": [],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 10,
                "slippage_limit_bps": 100,
            },
        }

        response = client.post(
            "/strategies",
            json={"name": "Test Strategy", "dsl": dsl},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Strategy"
        assert data["external_id"] == "test_strategy"

    def test_create_strategy_without_auth_returns_401(self, client):
        """Missing auth returns 401."""
        response = client.post("/strategies", json={"name": "Test", "dsl": {}})
        assert response.status_code in (401, 403)


class TestListStrategies:
    """Test GET /strategies."""

    @pytest.mark.asyncio
    async def test_list_strategies_empty(self, client, auth_headers):
        """List returns empty when no strategies."""
        response = client.get("/strategies", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []


class TestGetStrategy:
    """Test GET /strategies/{id}."""

    def test_get_nonexistent_strategy_returns_404(self, client, auth_headers):
        """Missing strategy returns 404."""
        response = client.get("/strategies/99999", headers=auth_headers)
        assert response.status_code == 404


class TestDeleteStrategy:
    """Test DELETE /strategies/{id}."""

    def test_delete_nonexistent_strategy_returns_404(self, client, auth_headers):
        """Missing strategy returns 404."""
        response = client.delete("/strategies/99999", headers=auth_headers)
        assert response.status_code == 404
