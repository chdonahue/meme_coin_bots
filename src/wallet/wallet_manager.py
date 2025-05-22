# src/wallet/wallet_manager.py

from src.wallet.wallet import WalletType, get_wallet_address, get_wallet_keypair
from src.wallet.wallet_factory import WalletFactory
from src.blockchain import get_wallet_contents, transfer_sol, wait_for_sol_diff
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
