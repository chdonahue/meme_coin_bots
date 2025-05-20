import logging
from typing import Union, List
from abc import ABC, abstractmethod
from src.listeners.wallet_listener import WalletListener
from src.blockchain import get_wallet_contents, get_network_wallet_contents
from src.transaction_parser import get_transaction_json, classify_transaction


class CopyTraderBase(ABC):
    def __init__(
        self,
        target_wallets: Union[str, List[str]],
        bot_address: str,
        allocation_sol: float,
    ):
        """
        Base class for the copy trading bot.

        Args:
            target_wallets (list or str): Wallets to copy (will aggregate them all and treat as one entity)
            bot_address (str): Address of the bot to use for copy trading
            allocation_sol (float): Total amount of SOL to allocate to the strategy (this caps the maximum that the bot will use)
        """
        self.target_wallets = target_wallets
        self.bot_address = bot_address
        self.allocation_sol = allocation_sol

        self.portfolio_value = 100  # TODO: hard coding this for now
        self.target_balance = {}
        self.bot_balance = {}
        self.seen_tokens = set()  # Tracks tokens that have been seen by this strategy
        self.listener = WalletListener(
            target_wallets, subscription_types=["logsSubscribe"]
        )  # logsSubscribe only for now

    async def initialize(self):
        logging.info("[*] Initializing strategy...")
        await self.listener.connect()
        self.target_balance = await get_network_wallet_contents(self.target_wallets)
        self.bot_balance = await get_wallet_contents(self.bot_address)

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
