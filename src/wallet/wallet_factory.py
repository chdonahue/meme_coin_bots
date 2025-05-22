# src/wallet/wallet_factory.py

import os
from base58 import b58decode
from dotenv import load_dotenv
from solders.keypair import Keypair
from src.wallet.wallet import WalletType, get_wallet_address, get_wallet_keypair

load_dotenv()


class WalletFactory:
    @staticmethod
    def create_wallet(wallet_type: WalletType, **kwargs):
        if wallet_type == WalletType.TEST:
            return WalletFactory._create_static_wallet()
        elif wallet_type == WalletType.BOT:
            return WalletFactory._create_derived_wallet(
                kwargs["mnemonic"], kwargs["wallet_idx"]
            )
        else:
            raise ValueError("Unsupported wallet type")

    @staticmethod
    def _create_static_wallet():
        secret = os.getenv("SOLANA_PRIVATE_KEY")
        pub = os.getenv("SOLANA_PUBLIC_KEY")
        if not secret or not pub:
            raise ValueError("Missing SOLANA_PRIVATE_KEY or SOLANA_PUBLIC_KEY in env")
        return {"address": pub, "keypair": Keypair.from_seed(b58decode(secret))}

    @staticmethod
    def _create_derived_wallet(mnemonic: str, wallet_idx: int):
        address = get_wallet_address(WalletType.BOT, mnemonic, wallet_idx)
        keypair = get_wallet_keypair(WalletType.BOT, mnemonic, wallet_idx)
        return {"address": address, "keypair": keypair}
