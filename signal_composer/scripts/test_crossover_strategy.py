"""Test BTC/SOL moving average crossover strategy.

Strategy: Use BTC's moving average crossover to signal SOL trades.
- When BTC 12-period MA crosses above 26-period MA → buy SOL (golden cross)
- When BTC 12-period MA crosses below 26-period MA → sell SOL (death cross)
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

# The strategy DSL
CROSSOVER_STRATEGY = {
    "id": "btc_sol_crossover",
    "name": "BTC/SOL MA Crossover",
    "description": "Buy SOL when BTC shows golden cross, sell on death cross",
    "version": 1,
    "tokens": ["BTC", "SOL"],
    "derived_streams": [
        {
            "id": "btc_ma_fast",
            "name": "BTC 12-period MA",
            "type": "moving_average",
            "token": "BTC",
            "metric": "price",
            "window": "1h",
        },
        {
            "id": "btc_ma_slow",
            "name": "BTC 26-period MA",
            "type": "moving_average",
            "token": "BTC",
            "metric": "price",
            "window": "4h",  # Longer window for slow MA
        },
    ],
    "triggers": [
        {
            "id": "golden_cross",
            "when": {
                "metric": "btc_ma_fast",
                "op": "crosses_above",
                "compare_to": "btc_ma_slow",
            },
            "action": {
                "type": "buy",
                "token": "SOL",
                "amount_pct": 50.0,  # Buy with 50% of available capital
            },
        },
        {
            "id": "death_cross",
            "when": {
                "metric": "btc_ma_fast",
                "op": "crosses_below",
                "compare_to": "btc_ma_slow",
            },
            "action": {
                "type": "sell_all",
                "token": "SOL",
            },
        },
    ],
    "risk_rules": {
        "stop_loss_pct": -10.0,  # Negative = 10% loss triggers stop
        "max_position_pct": 50.0,
        "max_trades_per_day": 5,
        "slippage_limit_bps": 100,
    },
}


async def main():
    from src.engine.dsl.parser import parse_strategy
    from src.engine.dsl.validator import validate_strategy
    from src.simulation.backtest import BacktestEngine
    from src.data.loader import PriceDataLoader

    print("=" * 60)
    print("BTC/SOL Moving Average Crossover Strategy Test")
    print("=" * 60)

    # 1. Parse and validate the strategy
    print("\n1. Parsing strategy DSL...")
    strategy = parse_strategy(CROSSOVER_STRATEGY)
    print(f"   Strategy: {strategy.name}")
    print(f"   Tokens: {strategy.tokens}")
    print(f"   Derived streams: {[s.id for s in strategy.derived_streams]}")
    print(f"   Triggers: {[t.id for t in strategy.triggers]}")

    print("\n2. Validating strategy...")
    errors = validate_strategy(strategy)
    if errors:
        print(f"   Validation errors: {errors}")
        return
    print("   Validation passed!")

    # 2. Load real price data
    days = 30
    print(f"\n3. Loading price data ({days} days, 1H)...")
    loader = PriceDataLoader()

    try:
        # Load BTC data
        btc_data, btc_source = await loader.load_price_history("BTC", "1H", days)
        print(f"   BTC: {len(btc_data)} candles from {btc_source}")

        # Load SOL data
        sol_data, sol_source = await loader.load_price_history("SOL", "1H", days)
        print(f"   SOL: {len(sol_data)} candles from {sol_source}")

        # Merge into unified price history
        price_history = []
        for i in range(min(len(btc_data), len(sol_data))):
            price_history.append(
                {
                    "timestamp": btc_data[i]["timestamp"],
                    "BTC": btc_data[i]["BTC"],
                    "SOL": sol_data[i]["SOL"],
                }
            )
        print(f"   Merged: {len(price_history)} ticks")

        if price_history:
            print(
                f"   First: BTC=${price_history[0]['BTC']:.2f}, SOL=${price_history[0]['SOL']:.2f}"
            )
            print(
                f"   Last:  BTC=${price_history[-1]['BTC']:.2f}, SOL=${price_history[-1]['SOL']:.2f}"
            )

    finally:
        await loader.close()

    # 3. Run backtest
    print("\n4. Running backtest...")
    engine = BacktestEngine(
        initial_capital=10000.0,
        slippage_bps=50,
    )

    result = engine.run(strategy, price_history)

    # 4. Display results
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"   Initial Capital:  $10,000.00")
    print(f"   Final Value:      ${result.final_portfolio.total_value:,.2f}")
    print(f"   Total Return:     {result.total_return_pct:+.2f}%")
    print(
        f"   Sharpe Ratio:     {result.sharpe_ratio:.2f}"
        if result.sharpe_ratio
        else "   Sharpe Ratio:     N/A"
    )
    print(f"   Max Drawdown:     {result.max_drawdown_pct:.2f}%")
    print(f"   Trade Count:      {result.trade_count}")
    print(f"   Win Rate:         {result.win_rate:.1f}%")

    if result.trades:
        print("\n   Trades:")
        for i, trade in enumerate(result.trades[:10]):  # Show first 10 trades
            action_str = trade.action.value.upper()
            print(
                f"      {i+1}. {action_str} {trade.amount:.4f} {trade.token} @ ${trade.price_at_exec:.2f} ({trade.trigger_id})"
            )
        if len(result.trades) > 10:
            print(f"      ... and {len(result.trades) - 10} more trades")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
