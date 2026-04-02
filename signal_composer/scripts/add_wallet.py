"""Add a trading wallet for the current user.

Usage: python scripts/add_wallet.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from base58 import b58decode
from solders.keypair import Keypair

from src.db.connection import get_session
from src.db.repositories import WalletRepository, UserRepository


async def main():
    print("=" * 60)
    print("ADD TRADING WALLET")
    print("=" * 60)

    # Get private key
    private_key = input("\nEnter private key (base58): ").strip()
    if not private_key:
        print("No key provided.")
        return

    # Validate key and derive address
    try:
        key_bytes = b58decode(private_key)
        if len(key_bytes) == 32:
            keypair = Keypair.from_seed(key_bytes)
        elif len(key_bytes) == 64:
            keypair = Keypair.from_bytes(key_bytes)
        else:
            print(f"Invalid key length: {len(key_bytes)} bytes")
            return
        address = str(keypair.pubkey())
    except Exception as e:
        print(f"Invalid key: {e}")
        return

    print(f"\nDerived address: {address}")

    # Get optional label
    label = input("Label (optional): ").strip() or None

    # Get user (for MVP, assume user_id=1 or create if needed)
    async with get_session() as session:
        user_repo = UserRepository(session)
        wallet_repo = WalletRepository(session)

        # Check if wallet already exists
        existing = await wallet_repo.get_by_address(address)
        if existing:
            print(f"\nWallet already exists (id={existing.id})")
            return

        # Get or create user (MVP: use first user or wallet address as identifier)
        users = await user_repo.list_all()
        if users:
            user = users[0]
            print(f"\nUsing existing user: {user.wallet_address}")
        else:
            print("\nNo users found. Create one first via /auth/challenge + /auth/verify")
            return

        # Create wallet
        wallet = await wallet_repo.create(
            user_id=user.id,
            address=address,
            private_key_b58=private_key,
            label=label,
        )

        print(f"\nWallet created!")
        print(f"  ID: {wallet.id}")
        print(f"  Address: {wallet.address}")
        print(f"  Label: {wallet.label or '(none)'}")


if __name__ == "__main__":
    asyncio.run(main())
