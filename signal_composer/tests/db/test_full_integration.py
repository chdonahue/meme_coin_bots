"""Full integration test for database workflow."""

import pytest
from datetime import datetime, timezone

from src.db.models import User, Strategy
from src.db.repositories import (
    UserRepository,
    StrategyRepository,
    TradeRepository,
    PerformanceRepository,
)
from src.simulation.persistence import SimulationPersistence
from src.simulation.backtest import BacktestEngine
from src.engine.dsl.types import (
    Strategy as StrategyDSL,
    Trigger,
    SimpleCondition,
    Action,
    ActionType,
    RiskRules,
    Operator,
)


class TestFullDatabaseIntegration:
    """Test complete workflow: create strategy -> backtest -> save -> query."""

    @pytest.mark.asyncio
    async def test_complete_workflow(self, db_session):
        """Full workflow from strategy creation to querying results."""
        # 1. Create user
        user_repo = UserRepository(db_session)
        user = await user_repo.get_or_create("integration_test_wallet")
        assert user.id is not None

        # 2. Create strategy DSL
        strategy_dsl = StrategyDSL(
            id="integration_test_strategy",
            name="Integration Test",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="buy_low",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.LT,
                        value=95.0,
                    ),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=25),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10,
                max_position_pct=50,
                max_trades_per_day=10,
                slippage_limit_bps=200,
            ),
        )

        # 3. Save strategy to database
        strategy_repo = StrategyRepository(db_session)
        db_strategy = Strategy(
            external_id=strategy_dsl.id,
            creator_id=user.id,
            name=strategy_dsl.name,
            description="Integration test strategy",
            dsl_json=strategy_dsl.model_dump(),
            status="active",
            is_public=True,
        )
        db_strategy = await strategy_repo.create(db_strategy)
        assert db_strategy.id is not None

        # 4. Run backtest
        price_history = [
            {"SOL": 100.0},
            {"SOL": 94.0},  # Buy trigger
            {"SOL": 92.0},  # Buy trigger
            {"SOL": 105.0},
        ]
        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=100)
        result = engine.run(strategy_dsl, price_history)

        assert result.trade_count >= 1

        # 5. Save backtest results
        trade_repo = TradeRepository(db_session)
        perf_repo = PerformanceRepository(db_session)
        persistence = SimulationPersistence(trade_repo, perf_repo)
        await persistence.save_backtest_result(db_strategy.id, result)

        # 6. Query and verify
        saved_trades = await trade_repo.list_by_strategy(db_strategy.id)
        assert len(saved_trades) == result.trade_count

        perf = await perf_repo.get_latest(db_strategy.id)
        assert perf is not None
        assert perf.total_return_pct == result.total_return_pct

        # 7. Query strategy with trades
        strategy_from_db = await strategy_repo.get_by_external_id("integration_test_strategy")
        assert strategy_from_db is not None
        assert strategy_from_db.name == "Integration Test"
