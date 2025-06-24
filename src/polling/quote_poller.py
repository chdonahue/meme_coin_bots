import asyncio
import logging
import math
from datetime import datetime, UTC
from typing import Callable, Optional
from src.token_addresses import SOL, USDC
from src.blockchain import get_jupiter_quote


def get_interval(
    elapsed_seconds: float,
    total_seconds: float,
    min_interval: float,
    max_interval: float,
):
    """
    Returns an interval on a log scale so that polling becomes less frequent over time. This is mainly to save space and API calls.
    If you want a linear relationship, set min_interval and max_itnerval to be equal

    Args:
        elapsed_seconds (float): Time elapsed so far in seconds
        total_seconds (float): Total time (in s) to poll
        min_interval (float): The minimum polling interval (s) to start at
        max_interval (float): The maximum interval to end polling at
    """
    # Use log scale with smoothing
    log_scale = math.log10(1 + 9 * (elapsed_seconds / total_seconds))  # from 0 to ~1
    return min_interval + log_scale * (max_interval - min_interval)


class QuotePoller:
    """
    Grabs quotes on a logarhthmic schedule
    Args:
        input_mint (str): input token address
        output_mint (str): output token address
        input_amount (int): The number of input tokens to trade (base units)
        duration_s (float): Duration to run polling
        quote_func (function): Usually will be get_jupiter_quote()
        quote_queue (Queue): Holds a queue that can be used to pass quotes
        save_callback (function): Option to save data
        min_quote_interval (float): Minimum interval to poll
        max_quote_interval (float): Maximum interval to poll
    """

    def __init__(
        self,
        input_mint: str,
        output_mint: str,
        input_amount: int,
        duration_s: Optional[float] = None,
        quote_queue: Optional[asyncio.Queue] = None,
        quote_func: Callable[[str, str, int], dict] = None,
        save_callback: Optional[Callable[[dict], None]] = None,
        min_quote_interval: float = 30,
        max_quote_interval: float = 60,
    ):
        self.input_mint = input_mint
        self.output_mint = output_mint
        self.input_amount = input_amount
        self.duration_s = duration_s
        self.quote_queue = quote_queue
        self.quote_func = quote_func
        self.save_callback = save_callback
        self.min_quote_interval = min_quote_interval
        self.max_quote_interval = max_quote_interval
        self.start_time = datetime.now(UTC)
        self.running = True

    async def start(self):
        while (
            self.duration_s is None
            or (datetime.now(UTC) - self.start_time).total_seconds() < self.duration_s
        ):
            if not self.running:
                break
            try:
                quote = await self.quote_func(
                    self.input_mint, self.output_mint, amount=self.input_amount
                )
                data = {
                    "timestamp": datetime.now(UTC),
                    "input_mint": self.input_mint,
                    "input_amount": self.input_amount,
                    "output_mint": self.output_mint,
                    "output_amount": int(quote["outAmount"]),
                    "price_impact_pct": float(quote["priceImpactPct"]),
                }
                if self.save_callback:
                    await self.save_callback(data)
                if self.quote_queue:
                    await self.quote_queue.put(data)  # Put the quote into the queue
                logging.debug(
                    f"[QuotePoller {data['timestamp']}]: Quote: {data['input_mint']}:{self.input_amount} -> {data['output_mint']}:{data['output_amount']}"
                )
                # Save quote...
            except Exception as e:
                logging.warning(f"[QuotePoller] Error: {e}")

            if self.duration_s is not None:
                elapsed_s = (datetime.now(UTC) - self.start_time).total_seconds()
                interval = get_interval(
                    elapsed_seconds=elapsed_s,
                    total_seconds=self.duration_s,
                    min_interval=self.min_quote_interval,
                    max_interval=self.max_quote_interval,
                )
            else:
                # For infinite duration, just use the min_quote_interval
                interval = self.min_quote_interval
            await asyncio.sleep(interval)

    def stop(self):
        """Method to gracefully stop the poller"""
        self.running = False


async def main():
    poller = QuotePoller(
        input_mint=SOL,
        output_mint=USDC,
        input_amount=1_000_000,  # 0.1 SOL
        duration_s=120,
        quote_func=get_jupiter_quote,
        min_quote_interval=10,
        max_quote_interval=20,
        # save_callback=save_quote_data
    )

    await poller.start()


if __name__ == "__main__":
    asyncio.run(main())
