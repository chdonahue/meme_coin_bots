"""
Contains tools for defining strategies
"""

import time
import re
import asyncio
import logging
from pynput.keyboard import Listener
import threading
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List
from src.token_addresses import SOL
from src.blockchain import get_jupiter_quote


@dataclass
class ExitRules:
    """
    Trading rules for a strategy
    """

    max_duration_s: int  # Number of seconds to commit to the strategy
    take_half_at: float  # At what % gain to sell half (i.e. 50)
    take_all_at: float  # At what % gain to sell all (i.e. 100)
    stop_out_at: float  # At what % loss to sell all  (i.e. -20)
    polling_interval: int  # polling frequency (in seconds)


def get_sol_per_token(quote: dict) -> float:
    """
    Gets the exchange rate of a token from a jupiter quote. Returned in sol per token.

    Args:
        quote (dict): Dictionary returned from get_jupiter_quote()

    Returns:
        sol_per_token (float): Exchange rate (Sol per token)
    """
    if quote["inputMint"] == SOL:
        sol_amount = int(quote["inAmount"])
        token_amount = int(quote["outAmount"])
    elif quote["outputMint"] == SOL:
        sol_amount = int(quote["outAmount"])
        token_amount = int(quote["inAmount"])
    sol_per_token = sol_amount / token_amount
    return sol_per_token


def get_percent_change(initial_quote, new_quote):
    """
    Given an initial and new dictionary, return the percent return

    Args:
        initial_quote (dict): initial quote dictionary
        new_quote (dict): new quote dictionary

    Returns:
        percent_return (float): Percent change (rounded to 3 decimal places)
    """
    initial_rate = get_sol_per_token(initial_quote)
    new_rate = get_sol_per_token(new_quote)
    percent_return = ((new_rate - initial_rate) / initial_rate) * 100
    return round(percent_return, 3)


async def poll_until_exit(
    rules: ExitRules,
    input_mint: str,
    output_mint: str,
    entry_quote: dict,
    check_manual_override=None,
):
    """
    This is an asynchronous generator that will poll at fixed intervals to get the exchange rate of the input and output tokens
    It will yield a command signal for the trader of the strategy when exit conditions are met.

    Args:
        rules (ExitRules): Rules governing this strategy
        input_mint (str): Input mint address
        output_mint (str): Output mint address
        entry_quote (dict): Initial quote for the token pair
        check_manual_override: for keyboard intervention

    Returns:
        Exit rule (str): String with control instruction
    """
    DUMMY_AMOUNT = (
        1000000  # Since we're working with ratios, this amount doesn't matter
    )
    t0 = time.monotonic()
    sold_half = False

    while True:
        # Check keyboard override first
        if check_manual_override and (override := check_manual_override()):
            yield override
            if override == "sell_all":
                return

        now = time.monotonic()
        elapsed = now - t0
        new_quote = await get_jupiter_quote(input_mint, output_mint, DUMMY_AMOUNT)
        pct_change = get_percent_change(entry_quote, new_quote)
        logging.info(f"Time Elapsed: {round(elapsed,2)}s, % Change: {pct_change}")

        # EVALUATE RULES:
        if pct_change <= rules.stop_out_at:
            yield "sell_all"
            return
        if not sold_half and pct_change >= rules.take_half_at:
            sold_half = True
            yield "sell_half"
            continue
        if pct_change >= rules.take_all_at:
            yield "sell_all"
            return
        if elapsed >= rules.max_duration_s:
            yield "sell_all"
            return
        await asyncio.sleep(rules.polling_interval)


async def wait_until(target_time: datetime):
    """
    Async wait until the system clock reaches the specified datetime.
    This can be used to wait until specific clock times to execute portions of the strategy

    Args:
        target_time (datetime): The target datetime to wait for
    """
    logging.info(f"Waiting until {target_time.strftime('%Y-%m-%d %H:%M:%S')}")

    while True:
        now = datetime.now()
        if now >= target_time:
            logging.info("Target time reached. Continuing execution.")
            return
        sleep_time = min((target_time - now).total_seconds(), 1.0)
        await asyncio.sleep(sleep_time)


def start_keyboard_listener(
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    key_command_map: Dict[str, str],
):
    def on_press(key):
        try:
            if hasattr(key, "char") and key.char:
                char = key.char.lower()
                if char in key_command_map:
                    logging.info(f"Key '{char}' OVERRIDE: {key_command_map[char]}")
                    asyncio.run_coroutine_threadsafe(
                        queue.put(key_command_map[char]), loop
                    )
        except Exception as e:
            logging.warning(f"Error handling key press: {e}")

    def listen():
        with Listener(on_press=on_press) as listener:
            listener.join()

    threading.Thread(target=listen, daemon=True).start()


async def watch_keyboard(queue: asyncio.Queue, current_override: dict):
    while True:
        command = await queue.get()
        current_override["event"] = command
        logging.info(f"Keyboard override set: {command}")


def find_solana_addresses(text: str) -> List[str]:
    """
    Function that finds all Solana addresses in a given string.

    Args:
        text: The text to search for Solana addresses

    Returns:
        List[str]: List of Solana addresses found
    """
    solana_regex = r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"
    return re.findall(solana_regex, text)
