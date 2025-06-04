import logging
from functools import wraps
from src.strategy.strategy import find_solana_addresses


def deduplicate_token_mentions(process_token_fn, memory_store=None):
    """
    Wraps a token handler to only run once per unique token.
    Designed for Telegram message dicts containing token addresses.
    """
    if memory_store is None:
        memory_store = {}

    def decorator(handler):
        @wraps(handler)
        async def wrapper(msg, *args, **kwargs):
            text = msg["text"]
            timestamp = msg["timestamp"]
            addresses = find_solana_addresses(text)

            for token in addresses:
                if token not in memory_store:
                    logging.info(f"[{timestamp}] New token mentioned: {token}")
                    memory_store[token] = timestamp
                    await process_token_fn(token, timestamp, msg, *args, **kwargs)
                else:
                    logging.info(f"[{timestamp}] Repeat mention: {token}")

        return wrapper

    return decorator
