"""
This functions to track liquidity pool data
"""

from pathlib import Path
import requests
import os
import json
import base64
from src.blockchain import get_helius_url, post_json
from solders.pubkey import Pubkey

# Raydium lists tokens in alphabetical order instead of by base priority, so this is to highlight which ones I want to be the base mint
BASE_TOKEN_PRIORITY = [
    "So11111111111111111111111111111111111111112",  # SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    # Add more base-preferred tokens here
]


def normalize_base_quote(mint_x: str, mint_y: str) -> tuple[str, str]:
    """
    Returns a tuple (base_mint, quote_mint) according to BASE_TOKEN_PRIORITY.
    """
    if mint_x == mint_y:
        raise ValueError("mint_x and mint_y must be different")

    if mint_x in BASE_TOKEN_PRIORITY and mint_y in BASE_TOKEN_PRIORITY:
        if BASE_TOKEN_PRIORITY.index(mint_x) < BASE_TOKEN_PRIORITY.index(mint_y):
            return mint_x, mint_y
        else:
            return mint_y, mint_x
    elif mint_x in BASE_TOKEN_PRIORITY:
        return mint_x, mint_y
    elif mint_y in BASE_TOKEN_PRIORITY:
        return mint_y, mint_x
    else:
        return tuple(sorted([mint_x, mint_y]))  # fallback to alphabetic order


def get_project_root(marker=".git") -> Path:
    """
    Walks up from the current directory to find the project root
    based on the presence of a marker directory (e.g., .git)

    Returns:
        Path to the root directory of the project
    Raises:
        FileNotFoundError if marker is not found
    """
    current = Path().resolve()
    for parent in [current] + list(current.parents):
        if (parent / marker).exists():
            return parent
    raise FileNotFoundError(f"Could not find project root with marker '{marker}'")


#####################################################################
# RAYDIUM POOLS:
#####################################################################
def cache_raydium_pools():
    """
    This will locally cache the Raydium pools to a json.
    It is LARGE AND SLOW. Only use if not time sensitive!
    """
    PROJECT_ROOT = get_project_root()
    url = "https://api.raydium.io/v2/sdk/liquidity/mainnet.json"
    data = requests.get(url).json()
    with open(os.path.join(PROJECT_ROOT, "data/raydium_pools.json"), "w") as f:
        json.dump(data, f)


def load_cached_pools():
    """
    This loads all the liquidity pool data from the local cache
    Returns:
        dict: The liquidity pool dictionary
    """
    PROJECT_ROOT = get_project_root()
    with open(os.path.join(PROJECT_ROOT, "data/raydium_pools.json"), "r") as f:
        return json.load(f)


def find_raydium_pool_by_mints(mint_a: str, mint_b: str) -> dict:
    """
    Finds Raydium pool data for a pair of tokens, normalizing base/quote order.
    """

    try:
        data = load_cached_pools()
    except FileNotFoundError:
        print("Could not find local cache, fetching from raydium")
        cache_raydium_pools()
        data = load_cached_pools()

    pools = data.get("official", []) + data.get("unOfficial", [])
    for pool in pools:
        pool_mints = {pool["baseMint"], pool["quoteMint"]}
        if {mint_a, mint_b}.issubset(pool_mints):
            base_mint, quote_mint = normalize_base_quote(
                pool["baseMint"], pool["quoteMint"]
            )
            return {
                "amm_id": pool["id"],
                "lp_mint": pool["lpMint"],
                "base_mint": base_mint,
                "quote_mint": quote_mint,
                "market_id": pool["marketId"],
                "version": pool.get("version", "unknown"),
            }
    return None


def get_vault_addresses(pool_address: str) -> dict:
    """
    Fetches normalized base/quote vaults and mint addresses for a Raydium pool.
    """
    helius_url = get_helius_url()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [pool_address, {"encoding": "base64"}],
    }
    data = post_json(helius_url, payload)
    account_info = data["result"]["value"]
    if not account_info:
        raise ValueError("Invalid account or missing data")
    byte_data = base64.b64decode(account_info["data"][0])

    def read_pubkey(offset: int) -> str:
        return str(Pubkey.from_bytes(byte_data[offset : offset + 32]))

    mint_a = read_pubkey(400)
    mint_b = read_pubkey(432)
    vault_a = read_pubkey(336)
    vault_b = read_pubkey(368)

    base_mint, quote_mint = normalize_base_quote(mint_a, mint_b)
    if base_mint == mint_a:
        base_vault = vault_a
        quote_vault = vault_b
    else:
        base_vault = vault_b
        quote_vault = vault_a

    return {
        "base_mint": base_mint,
        "quote_mint": quote_mint,
        "base_vault": base_vault,
        "quote_vault": quote_vault,
    }


def get_vault_balance(token_account: str) -> int:
    """
    Gets the balance of a token vault

    Args:
        token_account (str): account ID for the vault

    Returns:
        balance (int): Balance in smallest atomic unit for currency
    """
    helius_url = get_helius_url()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountBalance",
        "params": [token_account],
    }
    data = post_json(helius_url, payload)
    return int(data["result"]["value"]["amount"])


def simulate_cpmm_swap(
    x_before: float,  # amount of token you're swapping in (e.g. WSOL)
    y_before: float,  # amount of token you're swapping out (e.g. PICASSO)
    input_amount: float,  # how much you want to swap in
    fee_percent: float = 0.0025,  # Raydium usually charges ~0.25% fee
) -> dict:
    """
    Simulates a constant product (x*y=k) AMM swap. Calculates the slippage and expected price based on liquidity pool amounts
    Args:
        x_before (float): Amount of token you're swapping into
        y_before (float): Amount of token you're swapping out of
        input_amount (float): Amount of token you wish to swap
        fee_percent (float): Percentage that the market maker takes (Raydium takes 0.25%)

    Returns:
        dict: Information about the output amount and slippage
    """
    # Adjust input for fee
    net_input = input_amount * (1 - fee_percent)

    # Compute invariant
    k = x_before * y_before

    # New x after adding input
    x_after = x_before + net_input

    # Solve for new y using constant product
    y_after = k / x_after

    # Tokens received = decrease in y
    output_amount = y_before - y_after

    # Spot price before trade (y per x)
    spot_price = y_before / x_before
    # Effective price paid
    effective_price = output_amount / input_amount
    # Slippage
    slippage_pct = 100 * (1 - (effective_price / spot_price))

    return {
        "output_amount": output_amount,
        "spot_price": spot_price,
        "effective_price": effective_price,
        "slippage_percent": slippage_pct,
    }
