"""Quick test of Birdeye API."""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


async def test_birdeye():
    from src.data.sources.birdeye import BirdeyeDataSource

    api_key = os.getenv("BIRDEYE_API_KEY")
    print(f"API Key: {api_key[:10]}..." if api_key else "API Key: NOT SET")

    birdeye = BirdeyeDataSource()

    # Test health check
    print("\n1. Testing health check...")
    healthy = await birdeye.health_check()
    print(f"   Health: {'OK' if healthy else 'FAILED'}")

    # Test price fetch
    print("\n2. Testing price fetch for SOL...")
    sol_mint = "So11111111111111111111111111111111111111112"
    price = await birdeye.get_price(sol_mint)
    if price:
        print(f"   SOL Price: ${price.price:.2f}")
    else:
        print("   Price fetch FAILED")

    # Test OHLCV fetch
    print("\n3. Testing OHLCV fetch for SOL...")
    ohlcv = await birdeye.get_ohlcv(sol_mint, "1H", 24)
    print(f"   Got {len(ohlcv)} candles")
    if ohlcv:
        print(f"   Latest: {ohlcv[-1].timestamp} - Close: ${ohlcv[-1].close:.2f}")

    await birdeye.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(test_birdeye())
