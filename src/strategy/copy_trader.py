import logging
from datetime import datetime, UTC
import asyncio
from typing import Union, List
from abc import ABC
from src.listeners.wallet_listener import WalletListener
from src.wallet.wallet_manager import WalletManager
from src.wallet.wallet import get_total_wallet_value
from src.blockchain import get_wallet_contents, retry_swap_tokens
from src.transaction_parser import get_transaction_json, classify_transaction
from src.token_addresses import SOL


class CopyTraderBase(ABC):
    def __init__(
        self,
        target_wallets: Union[str, List[str]],
        bot_wallet: WalletManager,
    ):
        """
        Base class for the copy trading bot.

        Args:
            target_wallets (list or str): Wallets to copy (will aggregate them all and treat as one entity)
            bot_wallet (WalletManager): Bot to use for copy trading
        """
        self.target_wallets = target_wallets
        self.bot_wallet = bot_wallet
        self.listener = WalletListener(
            target_wallets, subscription_types=["logsSubscribe"]
        )  # logsSubscribe only for now

    async def start_listener(self):
        logging.info("[*] Initializing wallet listener...")
        await self.listener.connect()

    async def run(self):
        async for signature in self.listener.listen_signatures():
            await self.handle_signature(signature)

    async def handle_signature(self, signature):
        try:
            logging.info(f"[+] Received signature: {signature}")
            tx_json = await get_transaction_json(signature)

            tx_type = classify_transaction(tx_json)
            logging.info(f"[~] Classified transaction as: {tx_type}")

            if tx_type == "token_swap":
                await self.process_swap(tx_json)
            elif tx_type == "transfer":
                await self.process_transfer(tx_json)
            elif tx_type == "token_mint":
                await self.process_mint(tx_json)
            else:
                logging.info("Type of transaction unknown!")

        except Exception as e:
            logging.error(f"[!] Error processing signature {signature}: {e}")

    async def process_swap(self, tx_json):
        pass

    async def process_transfer(self, tx_json):
        pass

    async def process_mint(self, tx_json):
        pass


class CopyTradeExecutor:
    """
    Given a whale wallet and a bot wallet, this will track wallet states and the relative SOL value ratio between wallets
    It will execute swaps if one passes an input token, output token and whale input amount

    Args:
        whale_wallet_address (str): Address of the whale
        bot_wallet (WalletManager): The WalletManager object for the bot
        refresh_interval_sec (int): Number of seconds to wait between updating total value state (this is a bit slow)
        slippage_bps (int): Slippage to use for the swap
        prioritization_fee (int): Prioritization fee (lamports)
        simulation_mode (bool): Will run fake trades for testing if set to True
    """

    def __init__(
        self,
        whale_wallet_address: str,
        bot_wallet: WalletManager,
        refresh_interval_sec: int = 3600 * 24,
        slippage_bps: int = 300,
        prioritization_fee: int = 100000,
        simulation_mode: bool = False,
    ):
        self.whale_wallet_address = whale_wallet_address
        self.bot_wallet = bot_wallet
        self.refresh_interval_sec = refresh_interval_sec  # default to 1/day
        self.slippage_bps = slippage_bps
        self.prioritization_fee = prioritization_fee
        self.simulation_mode = simulation_mode
        self.scaling_factor = None
        self.last_scaling_time = None
        self._refresh_task = None

    async def initialize(self):
        """
        User needs to initalize wallet content state and scaling factor refresh loop
        """
        self.whale_contents = await get_wallet_contents(self.whale_wallet_address)
        self.bot_contents = await get_wallet_contents(self.bot_wallet.address)
        if self._refresh_task is None:
            self._refresh_task = asyncio.create_task(self._scaling_refresh_loop())
        if self.simulation_mode:
            logging.info(
                f"Running Copy Executor IN SIMULATION MODE. Tracking {self.whale_wallet_address}"
            )
        else:
            logging.info(
                f"Running Copy Executor in REAL MODE. Tracking {self.whale_wallet_address} with bot {self.bot_wallet.address}"
            )

    async def execute_swap(self, input_mint, output_mint, whale_input_amount):
        """
        Handles swap execution. Given an input_mint, output_mint, and the whale's input amount, executes the swap

        Args:
            input_mint (str): Input token address
            output_mint (str): Output token address
            whale_input_amount (int): Amount of input_mint to swap in base units
        """

        if self.scaling_factor is None:
            logging.warning(
                "[SWAP] Scaling factor is not initialized yet. Skipping trade."
            )
            return
        # If swapping from SOL to another token:
        if input_mint == SOL:
            bot_input_amount = self.scaling_factor * whale_input_amount
            if bot_input_amount > self.bot_contents.get(SOL, 0):
                logging.warning(
                    f"Swap amount {bot_input_amount} exceeds wallet contents {self.bot_contents.get(SOL, 0)}"
                )
                return
        else:
            whale_balance = self.whale_contents.get(input_mint)
            bot_balance = self.bot_contents.get(input_mint)

            if whale_balance is None:
                logging.warning(
                    f"[SWAP] Whale does not hold token {input_mint}. Skipping."
                )
                return

            if bot_balance is None or bot_balance <= 0:
                logging.warning(
                    f"[SWAP] Bot does not hold token {input_mint}. Skipping."
                )
                return

            if whale_balance <= 0:
                logging.warning(
                    f"[SWAP] Whale balance for {input_mint} is zero. Skipping."
                )
                return
            trade_fraction = min(
                whale_input_amount / self.whale_contents[input_mint], 1
            )  # fraction of whale's tokens to swap
            bot_input_amount = trade_fraction * self.bot_contents.get(input_mint, 0)

        if self.simulation_mode:
            logging.info(
                f"Simulating swap from {input_mint} to {output_mint}. {bot_input_amount} swapped!"
            )
            return

        # Execute swap:
        tx_dict = await retry_swap_tokens(
            input_mint=input_mint,
            output_mint=output_mint,
            amount=bot_input_amount,
            wallet_keypair=self.bot_wallet.keypair,
            slippage_bps=self.slippage_bps,
            prioritization_fee=self.prioritization_fee,
            max_retries=5,
            retry_delay=5.0,
        )
        logging.info(
            f"Swapped from {input_mint} to {output_mint}. {bot_input_amount} swapped! Signature: {tx_dict["signature"]}"
        )
        # Update state:
        self.whale_contents = await get_wallet_contents(self.whale_wallet_address)
        self.bot_contents = await get_wallet_contents(self.bot_wallet.address)

    async def _scaling_refresh_loop(self):
        while True:
            logging.info("Calculating Wallet Scaling factor...")
            try:
                whale_value = await get_total_wallet_value(
                    self.whale_wallet_address
                )  # (in lamports)
                my_value = await self.bot_wallet.get_total_value()

                if whale_value <= 0:
                    self.scaling_factor = 0.0
                    logging.warning("[SCALING] Whale wallet value = 0")
                else:
                    self.scaling_factor = min(
                        my_value / whale_value, 1
                    )  # we'll assume bot value is always smaller than the whale's
                    logging.info(
                        f"[SCALING] Refreshed scaling factor: {self.scaling_factor:.5f}"
                    )

                self.last_scaling_time = datetime.now(UTC).isoformat()
            except Exception as e:
                logging.error(f"[SCALING] Failed to refresh scaling factor: {e}")

            await asyncio.sleep(self.refresh_interval_sec)
