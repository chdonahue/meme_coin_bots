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

    args = parser.parse_args()

    if args.command == "parse":
        return cmd_parse(args)
    elif args.command == "price":
        return asyncio.run(cmd_price(args))
    elif args.command == "evaluate":
        return asyncio.run(cmd_evaluate(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
