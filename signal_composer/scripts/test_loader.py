"""Test the PriceDataLoader directly."""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


async def main():
    from src.data.loader import PriceDataLoader

    print("Testing PriceDataLoader...")
    print(f"BIRDEYE_API_KEY: {os.getenv('BIRDEYE_API_KEY', 'NOT SET')[:10]}...")

    loader = PriceDataLoader()

    try:
        print("\nLoading SOL price history (7 days, 1H interval)...")
        data, source = await loader.load_price_history("SOL", "1H", 7)
        print(f"Source: {source}")
        print(f"Got {len(data)} data points")
        if data:
            print(f"First: {data[0]}")
            print(f"Last: {data[-1]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await loader.close()


if __name__ == "__main__":
    asyncio.run(main())
