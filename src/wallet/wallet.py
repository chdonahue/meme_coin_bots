"""
Utility functions to work with wallets
"""

from dotenv import load_dotenv
import os
import asyncio
import logging
from bip_utils import (
    Bip39SeedGenerator,
    Bip44,
    Bip44Coins,
    Bip44Changes,
    Bip39MnemonicGenerator,
)
from solders.keypair import Keypair
from base58 import b58decode, b58encode
from nacl.signing import SigningKey

from enum import Enum, auto
from src.blockchain import get_wallet_contents  # TODO: move to this module
from src.token_addresses import SOL
from src.blockchain import get_jupiter_quote_with_backoff


class WalletType(Enum):
    """Wallet Types can be TEST or BOT"""

    TEST = auto()  # This is the TEST wallet used for bridging to hot wallets
    BOT = auto()  # This is the family of BOT wallets used for trading


def create_mnemonic_phrase():
    """Create a random 24 word mnemonic phrase"""
    return Bip39MnemonicGenerator().FromWordsNumber(24)


def generate_wallets_from_mnemonic(mnemonic, count=1, start_index=0):
    """
    Generates a deterministic family of Solana wallets from a mnemonic phrase.
    You can keep track of multiple accounts with a single phrase and index.

    Args:
        mnemonic (str): The mnemonic phrase to use
        count (int): The number of wallets to generate
        start_index (int): The starting index for the wallets
    Returns:
        wallets (list): A list of dictionaries containing the public and private keys
    """
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    wallets = []

    bip44_mst_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.SOLANA)

    for i in range(start_index, start_index + count):
        bip44_acc_ctx = bip44_mst_ctx.Purpose().Coin().Account(i)
        bip44_chg_ctx = bip44_acc_ctx.Change(Bip44Changes.CHAIN_EXT)
        bip44_addr_ctx = bip44_chg_ctx.AddressIndex(0)

        # Private key (32 bytes)
        priv_key_bytes = bip44_addr_ctx.PrivateKey().Raw().ToBytes()
        pub_key_bytes = bip44_addr_ctx.PublicKey().RawUncompressed().ToBytes()[1:]

        # Build the full 64-byte secret key (private + public)
        full_secret_key = priv_key_bytes + pub_key_bytes

        # Now make a Solana Keypair from this
        keypair = Keypair.from_bytes(full_secret_key)

        wallets.append(
            {
                "index": i,
                "public_key": str(keypair.pubkey()),
                "private_key": b58encode(keypair.secret()).decode(
                    "ascii"
                ),  # base58 encoding
            }
        )

    return wallets


def verify_solana_keypair(public_key_str, private_key_str):
    """
    Verifies that a public/private key pair is valid by:
        1. Decoding the private key
        2. Creating a keypair from the decoded private key
        3. Checking if the derived public key matches the provided public key
    """
    try:
        # Decode the private key from base58
        private_key_bytes = b58decode(private_key_str)

        if len(private_key_bytes) == 64:
            # Already a full secret key (private + public)
            full_secret_key = private_key_bytes
        elif len(private_key_bytes) == 32:
            # Only private key provided, need to derive public key
            signing_key = SigningKey(private_key_bytes)
            public_key_bytes = signing_key.verify_key.encode()
            full_secret_key = private_key_bytes + public_key_bytes
        else:
            raise ValueError(
                f"Invalid private key length: {len(private_key_bytes)} bytes (expected 32 or 64)"
            )

        # Create a keypair from the full secret key
        keypair = Keypair.from_bytes(full_secret_key)

        # Get the public key from the keypair
        derived_public_key = str(keypair.pubkey())

        # Compare the derived public key with the provided public key
        is_valid = derived_public_key == public_key_str

        return {
            "is_valid": is_valid,
            "provided_public_key": public_key_str,
            "derived_public_key": derived_public_key,
        }
    except Exception as e:
        return {"is_valid": False, "error": str(e)}


def get_wallet_keypair(
    wallet_type: WalletType, mnemonic_phrase: str = None, wallet_idx: int = None
) -> Keypair:
    """
    To avoid passing around private keys, use this function to generate the Keypair object for signing transactions.
    Args:
        wallet_type (WalletType): Can be TEST or BOT
        mnemonic_phrase (str): 24 word mnemonic phrase used to generate a family of wallets (found in .env)
        wallet_idx (int): Bot index (starts at 0)
    Returns:
        keypair (Keypair): Keypair for the wallet
    """
    load_dotenv()  # load environment variables
    if wallet_type == WalletType.TEST:
        private_key_bytes = b58decode(os.getenv("SOLANA_PRIVATE_KEY"))
        return Keypair.from_seed(private_key_bytes)
    elif wallet_type == WalletType.BOT:
        if wallet_idx is None or mnemonic_phrase is None:
            raise ValueError(
                "wallet_idx and mnemonic phrase must be provided for derived wallets."
            )
        wallet = generate_wallets_from_mnemonic(
            mnemonic_phrase, count=1, start_index=wallet_idx
        )[0]
        return Keypair.from_seed(b58decode(wallet["private_key"]))
    else:
        raise ValueError("Unsupported wallet type.")


def get_wallet_address(
    wallet_type: WalletType, mnemonic_phrase: str = None, wallet_idx: int = None
) -> str:
    """
    Returns the public key address of the wallet (str)
    Args:
        wallet_type (WalletType): Can be TEST or BOT
        mnemonic_phrase (str): 24 word mnemonic phrase used to generate a family of wallets (found in .env)
        wallet_idx (int): Bot index (starts at 0)
    Returns:
        public key (str): String for the wallet's public key
    """
    load_dotenv()
    if wallet_type == WalletType.TEST:
        return os.getenv("SOLANA_PUBLIC_KEY")
    elif wallet_type == WalletType.BOT:
        if wallet_idx is None or mnemonic_phrase is None:
            raise ValueError(
                "wallet_idx and mnemonic phrase must be provided for derived wallets."
            )
        wallet = generate_wallets_from_mnemonic(
            mnemonic_phrase, count=1, start_index=wallet_idx
        )[0]
        return wallet["public_key"]
    else:
        raise ValueError("Unsupported wallet type.")


async def get_total_wallet_value(
    wallet_address: str, token_threshold: int = 100_000, max_tokens: int = 15
) -> int:
    """
    Utility function that will calculate the total value of a wallet. Sleeps for 1s between calls
    Args:
        wallet_address (str): address for the wallet
        token_threshold (int): Skips trying to find value of tokens where amount is below this theshold (to avoid too many API calls)
        max_tokens (int): Will truncate after max_tokens to save time.
    """
    contents = await get_wallet_contents(wallet_address)
    total_spl_tokens = len(contents.keys()) - 1
    if total_spl_tokens > token_threshold:
        logging.warning(
            f"Total value may be inaccurate, wallet contains {total_spl_tokens} tokens. Returning first {max_tokens}!"
        )
    total_lamports = 0
    token_count = 0
    for token in contents.keys():
        if token_count >= max_tokens:
            return total_lamports
        if token == SOL:
            total_lamports += contents.get(token, {}).get("raw_amount", 0)
        else:
            amount = contents.get(token, {}).get("raw_amount")
            if amount < token_threshold:  # skip if this looks like dust
                continue
            quote = await get_jupiter_quote_with_backoff(
                input_mint=token, output_mint=SOL, amount=amount
            )
            if quote:
                token_count += 1
                total_lamports += int(quote.get("outAmount", 0))
        await asyncio.sleep(1.0)
    return total_lamports
