"""
This is a testbot to make sure that trading is working. Check keyboard override. No timing tested here
"""

import os
import argparse
import asyncio
from datetime import datetime
import logging
from dotenv import load_dotenv

from src.wallet.wallet import WalletType
from src.wallet.wallet_manager import WalletManager
from src.token_addresses import SOL, USDC
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
)

load_dotenv()
MAX_SOL = 0.05  # Maximum SOL to devote to strategy

SLIPPAGE_BPS = 4500  # 45% slippage for exit trade
PRIORITIZATION_FEE = 60000

exit_rules = ExitRules(
    max_duration_s=60,  # 1 min (from the TARGET TIME)
    take_half_at=20,  # 60% gain
    take_all_at=200,  # 250% gain
    stop_out_at=-30,  # get completely out at -30%
    polling_interval=5,  # 5s intervals
)

KEYBOARD_EXIT_MAPPING = {
    "h": "sell_half",
    "a": "sell_all",
}


# Configure Logging
def setup_logger(strategy_name="Test"):
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

    # SWAP INTO TOKEN:
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

    # EXIT LOGIC:
    pre_lamports = None
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
    setup_logger("Test")  # Setup logging with strategy name
    args = parse_args()

    # Setup Strategy parameters: Trade from TEST wallet to solambo base 0:
    mnemonic = os.getenv("SOLAMBO_BASE")
    base = WalletManager(WalletType.TEST)
    trader = WalletManager(WalletType.BOT, mnemonic=mnemonic, wallet_idx=0)

    base_contents = await get_wallet_contents(base.address)
    base_sol = base_contents.get(SOL, {}).get("amount", 0)
    amount_sol = min(args.amount_sol or 0, MAX_SOL, base_sol)
    logging.info(f"Transferring {amount_sol} SOL to trade wallet")
    lamports_to_transfer = convert_to_base_unit(SOL, amount_sol)
    sig = await base.transfer_to(
        trader.address, lamports_to_transfer
    )  # transfer from base to trader
    logging.info(f"Transfer TX: {sig}")

    await base.wait_for_change(
        prev_lamports=convert_to_base_unit(SOL, base_sol)
    )  # wait for base wallet to change state

    await run_strategy(trader, base, USDC)

    logging.info("STRATEGY COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
