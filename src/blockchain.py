"""
Contains functions used for solana blockchain interactions.
"""

import requests
import asyncio
import random
import logging
from collections import OrderedDict
from typing import Dict, Tuple, List, Union
from collections import defaultdict
from base64 import b64decode
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction, VersionedTransaction
from solders.message import Message
from solana.rpc.types import TxOpts

from spl.token.constants import TOKEN_PROGRAM_ID
from solders.system_program import TransferParams, transfer
from spl.token.instructions import (
    get_associated_token_address,
    create_associated_token_account,
)
from spl.token.instructions import (
    transfer as spl_transfer,
    TransferParams as SplTransferParams,
)
from src.client import get_helius_client, get_helius_url
from src.token_addresses import SOL


def post_json(url: str, payload: dict) -> dict:
    """
    Helper to send a POST request and raise exceptions on error.
    Args:
        url (str): The URL to send the request to
        payload (dict): The JSON payload to send

    Returns:
        data (dict): The JSON response data
    """
    resp = requests.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise ValueError(data["error"].get("message", "Unknown API error"))
    return data


def convert_to_base_unit(mint_address, amount: float) -> int:
    """
    Converts a mint address canonical unit to its base unit:
    For example, 1 SOL will be converted to 1_000_000_000 LAMPORTS
    Args:
        mint_address (str): Mint address of token
        amount (float): Amount of token in canonical units

    Returns:
        int: Amount of token in base units
    """
    decimals = get_token_decimals(mint_address)
    return int(amount * (10**decimals))


def base_to_ui_unit(mint_address, amount_base: float) -> int:
    """
    Converts a mint address base unit to canonical unit :
    For example, 1 LAMPORT will be converted to 1e-9 SOL
    Args:
        mint_address (str): Mint address of token
        amount_base (int): Amount of token in canonical units

    Returns:
        int: Amount of token in base units
    """
    decimals = get_token_decimals(mint_address)
    return amount_base // (10**decimals)


async def get_sol_balance(wallet_address: str) -> int:
    """
    Get SOL balance in lamports for a wallet address.

    Args:
        wallet_address (str): The wallet address to check

    Returns:
        data (int): The SOL balance in lamports
    """
    helius_url = get_helius_url()
    payload = {
        "jsonrpc": "2.0",
        "id": "sol-balance",
        "method": "getBalance",
        "params": [wallet_address],
    }
    try:
        data = post_json(helius_url, payload)
        return data.get("result", {}).get("value", 0)
    except Exception:
        return 0


def get_token_metadata(token_address: str) -> Tuple[str, str]:
    """
    Get name and symbol for a token mint.

    Args:
        token_address (str): The token mint address

    Returns:
        meta (Tuple[str, str]): The token name and symbol
    """
    helius_url = get_helius_url()
    payload = {
        "jsonrpc": "2.0",
        "id": "meta",
        "method": "getAsset",
        "params": {"id": token_address},
    }
    try:
        data = post_json(helius_url, payload)
        meta = data.get("result", {}).get("content", {}).get("metadata", {})
        return meta.get("name", "Unknown"), meta.get("symbol", "UNKNOWN")
    except Exception:
        return "Unknown", "UNKNOWN"


def process_token(token: dict) -> dict:
    """
    Convert raw token account to detailed info with decimals and metadata.

    Args:
        token (dict): The token account data

    Returns:
        result (dict): The processed token account data
    """
    token_mint_address = token.get("mint")
    raw_amount = token.get("amount")
    try:
        decimals = get_token_decimals(token_mint_address)
        adjusted = raw_amount / (10**decimals)
        name, symbol = get_token_metadata(token_mint_address)
        return {
            "mint": token_mint_address,
            "raw_amount": raw_amount,
            "amount": adjusted,
            "decimals": decimals,
            "name": name,
            "symbol": symbol,
        }
    except Exception as e:
        return {
            "mint": token_mint_address,
            "raw_amount": raw_amount,
            "amount": None,
            "decimals": None,
            "name": "Unknown",
            "symbol": "UNKNOWN",
            "error": str(e),
        }


async def get_wallet_contents(wallet_address: str) -> OrderedDict[str, dict]:
    """
    Get a wallet's SOL and SPL token balances with metadata efficiently.
    This will create an ordered dict with SOL first and the rest of the tokens ordered by their base amount

    Args:
        wallet_address (str): Wallet address

    Returns:
        contents (dict): Dictionary of all tokens held by the wallet
    """
    helius_url = get_helius_url()

    # Step 1: Fetch token accounts (raw amounts)
    token_accounts_payload = {
        "jsonrpc": "2.0",
        "id": "get-tokens",
        "method": "getTokenAccounts",
        "params": {
            "owner": wallet_address,
            "limit": 1000,
            "displayOptions": {"showZeroBalance": False},
        },
    }
    data = post_json(helius_url, token_accounts_payload)
    token_accounts = data.get("result", {}).get("token_accounts", [])

    # Step 2: Fetch asset metadata in bulk
    assets_payload = {
        "jsonrpc": "2.0",
        "id": "meta-bulk",
        "method": "getAssetsByOwner",
        "params": {
            "ownerAddress": wallet_address,
            "page": 1,
            "limit": 1000,
        },
    }
    assets_data = post_json(helius_url, assets_payload)
    assets = assets_data.get("result", {}).get("items", [])

    # Step 3: Index by mint for fast lookup
    mint_to_meta = {
        asset.get("id"): {
            "name": asset.get("content", {}).get("metadata", {}).get("name", None),
            "symbol": asset.get("content", {}).get("metadata", {}).get("symbol", None),
            "decimals": asset.get("token_info", {}).get("decimals", None),
        }
        for asset in assets
    }

    # Step 4: Add SOL
    wallet_contents = OrderedDict()
    sol_balance = await get_sol_balance(wallet_address)
    if sol_balance > 0:
        wallet_contents[SOL] = {
            "mint": SOL,
            "raw_amount": sol_balance,
            "amount": sol_balance / 1_000_000_000,
            "decimals": 9,
            "name": "Solana",
            "symbol": "SOL",
        }

    # Step 5: Add SPL tokens using metadata
    spl_tokens = []
    for token in token_accounts:
        mint = token.get("mint")
        raw_amount = token.get("amount", 0)
        if raw_amount <= 0:
            continue
        meta = mint_to_meta.get(mint, {})
        decimals = meta.get("decimals")
        amount = raw_amount / (10**decimals) if decimals is not None else None
        spl_tokens.append(
            (
                mint,
                {
                    "mint": mint,
                    "raw_amount": raw_amount,
                    "amount": amount,
                    "decimals": decimals,
                    "name": meta.get("name", None),
                    "symbol": meta.get("symbol", None),
                },
            )
        )

    # Step 6: Sort SPL tokens and add to wallet_contents
    spl_tokens_sorted = sorted(
        spl_tokens, key=lambda item: item[1]["raw_amount"], reverse=True
    )
    wallet_contents.update(spl_tokens_sorted)

    return wallet_contents


async def get_network_wallet_contents(
    wallet_addresses: Union[str, List[str]],
) -> Dict[str, dict]:
    """
    Get combined contents of multiple wallets, merging balances of tokens with the same mint address.
    Used for tracking networks of interconnected wallets.

    Args:
        wallet_addresses (list): List of wallet addresses

    Returns:
        contents (dict): Dictionary of tokens and amounts held by the group of wallets
    """

    if isinstance(wallet_addresses, str):
        wallet_addresses = [wallet_addresses]
    combined_contents = defaultdict(
        lambda: {
            "mint": None,
            "raw_amount": 0,
            "amount": 0.0,
            "decimals": None,
            "name": None,
            "symbol": None,
        }
    )

    for address in wallet_addresses:
        wallet_data = await get_wallet_contents(address)
        for mint, token_data in wallet_data.items():
            entry = combined_contents[mint]
            entry["mint"] = mint
            entry["decimals"] = token_data.get("decimals")
            entry["name"] = token_data.get("name")
            entry["symbol"] = token_data.get("symbol")
            entry["raw_amount"] += token_data.get("raw_amount", 0)

            # Avoid double scaling if decimals is None
            if entry["decimals"] is not None:
                entry["amount"] = entry["raw_amount"] / (10 ** entry["decimals"])
            else:
                entry["amount"] = None

    return dict(combined_contents)


async def wait_for_sol_diff(
    address: str,
    prev_lamports: int,
    timeout: int = 15,
    min_change_threshold: int = 5_000_000,
):
    """
    Wait until SOL balance changes and exceeds a minimum threshold.
    This avoids reacting to transient or intermediate state changes.
    """
    for _ in range(timeout):
        contents = await get_wallet_contents(address)
        current_lamports = contents.get(SOL, {}).get("raw_amount", 0)

        # Check both: balance has changed and it's not just a dust blip
        if abs(current_lamports - prev_lamports) >= min_change_threshold:
            logging.info(
                f"[INFO] Wallet change detected in {address}: {prev_lamports} -> {current_lamports}"
            )
            return current_lamports

        await asyncio.sleep(1)

    raise TimeoutError("SOL balance did not change meaningfully in time.")


def get_token_decimals(token_address: str) -> int:
    """
    Fetches the number of decimals for a given token mint address.

    Args:
        token_address (str): The mint address of the token.

    Returns:
        int: The number of decimals for the token.
    """
    # Use the Helius API to create a client:
    client = get_helius_client()

    token_mint_pubkey = Pubkey.from_string(token_address)
    resp = client.get_account_info(token_mint_pubkey)

    if resp.value is None or resp.value.data is None:
        raise ValueError(f"Invalid mint address or no data found for {token_address}")
    decimals = resp.value.data[44]
    return decimals


################################################################################
# TRANSFER FUNCTIONS:
################################################################################


async def transfer_sol(
    sender_keypair: Keypair, recipient_address: str, amount_lamports: float
):
    """
    Transfer SOL from one account to another.

    Args:
        sender_keypair (Keypair): Sender's keypair (Solders)
        recipient_address (str): Recipient's public key
        amount_lamports (float): Amount to transfer in lamports

    Returns:
        signature (str): Transaction signature
    """
    # Use the Helius API to create a client:
    client = get_helius_client()

    # Convert address
    recipient_pubkey = Pubkey.from_string(recipient_address)

    # Create transfer instruction - using the correct parameter names
    transfer_ix = transfer(
        TransferParams(
            from_pubkey=sender_keypair.pubkey(),
            to_pubkey=recipient_pubkey,
            lamports=amount_lamports,
        )
    )

    # Fetch a recent blockhash
    blockhash_resp = client.get_latest_blockhash()
    recent_blockhash = blockhash_resp.value.blockhash

    # Build the Message
    message = Message(instructions=[transfer_ix], payer=sender_keypair.pubkey())

    # Build the Transaction
    transaction = Transaction(
        from_keypairs=[sender_keypair],
        message=message,
        recent_blockhash=recent_blockhash,
    )

    # Send the transaction
    send_resp = client.send_raw_transaction(bytes(transaction))
    signature = str(send_resp.value)

    return signature


async def transfer_spl_token(
    sender_keypair: Keypair,
    recipient_address: str,
    token_mint_address: str,
    amount: float,
):
    """
    Transfer SPL tokens from one account to another.

    Args:
        sender_keypair (Keypair): Sender's keypair (Solders)
        recipient_address (str): Recipient's public key
        token_mint_address (str): Token mint address
        amount (float): Amount to transfer in base units

    Returns:
        signature (str): Transaction signature
    """
    # Use the Helius API to create a client:
    client = get_helius_client()

    # Convert addresses
    recipient_pubkey = Pubkey.from_string(recipient_address)
    token_mint_pubkey = Pubkey.from_string(token_mint_address)

    # Get associated token addresses
    source_token_account = get_associated_token_address(
        owner=sender_keypair.pubkey(), mint=token_mint_pubkey
    )
    dest_token_account = get_associated_token_address(
        owner=recipient_pubkey, mint=token_mint_pubkey
    )

    # Prepare instructions
    instructions = []

    # Check if source token account exists
    source_account_info = client.get_account_info(source_token_account)
    source_exists = source_account_info.value is not None

    if not source_exists:
        logging.info(f"Creating associated token account for sender...")
        create_source_ata_ix = create_associated_token_account(
            payer=sender_keypair.pubkey(),
            owner=sender_keypair.pubkey(),
            mint=token_mint_pubkey,
        )
        instructions.append(create_source_ata_ix)

    # Check if destination token account exists
    dest_account_info = client.get_account_info(dest_token_account)
    destination_exists = dest_account_info.value is not None

    if not destination_exists:
        logging.info(f"Creating associated token account for recipient...")
        create_ata_ix = create_associated_token_account(
            payer=sender_keypair.pubkey(),
            owner=recipient_pubkey,
            mint=token_mint_pubkey,
        )
        instructions.append(create_ata_ix)

    # Create transfer instruction - pass parameters directly
    transfer_ix = spl_transfer(
        SplTransferParams(
            program_id=TOKEN_PROGRAM_ID,
            source=source_token_account,
            dest=dest_token_account,
            owner=sender_keypair.pubkey(),
            amount=amount,
            signers=[],  # This is required in the TransferParams
        )
    )

    instructions.append(transfer_ix)

    # Fetch a recent blockhash
    blockhash_resp = client.get_latest_blockhash()
    recent_blockhash = blockhash_resp.value.blockhash

    # Build the Message
    message = Message(instructions=instructions, payer=sender_keypair.pubkey())

    # Build the Transaction
    transaction = Transaction(
        from_keypairs=[sender_keypair],
        message=message,
        recent_blockhash=recent_blockhash,
    )

    # Send the transaction
    send_resp = client.send_raw_transaction(bytes(transaction))
    signature = str(send_resp.value)

    return signature


################################################################################
# SWAP FUNCTIONS:
################################################################################
async def get_jupiter_quote(
    input_mint: str, output_mint: str, amount: int, slippage_bps: int = 100
):
    """
    Fetches a swap quote from Jupiter.

    Args:
        input_mint (str): Mint address of the input token.
        output_mint (str): Mint address of the output token.
        amount (int): Raw amount of input token in smallest unit (e.g., lamports).
        slippage_bps (int): Max allowed slippage in basis points (default = 1%).

    Returns:
        quote (dict): Quote data with all relevant information.
    """
    url = "https://quote-api.jup.ag/v6/quote"
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": amount,
        "slippageBps": slippage_bps,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    quote = response.json()
    return quote


async def get_jupiter_quote_with_backoff(
    input_mint: str, output_mint: str, amount: int, slippage_bps: int = 100
):
    retries = 3
    for i in range(retries):
        try:
            return await get_jupiter_quote(
                input_mint, output_mint, amount, slippage_bps
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                wait_time = 2**i
                logging.info(f"[WARN] Rate limit hit. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            elif e.response.status_code == 400:  # bad quote
                logging.info("Token pair doesn't seem to be available for quote")
                return None
            else:
                raise


async def get_swap_transaction(
    quote: dict, user_keypair: Keypair, prioritization_fee=1000
) -> str:
    """
    Get transaction data from Jupiter API.

    Args:
        quote (dict): Quote data from Jupiter API.
        user_keypair (Keypair): Wallet keypair executing the transaction.
        prioritization_fee (int): Prioritization fee in lamports.

    Returns:
        Dict[str, Any]: Transaction data with serialized transaction
    """
    swap_url = "https://quote-api.jup.ag/v6/swap"

    payload = {
        "quoteResponse": quote,
        "userPublicKey": str(user_keypair.pubkey()),
        "wrapUnwrapSOL": True,
        "prioritizationFeeLamports": prioritization_fee,
    }
    transaction = post_json(swap_url, payload)
    return transaction


async def execute_transaction(serialized_tx: str, user_keypair: Keypair) -> str:
    """
    Execute a serialized Jupiter transaction with retry logic.

    Args:
        serialized_tx (str): Base64-encoded serialized transaction.
        user_keypair (Keypair): User's keypair for signing the transaction.

    Returns:
        str: Transaction signature.
    """
    client = get_helius_client()
    tx_bytes = b64decode(serialized_tx)

    # Deserialize transaction
    tx = VersionedTransaction.from_bytes(tx_bytes)

    # Create a new transaction with the message and keypair
    signed_tx = VersionedTransaction(tx.message, [user_keypair])
    tx_opts = TxOpts(skip_preflight=False, preflight_commitment="processed")

    try:
        result = client.send_raw_transaction(bytes(signed_tx), opts=tx_opts)
        signature = str(result.value)
        logging.info(f"Transaction submitted: {signature}")
        return signature
    except Exception as e:
        logging.info(f"Transaction failed: {e}")

    return None


async def verify_transaction(signature: str) -> str:
    """
    This function checks the status of a transaction on Solana using Helius API.
    Args:
        signature (str): The transaction signature to check.
    Returns:
        bool: True if the transaction is confirmed, False otherwise.
    """
    rpc_url = get_helius_url()
    try:
        response = requests.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignatureStatuses",
                "params": [[signature], {"searchTransactionHistory": True}],
            },
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 200:
            return False

        result = response.json()
        status = result.get("result", {}).get("value", [None])[0]

        return status is not None and status.get("err") is None
    except Exception:
        return False


async def swap_tokens(
    input_mint: str,
    output_mint: str,
    amount: int,
    wallet_keypair: Keypair,
    slippage_bps: int = 100,
    prioritization_fee: int = 50000,
) -> dict:
    """
    Function that performs a swap between two tokens

    Args:
        input_mint (str): input mint
        output_mint (str): output mint
        amount (int): Amount of input mint to trade (in base units)
        wallet_keypair (Keypair): Keypair of the owner's wallet
        slippage_bps (int): Slippage basis points (default is 100 (or 1%)
        prioritization_fee (int): Prioritization fee in Lamports

    Returns:
        transaction_dict (dict): Dictionary with Signature and quote
    """
    transaction_dict = {}
    try:
        quote = await get_jupiter_quote(input_mint, output_mint, amount, slippage_bps)
        tx_data = await get_swap_transaction(quote, wallet_keypair, prioritization_fee)
        serialized_tx = tx_data["swapTransaction"]
        signature = await execute_transaction(serialized_tx, wallet_keypair)
        if not signature:
            logging.info("❌ Preflight failed")
            return None
    except Exception as e:
        logging.info(f"[Error] Transaction build/execute failed: {e}")
    transaction_dict["signature"] = signature
    transaction_dict["quote"] = quote
    return transaction_dict


async def retry_swap_tokens(
    input_mint: str,
    output_mint: str,
    amount: int,
    wallet_keypair: Keypair,
    slippage_bps: int = 100,
    prioritization_fee: int = 50000,
    max_retries: int = 3,
    retry_delay: float = 2.0,
):
    """
    Wrapper to swap tokens with retry logic. Will retry token swap if a failure occurs.
    Args:
        input_mint (str): input mint
        output_mint (str): output mint
        amount (int): Amount of input mint to trade (in base units)
        wallet_keypair (Keypair): Keypair of the owner's wallet
        slippage_bps (int): Slippage basis points (default is 100 (or 1%)
        prioritization_fee (int): Prioritization fee in Lamports
        max_retries (int): Number of times to retry transaction
        retry_delay (float): Time in seconds to delay between retries

    Returns:
        transaction_dict (dict): Dictionary with Signature and quote
    """

    for i in range(max_retries):
        try:
            return await swap_tokens(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount,
                wallet_keypair=wallet_keypair,
                slippage_bps=slippage_bps,
                prioritization_fee=prioritization_fee,
            )
        except Exception as e:
            logging.info(f"[WARN] Swap failed (attempt {i+1}): {e}")
            await asyncio.sleep(retry_delay * (2**i) + random.uniform(0, 1))
            slippage_bps = int(
                slippage_bps * 1.25
            )  # optionally increase slippage each try
    raise Exception(f"Swap failed after {max_retries} attempts.")
