"""CLI for testing SignalComposer engine."""

import argparse
import asyncio
import sys
from pathlib import Path

from .engine.dsl.parser import parse_strategy_file, ParseError
from .engine.dsl.validator import validate_strategy
from .engine.dsl.executor import StrategyExecutor
from .data.sources.jupiter import JupiterDataSource


def cmd_parse(args: argparse.Namespace) -> int:
    """Parse and validate a strategy file."""
    try:
        strategy = parse_strategy_file(args.file)
        print(f"Parsed strategy: {strategy.name}")
        print(f"  ID: {strategy.id}")
        print(f"  Tokens: {', '.join(strategy.tokens)}")
        print(f"  Triggers: {len(strategy.triggers)}")
        print(f"  Derived streams: {len(strategy.derived_streams)}")

        errors = validate_strategy(strategy)
        if errors:
            print("\nValidation errors:")
            for error in errors:
                print(f"  - {error}")
            return 1
        else:
            print("\nValidation passed")
            return 0

    except ParseError as e:
        print(f"Parse error: {e.message}")
        if e.details:
            print(f"  Details: {e.details}")
        return 1


async def cmd_price(args: argparse.Namespace) -> int:
    """Fetch current price for a token."""
    source = JupiterDataSource()
    try:
        tick = await source.get_price(args.token)
        if tick:
            print(f"Token: {tick.token}")
            print(f"Price: ${tick.price:.6f}")
            print(f"Source: {tick.source}")
            print(f"Time: {tick.timestamp.isoformat()}")
            return 0
        else:
            print(f"Could not fetch price for {args.token}")
            return 1
    finally:
        await source.close()


async def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a strategy against current market data."""
    try:
        strategy = parse_strategy_file(args.file)
        print(f"Evaluating strategy: {strategy.name}")

        # Fetch prices for tokens
        source = JupiterDataSource()
        try:
            prices = await source.get_prices(strategy.tokens)
        finally:
            await source.close()

        # Build market data (simplified - just current price)
        market_data = {}
        for token, tick in prices.items():
            market_data[token] = {
                "price": tick.price,
                "price_change_pct": {"15m": 0.0},  # Placeholder
                "volume": {"15m": 0},  # Placeholder
            }
            print(f"  {token}: ${tick.price:.6f}")

        # Evaluate
        executor = StrategyExecutor(strategy)
        actions = executor.evaluate(market_data)

        if actions:
            print(f"\n{len(actions)} trigger(s) fired:")
            for ta in actions:
                print(f"  - {ta.trigger_id}: {ta.action.type.value} {ta.action.token}")
        else:
            print("\nNo triggers fired")

        return 0

    except ParseError as e:
        print(f"Parse error: {e.message}")
        return 1


async def cmd_backtest(args: argparse.Namespace) -> int:
    """Run backtest with generated price history."""
    from datetime import datetime, timezone, timedelta
    import random

    try:
        strategy = parse_strategy_file(args.file)
        print(f"Backtesting strategy: {strategy.name}")
        print(f"Initial capital: ${args.capital:,.2f}")
        print(f"Days: {args.days}")
        print()

        # Generate synthetic price history for demo
        base_price = 100.0
        base_time = datetime.now(timezone.utc) - timedelta(days=args.days)
        price_history = []

        for i in range(args.days * 48):  # 48 ticks per day (30 min intervals)
            timestamp = base_time + timedelta(minutes=i * 30)
            change = random.gauss(0.001, 0.02)  # Random walk with drift
            base_price *= 1 + change

            tick = {"timestamp": timestamp}
            for token in strategy.tokens:
                tick[token] = base_price * (1 + random.gauss(0, 0.01))
            price_history.append(tick)

        # Run backtest
        from .simulation.backtest import BacktestEngine

        engine = BacktestEngine(
            initial_capital=args.capital,
            slippage_bps=args.slippage,
        )
        result = engine.run(strategy, price_history)

        # Print results
        print("=" * 50)
        print("BACKTEST RESULTS")
        print("=" * 50)
        print(f"Total Return:   {result.total_return_pct:+.2f}%")
        print(
            f"Sharpe Ratio:   {result.sharpe_ratio:.2f}"
            if result.sharpe_ratio
            else "Sharpe Ratio:   N/A"
        )
        print(f"Max Drawdown:   {result.max_drawdown_pct:.2f}%")
        print(f"Trade Count:    {result.trade_count}")
        print(
            f"Win Rate:       {result.win_rate:.1f}%" if result.win_rate else "Win Rate:       N/A"
        )
        print()
        print(f"Final Value:    ${result.equity_curve[-1]:,.2f}")

        if args.verbose and result.trades:
            print()
            print("TRADE LOG (last 10):")
            print("-" * 50)
            for trade in result.trades[-10:]:
                print(
                    f"  {trade.timestamp.strftime('%Y-%m-%d %H:%M')} | {trade.action.value.upper():8} | {trade.token} | ${trade.amount:.2f} @ ${trade.price_at_exec:.2f}"
                )

        return 0

    except ParseError as e:
        print(f"Parse error: {e.message}")
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SignalComposer CLI",
        prog="signal-composer",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # parse command
    parse_parser = subparsers.add_parser("parse", help="Parse and validate a strategy")
    parse_parser.add_argument("file", type=Path, help="Strategy JSON file")

    # price command
    price_parser = subparsers.add_parser("price", help="Get current price for a token")
    price_parser.add_argument("token", help="Token mint address")

    # evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate strategy against market")
    eval_parser.add_argument("file", type=Path, help="Strategy JSON file")

    # backtest command
    backtest_parser = subparsers.add_parser(
        "backtest", help="Run backtest with generated price history"
    )
    backtest_parser.add_argument("file", type=Path, help="Strategy JSON file")
    backtest_parser.add_argument(
        "--capital", type=float, default=10000, help="Initial capital (default: 10000)"
    )
    backtest_parser.add_argument(
        "--days", type=int, default=30, help="Number of days to simulate (default: 30)"
    )
    backtest_parser.add_argument(
        "--slippage", type=int, default=100, help="Slippage in basis points (default: 100)"
    )
    backtest_parser.add_argument("-v", "--verbose", action="store_true", help="Show trade log")

    args = parser.parse_args()

    if args.command == "parse":
        return cmd_parse(args)
    elif args.command == "price":
        return asyncio.run(cmd_price(args))
    elif args.command == "evaluate":
        return asyncio.run(cmd_evaluate(args))
    elif args.command == "backtest":
        return asyncio.run(cmd_backtest(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
