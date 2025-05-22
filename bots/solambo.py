"""
This is the bot that trades based on SOLAMBO pump channel
This one can be tricky and there is suspicious trading sometimes a whole hour beforehand.
However, the person adds a ton of liquidity to the pool so it is quite possible to make a lot here.
The trader for the previous one becomes the seed for the next. Transfers can be up to a couple hours before.
The new coin can mint any time in the 2 hours before, and sometimes he pulls the trade and goes into another at the last minute.
So far pumps have been executing at 11:00
NOTE: Eventually would be good to edge into buying. Perhaps half in at go time, then put half more after a large sell order (would have to detect quicker)
"""

import os
import argparse
import asyncio
from datetime import datetime
import logging
from dotenv import load_dotenv
from src.wallet.wallet import WalletType
from src.wallet.wallet_manager import WalletManager
from src.token_addresses import SOL
from src.blockchain import (
    convert_to_base_unit,
    retry_swap_tokens,
    get_wallet_contents,
)
from src.strategy.strategy import (
    ExitRules,
    poll_until_exit,
    start_keyboard_listener,
    watch_keyboard,
    wait_until,
)

load_dotenv()
now = datetime.now()
# === CONFIG ===
TARGET_TIME = now.replace(
    hour=10, minute=55, second=15  # this seems to be a good time before massive buying
)  # Set to initiate SWAP at 10:55:15
BASE_IDX = 0  # Index for the BASE wallet (trade this less frequently whenever I want to cash out or rebalance)
BOT_IDX = 0  # Index for this trade Eventually auto increment once I have a listener
MAX_SOL = 0.6  # Maximum SOL to devote to strategy

SLIPPAGE_BPS = 4500  # 45% slippage for exit trade
PRIORITIZATION_FEE = 100000
RENT_BUFFER = (
    5000000  # Rent factor (in lamports) to be left behind on all SOL transactions
)

exit_rules = ExitRules(
    max_duration_s=60 * 9,  # 9 min (from the TARGET TIME)
    take_half_at=30,  # 30% gain
    take_all_at=100,  # 100% gain
    stop_out_at=-30,  # get completely out at -30%
    polling_interval=5,  # 5s intervals
)

KEYBOARD_EXIT_MAPPING = {
    "h": "sell_half",
    "a": "sell_all",
}


# Configure Logging
def setup_logger(strategy_name="Solambo"):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_filename = f"{strategy_name}_{timestamp}.log"
    log_path = os.path.join(log_dir, log_filename)

    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Also print logs to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    console.setFormatter(formatter)
    logging.getLogger().addHandler(console)

    logging.info(f"Logger initialized. Logs will be saved to {log_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Auto-trade a token on Solana")
    parser.add_argument("--token_address", help="Mint address of the token to buy")
    parser.add_argument(
        "--amount_sol", type=float, help="Amount of SOL to swap initially"
    )
    return parser.parse_args()


async def run_strategy(trader: WalletManager, base: WalletManager, token_address: str):
    """
    This runs the strategy logic for the trade bot
    """
    from asyncio import Queue

    # Start keyboard queue and listener
    queue = Queue()
    current_override = {"event": None}
    asyncio.create_task(watch_keyboard(queue, current_override))

    def check_manual_override():
        event = current_override["event"]
        if event:
            current_override["event"] = None
            return event
        return None

    loop = asyncio.get_running_loop()
    start_keyboard_listener(queue, loop, key_command_map=KEYBOARD_EXIT_MAPPING)

    logging.info("EXECUTING SWAP STRATEGY:")
    # # MAKE INITIAL SWAP INTO TOKEN (SOL -> TOKEN)
    logging.info(f"Swapping SOL into {token_address}")
    amount_lamports = await trader.get_lamports()
    amount_lamports = max(amount_lamports - trader.rent_buffer, 0)

    transaction_info = await retry_swap_tokens(
        input_mint=SOL,
        output_mint=token_address,
        amount=amount_lamports,
        wallet_keypair=trader.keypair,
        slippage_bps=300,
        prioritization_fee=PRIORITIZATION_FEE,
    )
    logging.info(f"Swap TX: {transaction_info['signature']}")
    entry_quote = transaction_info["quote"]

    # NOW START POLLING FOR EXIT STRATEGY:
    async for event in poll_until_exit(
        exit_rules,
        input_mint=SOL,
        output_mint=token_address,
        entry_quote=entry_quote,
        check_manual_override=check_manual_override,
    ):

        logging.info(f"Event Detected: {event}")
        token_balance = await trader.get_token_balance(token_address)

        if event == "sell_half":
            amount = token_balance // 2
        elif event == "sell_all":
            pre_lamports = await trader.get_lamports()
            amount = token_balance
        else:
            continue

        await retry_swap_tokens(
            input_mint=token_address,
            output_mint=SOL,
            amount=amount,
            wallet_keypair=trader.keypair,
            slippage_bps=SLIPPAGE_BPS,
            prioritization_fee=PRIORITIZATION_FEE,
        )

        if event == "sell_all":
            break

    # Final transfer step
    if pre_lamports is not None:
        logging.info("Waiting for SOL change after exit")
        await trader.wait_for_change(prev_lamports=pre_lamports)

    sig = await trader.transfer_all_to(base.address)
    logging.info(f"Final transfer complete: {sig}")


async def main():
    setup_logger("Solambo")  # Setup logging with strategy name

    args = parse_args()
    if not args.token_address:
        raise ValueError("Token address must be provided via --token_address")
    token_address = args.token_address

    # GET BASE WALLET CONTENTS:
    base_mnemonic = os.getenv("SOLAMBO_BASE")
    trade_mnemonic = os.getenv("SOLAMBO_TRADE")
    base = WalletManager(WalletType.BOT, mnemonic=base_mnemonic, wallet_idx=BASE_IDX)
    trader = WalletManager(WalletType.BOT, mnemonic=trade_mnemonic, wallet_idx=BOT_IDX)

    base_contents = await get_wallet_contents(base.address)
    base_sol = base_contents.get(SOL, {}).get("amount", 0)
    amount_sol = min(args.amount_sol or 0, MAX_SOL, base_sol)

    # ==================================================
    # 1: TRANSFER SOL FROM BASE WALLET TO TRADING WALLET
    # ==================================================
    logging.info(
        f"Trading {amount_sol} from Base Wallet: {base.address} to {trader.address}"
    )
    lamports_to_transfer = convert_to_base_unit(SOL, amount=amount_sol)
    sig = await base.transfer_to(
        trader.address, lamports_to_transfer
    )  # transfer from base to trader
    logging.info(f"Transfer TX: {sig}")

    logging.info("Waiting for Wallet to change state:")
    await base.wait_for_change(
        prev_lamports=convert_to_base_unit(SOL, base_sol)
    )  # wait for base wallet to change state

    # ==================================================
    # 2. WAIT UNTIL TARGET TIME AND EXECUTE SWAP STRATEGY:
    # ==================================================
    logging.info(f"Waiting until: {TARGET_TIME}")
    await wait_until(TARGET_TIME)
    await run_strategy(trader, base, token_address)
    logging.info("STRATEGY COMPLETE!!")


if __name__ == "__main__":
    asyncio.run(main())
