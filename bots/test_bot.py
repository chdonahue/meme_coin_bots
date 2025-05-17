"""
This is a testbot to make sure that trading is working. Check keyboard override. No timing tested here
"""

import os
import argparse
import asyncio
from datetime import datetime
import logging
from dotenv import load_dotenv
from src.wallet_secrets import (
    WalletType,
    get_wallet_address,
    get_wallet_keypair,
)
from src.blockchain import (
    convert_to_base_unit,
    transfer_sol,
    retry_swap_tokens,
    get_wallet_contents,
    wait_for_sol_diff,
)
from src.strategy import (
    ExitRules,
    poll_until_exit,
    start_keyboard_listener,
    watch_keyboard,
    wait_until,
)
from src.token_addresses import SOL, USDC

load_dotenv()
MAX_SOL = 0.05  # Maximum SOL to devote to strategy

SLIPPAGE_BPS = 4500  # 45% slippage for exit trade
PRIORITIZATION_FEE = 60000
RENT_BUFFER = (
    5000000  # Rent factor (in lamports) to be left behind on all SOL transactions
)

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

# Get wallets for this strategy:
base_phrase = os.getenv("SOLAMBO_BASE")
base_bot_address = get_wallet_address(wallet_type=WalletType.TEST)
base_bot_keypair = get_wallet_keypair(wallet_type=WalletType.TEST)
trade_bot_address = get_wallet_address(
    wallet_type=WalletType.BOT, mnemonic_phrase=base_phrase, wallet_idx=0
)
trade_bot_keypair = get_wallet_keypair(
    wallet_type=WalletType.BOT, mnemonic_phrase=base_phrase, wallet_idx=0
)


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


async def run_strategy(token_address, exit_rules):
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
    pre_trade_lamports = 0
    # # MAKE INITIAL SWAP INTO TOKEN (SOL -> TOKEN)
    logging.info(f"Swapping SOL into {token_address}")
    wallet_contents = await get_wallet_contents(trade_bot_address)
    amount_lamports = wallet_contents.get(SOL, {}).get("raw_amount", 0) - RENT_BUFFER
    transaction_info = await retry_swap_tokens(
        input_mint=SOL,
        output_mint=token_address,
        amount=amount_lamports,
        wallet_keypair=trade_bot_keypair,
        slippage_bps=300,  # Lower slippage for the initial trade in
        prioritization_fee=PRIORITIZATION_FEE,
    )
    logging.info(f"Transaction executed: {transaction_info['signature']}")

    # NOW START POLLING FOR EXIT STRATEGY:
    entry_quote = transaction_info["quote"]

    async for event in poll_until_exit(
        exit_rules,
        input_mint=SOL,
        output_mint=token_address,
        entry_quote=entry_quote,
        check_manual_override=check_manual_override,
    ):

        logging.info(f"Event Detected: {event}")

        if event == "sell_half":
            wallet_contents = await get_wallet_contents(trade_bot_address)
            exit_amount = max(
                wallet_contents.get(token_address, {}).get("raw_amount", 0) // 2, 0
            )
            await retry_swap_tokens(
                input_mint=token_address,
                output_mint=SOL,
                amount=exit_amount,
                wallet_keypair=trade_bot_keypair,
                slippage_bps=SLIPPAGE_BPS,
                prioritization_fee=PRIORITIZATION_FEE,
            )
            continue

        elif event == "sell_all":
            wallet_contents = await get_wallet_contents(trade_bot_address)
            exit_amount = wallet_contents.get(token_address, {}).get("raw_amount", 0)
            pre_trade_lamports = wallet_contents.get(SOL, {}).get("raw_amount", 0)

            await retry_swap_tokens(
                input_mint=token_address,
                output_mint=SOL,
                amount=exit_amount,
                wallet_keypair=trade_bot_keypair,
                slippage_bps=SLIPPAGE_BPS,
                prioritization_fee=PRIORITIZATION_FEE,
                max_retries=10,
            )
            break  # exit the loop cleanly

    # Final transfer step
    logging.info("Waiting for Wallet to change state:")
    await wait_for_sol_diff(
        address=trade_bot_address, prev_lamports=pre_trade_lamports, timeout=30
    )
    wallet_contents = await get_wallet_contents(trade_bot_address)
    lamports_to_transfer = (
        wallet_contents.get(SOL, {}).get("raw_amount", 0) - RENT_BUFFER
    )
    lamports_to_transfer = max(lamports_to_transfer, 0)
    logging.info(
        f"Transferring {lamports_to_transfer} lamports from {trade_bot_address} to {base_bot_address}"
    )
    signature = await transfer_sol(
        trade_bot_keypair, base_bot_address, lamports_to_transfer
    )
    logging.info(
        f"Transferred {lamports_to_transfer} from trade wallet to base wallet: ({base_bot_address})"
    )
    logging.info(f"Signature: {signature}")


async def main():
    setup_logger("Solambo")  # Setup logging with strategy name

    args = parse_args()

    token_address = USDC
    # GET BASE WALLET CONTENTS:
    base_wallet_contents = await get_wallet_contents(base_bot_address)
    base_wallet_sol = base_wallet_contents.get(SOL, {}).get("amount", 0)
    amount_sol = min(
        args.amount_sol, MAX_SOL, base_wallet_sol
    )  # Get a safe amount of SOL to transfer

    # ==================================================
    # 1: TRANSFER SOL FROM BASE WALLET TO TRADING WALLET
    # ==================================================
    logging.info(f"Trading {amount_sol} from Base Wallet: {base_bot_address}")
    lamports_to_transfer = convert_to_base_unit(SOL, amount=amount_sol) - RENT_BUFFER
    signature = await transfer_sol(
        base_bot_keypair, trade_bot_address, lamports_to_transfer
    )
    logging.info(
        f"Transferred {lamports_to_transfer} lamports from {base_bot_address} to {trade_bot_address}"
    )
    logging.info(f"Signature: {signature}")

    # Wait for wallet to change state:
    logging.info("Waiting for Wallet to change state:")
    previous_lamports = convert_to_base_unit(SOL, amount=base_wallet_sol)
    await wait_for_sol_diff(
        address=base_bot_address, prev_lamports=previous_lamports, timeout=30
    )

    # ==========================================
    # 2: EXECUTE SWAP STRATEGY:
    # ==========================================
    await run_strategy(token_address, exit_rules)

    logging.info("STRATEGY COMPLETE!!")


if __name__ == "__main__":
    asyncio.run(main())
