"""Test BTC data availability."""

import asyncio
from dotenv import load_dotenv

load_dotenv()


async def main():
    from src.data.loader import PriceDataLoader

    loader = PriceDataLoader()

    print("Testing BTC (wrapped) price data...")
    try:
        data, source = await loader.load_price_history("BTC", "1H", 7)
        print(f"Source: {source}")
        print(f"Got {len(data)} data points")
        if data:
            print(f"First: {data[0]}")
            print(f"Last: {data[-1]}")
    except Exception as e:
        print(f"Error: {e}")

    print("\nTesting SOL price data...")
    try:
        data, source = await loader.load_price_history("SOL", "1H", 7)
        print(f"Source: {source}")
        print(f"Got {len(data)} data points")
        if data:
            print(f"First: {data[0]}")
            print(f"Last: {data[-1]}")
    except Exception as e:
        print(f"Error: {e}")

    await loader.close()


if __name__ == "__main__":
    asyncio.run(main())
