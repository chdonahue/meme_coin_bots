"""
This script will start polling SOL and USDC every hour and save to the supabase database.
It runs indefinitely.
"""

import asyncio
import signal
import sys
from functools import partial
from src.blockchain import get_jupiter_quote
from src.polling.quote_poller import QuotePoller
from src.db.supabase import save_quote_to_supabase, get_supabase_pool
from src.token_addresses import SOL, USDC


poller = None  # Global reference so signal handler can access it


def signal_handler(sig, _):
    print(f"\nReceived signal {sig}. Shutting down gracefully...")
    if poller:
        poller.stop()  # Your QuotePoller.stop() method
    print("Cleanup complete. Exiting.")
    sys.exit(0)


async def main():
    global poller

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        quote_queue = asyncio.Queue()
        pool = await get_supabase_pool()

        poller = QuotePoller(
            input_mint=SOL,
            output_mint=USDC,
            input_amount=1_000_000_000,  # 1 SOL
            quote_func=get_jupiter_quote,
            min_quote_interval=3600,  # fixed to 1hr intervals
            max_quote_interval=3600,
            quote_queue=quote_queue,
            save_callback=partial(save_quote_to_supabase, pool=pool),
        )
        await poller.start()
    except Exception as e:
        print(f"Failed to start poller: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
