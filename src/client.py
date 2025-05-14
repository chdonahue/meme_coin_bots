"""
This module holds tools for interfacing with clients that interact
with the Solana blockchain.
"""

import os
from dotenv import load_dotenv
from solana.rpc.api import Client


def get_helius_client() -> Client:
    """
    Returns a Solana RPC client connected to the Helius API.
    """
    helius_url = get_helius_url()
    return Client(helius_url)


def get_helius_url() -> str:
    """
    Returns the Helius API URL with the API key from the environment.
    """
    load_dotenv()
    api_key = os.getenv("HELIUS_API_KEY")
    if not api_key:
        raise EnvironmentError("HELIUS_API_KEY is not set in .env")
    helius_url = f"https://rpc.helius.xyz/?api-key={api_key}"
    return helius_url
