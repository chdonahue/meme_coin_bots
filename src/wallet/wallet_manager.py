# src/wallet/wallet_manager.py

from src.wallet.wallet import WalletType, get_total_wallet_value
from src.wallet.wallet_factory import WalletFactory
from src.blockchain import (
    get_wallet_contents,
    transfer_sol,
    wait_for_sol_diff,
    get_jupiter_quote_with_backoff,
)
from src.token_addresses import SOL


class WalletManager:
    def __init__(
        self,
        wallet_type: WalletType,
        mnemonic: str = None,
        wallet_idx: int = None,
        rent_buffer: int = 5_000_000,
    ):
        wallet = WalletFactory.create_wallet(
            wallet_type, mnemonic=mnemonic, wallet_idx=wallet_idx
        )
        self.address = wallet["address"]
        self.keypair = wallet["keypair"]
        self.wallet_type = wallet_type
        self.rent_buffer = rent_buffer

    async def get_lamports(self):
        contents = await get_wallet_contents(self.address)
        return contents.get(SOL, {}).get("raw_amount", 0)

    async def transfer_to(self, target_address: str, lamports: int):
        lamports = max(lamports - self.rent_buffer, 0)
        return await transfer_sol(self.keypair, target_address, lamports)

    async def transfer_all_to(self, target_address: str):
        lamports = await self.get_lamports()
        return await self.transfer_to(target_address, lamports)

    async def wait_for_change(
        self, prev_lamports: int, timeout: int = 30, min_change_threshold=5_000_000
    ):
        """
        Waits for the wallet balance to change compared to a previous value.
        """
        return await wait_for_sol_diff(
            self.address, prev_lamports, timeout, min_change_threshold
        )

    async def get_contents(self) -> dict:
        return await get_wallet_contents(self.address)

    async def get_token_balance(self, mint: str) -> int:
        contents = await self.get_contents()
        return contents.get(mint, {}).get("raw_amount", 0)

    async def get_total_value(
        self, token_threshold: int = 100_000, max_tokens: int = 15
    ) -> int:
        """
        Get the total value of the wallet in lamports
        It uses the jupiter API to get real time quotes for each token in the wallet
        Args:
            token_threshold (int): Skips trying to find value of tokens where amount is below this theshold (to avoid too many API calls)
            max_tokens (int): Truncates search after max_tokens is reached
        """
        return await get_total_wallet_value(
            self.address, token_threshold=token_threshold, max_tokens=max_tokens
        )
