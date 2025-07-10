"""
This script will continuously monitor newly raydium bonded tokens by listening to this wallet: 39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg
It will poll the token exchange rates and add to the quotes table (log scale resolution) for 48 hours
It will save metadata to the token_metadata table
It will extract bonding history (TODO) to a new table
"""

import asyncio
import signal
import sys
import logging
from functools import partial
from src.blockchain import get_jupiter_quote, get_token_metadata
from src.polling.quote_poller import QuotePoller
from src.transaction_parser import (
    get_transaction_json,
    classify_transaction,
    extract_new_token_mint,
)
from src.listeners.wallet_listener import WalletListener
from src.db.supabase import save_quote_to_supabase, save_token_metadata_to_supabase
from src.utils.logging_utils import setup_logger
from src.token_addresses import SOL

RAYDIUM_BONDING_WALLET = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
active_pollers = []
shutdown_event = asyncio.Event()
seen_tokens = set()


def signal_handler(sig, frame):
    logging.info(f"\n[!] Received signal {sig}. Initiating shutdown...")
    shutdown_event.set()  # Triggers shutdown logic in async code


async def process_signature(sig: str):
    try:
        tx_json = await get_transaction_json(sig)
        tx_type = classify_transaction(tx_json)

        if tx_type != "add_liquidity":
            return  # ignore irrelevant transactions

        token_address = extract_new_token_mint(tx_json)
        if not token_address:
            logging.info(f"[{sig}] No token address extracted.")
            return

        logging.info(f"[{sig}] Detected new bonding: {token_address}")
        asyncio.create_task(handle_new_token(token_address))

    except Exception as e:
        logging.warning(f"[{sig}] Failed to process transaction: {e}")


async def handle_new_token(token_address: str):
    if token_address in seen_tokens:
        logging.info(f"[~] Token {token_address} already being handled, skipping.")
        return
    seen_tokens.add(token_address)
    logging.info(f"[+] New bonded token detected: {token_address}")

    try:
        # Get token metadata and store in supabase:
        metadata = await get_token_metadata(token_address)
        await save_token_metadata_to_supabase(metadata)

        # Create a fresh queue for this token
        quote_queue = asyncio.Queue()

        poller = QuotePoller(
            input_mint=SOL,
            output_mint=token_address,
            input_amount=1_000_000_000,  # 1 SOL
            quote_func=get_jupiter_quote,
            min_quote_interval=15,  # 15s (need to stay under free API limits)
            max_quote_interval=60 * 20,  # max of every 20 minutes
            duration_s=3600 * 10,  # 10 hours
            quote_queue=quote_queue,
            save_callback=partial(save_quote_to_supabase),
        )

        task = asyncio.create_task(poller.start())
        active_pollers.append(task)

    except Exception as e:
        logging.warning(f"[!] Failed to handle new token {token_address}: {e}")


async def shutdown():
    logging.info("[!] Stopping all active pollers...")
    for task in active_pollers:
        task.cancel()
    await asyncio.gather(*active_pollers, return_exceptions=True)
    logging.info("[✓] Shutdown complete. Exiting.")
    sys.exit(0)


async def main():
    setup_logger("raydium_bonding")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    listener = WalletListener(wallets=[RAYDIUM_BONDING_WALLET])
    await listener.connect()
    logging.info("[*] Listening for bonding transactions...")

    async def listen_loop():
        async for sig in listener.listen_signatures():
            asyncio.create_task(process_signature(sig))

    # Start listener in background so we can await shutdown
    asyncio.create_task(listen_loop())

    # Wait for shutdown signal
    await shutdown_event.wait()
    await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
