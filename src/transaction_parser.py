import logging
import requests
import asyncio
from typing import List, Optional, Literal, Dict, Union
from dataclasses import dataclass, field
from src.blockchain import get_helius_url
from src.token_addresses import ALL_SWAP_PROGRAMS, RAYDIUM_LP_PROGRAMS, SOL


@dataclass
class ParsedTransaction:
    """
    Data class to hold parsed transaction data
    """

    tx_type: Literal[
        "token_swap",
        "transfer",
        "token_mint",
        "token_burn",
        "add_liquidity",
        "other",
        "failed",
    ]
    signature: str
    wallet: Optional[str] = None  # wallet you're tracking
    signer: Optional[str] = None
    direction: Optional[Literal["inbound", "outbound"]] = None
    input_token: Optional[str] = None
    input_amount: Optional[int] = None
    input_ui_amount: Optional[float] = None
    output_token: Optional[str] = None
    output_amount: Optional[int] = None
    output_ui_amount: Optional[float] = None
    metadata: Dict = field(default_factory=dict)  # optional extensible field


async def get_transaction_json(signature: str, retries: int = 5, delay: float = 1.0):
    """
    Get transaction data from signature.
    Args:
        signature (str): Signature for the transaction
        retries (int): Number of times to retry the transaction
        delay (float): Delay between retry attempts

    Returns:
        tx_json (dict): A dictionary of transaction details from the signature
    """
    helius_url = get_helius_url()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
        ],
    }

    for attempt in range(retries):
        try:
            response = requests.post(helius_url, json=payload)
            response.raise_for_status()
            result = response.json().get("result")
            if result is not None:
                return result
            else:
                logging.warning(
                    f"Transaction {signature} not yet available. Retry {attempt + 1}/{retries}"
                )
        except Exception as e:
            logging.warning(
                f"Error fetching transaction {signature}: {e}. Retry {attempt + 1}/{retries}"
            )

        await asyncio.sleep(delay)

    raise ValueError(f"Transaction {signature} not available after {retries} retries")


def classify_transaction(tx_json) -> str:
    """
    Classifies a Solana transaction into types like token_swap, transfer, token_mint, etc.
    """

    # === Step 1: Quick exit for failed transactions ===
    if "meta" not in tx_json or tx_json["meta"].get("err"):
        return "failed"

    meta = tx_json["meta"]
    logs = meta.get("logMessages", [])
    inner = meta.get("innerInstructions", [])
    top_level = (
        tx_json.get("transaction", {}).get("message", {}).get("instructions", [])
    )

    # === Step 2: Collect all program IDs ===
    all_program_ids = {
        ix.get("programId")
        for ix_group in inner
        for ix in ix_group.get("instructions", [])
        if "programId" in ix
    }.union({ix.get("programId") for ix in top_level if "programId" in ix})

    # === Step 3: Match known patterns ===
    if any(pid in ALL_SWAP_PROGRAMS for pid in all_program_ids) or any(
        "Instruction: Buy" in log
        or "Instruction: Sell" in log
        or "Instruction: Route" in log
        or "swap" in log.lower()
        for log in logs
    ):
        return "token_swap"

    if any(pid in RAYDIUM_LP_PROGRAMS for pid in all_program_ids) or any(
        "Instruction: CreatePool" in log or "Instruction: AddLiquidity" in log
        for log in logs
    ):
        return "add_liquidity"

    if any("Instruction: Burn" in log for log in logs):
        return "token_burn"
    if any(
        "Instruction: InitializeMint" in log
        or "InitializeMint2" in log
        or "Instruction: MintTo" in log
        for log in logs
    ):
        return "token_mint"

    # === Step 4: Catch fallback transfers (non-SPL-token movement) ===
    pre = meta.get("preBalances", [])
    post = meta.get("postBalances", [])
    pre_tokens = meta.get("preTokenBalances", [])
    post_tokens = meta.get("postTokenBalances", [])

    if (pre != post) or (pre_tokens != post_tokens):
        return "transfer"

    # === Step 5: Default case ===
    return "other"


def parse_transaction(tx_json) -> List[ParsedTransaction]:
    """
    Given a transaction json, this parses all the transaction details. Can be used downstream
    for building flexible strategies.

    Args:
        tx_json (dict): Transaction dictionary

    Returns:
        A list of ParsedTransactions for each involved wallet in the transaction
    """

    signature = tx_json.get("transaction", {}).get("signatures", [""])[0]
    tx_type = classify_transaction(tx_json)
    meta = tx_json.get("meta", {})
    message = tx_json.get("transaction", {}).get("message", {})
    account_keys = message.get("accountKeys", [])
    signers = {
        acct["pubkey"]
        for acct in account_keys
        if isinstance(acct, dict) and acct.get("signer")
    }
    pre = meta.get("preBalances", [])
    post = meta.get("postBalances", [])
    pre_tokens = meta.get("preTokenBalances", [])
    post_tokens = meta.get("postTokenBalances", [])

    # === STEP 1: SOL TRANSFERS ===
    transfers = []
    for i, acct in enumerate(account_keys):
        if i >= len(pre) or i >= len(post):
            continue
        key = acct.get("pubkey") if isinstance(acct, dict) else acct
        delta = post[i] - pre[i]
        if delta == 0:
            continue

        direction = "inbound" if delta > 0 else "outbound"
        lamports = abs(delta)
        sol = lamports / 1e9

        transfers.append(
            ParsedTransaction(
                tx_type=tx_type,
                signature=signature,
                signer=key if key in signers else None,
                wallet=key,
                direction=direction,
                input_token=SOL if direction == "outbound" else None,
                input_amount=lamports if direction == "outbound" else None,
                input_ui_amount=sol if direction == "outbound" else None,
                output_token=SOL if direction == "inbound" else None,
                output_amount=lamports if direction == "inbound" else None,
                output_ui_amount=sol if direction == "inbound" else None,
            )
        )

    # === STEP 2: SPL TOKEN TRANSFERS ===
    token_balances = {}  # key: (wallet, mint) → {pre, post, decimals}

    for entry in pre_tokens:
        key = (entry["owner"], entry["mint"])
        token_balances[key] = {
            "pre": int(entry["uiTokenAmount"]["amount"]),
            "decimals": entry["uiTokenAmount"]["decimals"],
        }

    for entry in post_tokens:
        key = (entry["owner"], entry["mint"])
        if key not in token_balances:
            token_balances[key] = {
                "pre": 0,
                "decimals": entry["uiTokenAmount"]["decimals"],
            }
        token_balances[key]["post"] = int(entry["uiTokenAmount"]["amount"])

    for (wallet, mint), values in token_balances.items():
        pre_amt = values.get("pre", 0)
        post_amt = values.get("post", 0)
        delta = post_amt - pre_amt
        if delta == 0:
            continue

        ui_amt = abs(delta) / (10 ** values["decimals"])
        direction = "inbound" if delta > 0 else "outbound"

        transfers.append(
            ParsedTransaction(
                tx_type=tx_type,  # use consistent label unless you want "spl_transfer"
                signature=signature,
                signer=wallet if wallet in signers else None,
                wallet=wallet,
                direction=direction,
                input_token=mint if direction == "outbound" else None,
                input_amount=abs(delta) if direction == "outbound" else None,
                input_ui_amount=ui_amt if direction == "outbound" else None,
                output_token=mint if direction == "inbound" else None,
                output_amount=abs(delta) if direction == "inbound" else None,
                output_ui_amount=ui_amt if direction == "inbound" else None,
            )
        )

    return transfers


def extract_swap_data(
    parsed_txs: List[ParsedTransaction], tracked_wallets: Union[str, List[str]]
) -> Optional[Dict]:
    """
    Extracts swap data from parsed transactions for a given wallet or list of wallets.
    Handles both SOL → Token and Token → SOL directions.
    """
    if isinstance(tracked_wallets, str):
        tracked_wallets = [tracked_wallets]

    # Check if none of the txs are swaps, return early
    if not any(tx.tx_type == "token_swap" for tx in parsed_txs):
        return {}

    input_tx = None
    output_tx = None

    for tx in parsed_txs:
        if (
            tx.signer in tracked_wallets
            and tx.direction == "outbound"
            and tx.input_token is not None
        ):
            input_tx = tx

        elif (
            tx.wallet in tracked_wallets
            and tx.direction == "inbound"
            and tx.output_token is not None
        ):
            output_tx = tx

    if input_tx and output_tx:
        return {
            "input_token": input_tx.input_token,
            "input_amount": input_tx.input_amount,
            "output_token": output_tx.output_token,
            "output_amount": output_tx.output_amount,
        }

    return None


def extract_new_token_mint(tx_json: dict) -> str | None:
    """
    Extracts the newly introduced (likely LP) token from raw tx_json by comparing pre and post balances.
    Returns a mint that was either missing or had 0 balance before, but now has a positive balance.

    Args:
        tx_json (dict): transaction info

    Returns:
        str or None: Detected new token mint
    """

    pre = tx_json.get("meta", {}).get("preTokenBalances", [])
    post = tx_json.get("meta", {}).get("postTokenBalances", [])

    # Build dict: (account, mint) → pre amount
    pre_balances = {
        (p["accountIndex"], p["mint"]): int(p["uiTokenAmount"]["amount"]) for p in pre
    }

    # Candidates: tokens that had 0 or no pre balance, but now have a positive balance
    candidates = []
    for p in post:
        key = (p["accountIndex"], p["mint"])
        post_amt = int(p["uiTokenAmount"]["amount"])
        pre_amt = pre_balances.get(key, 0)

        if pre_amt == 0 and post_amt > 0 and p["mint"] != SOL:
            candidates.append((p["mint"], post_amt))

    if not candidates:
        return None

    # Return the one with the largest post amount (most likely LP token)
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]
