import logging
import requests
import asyncio
from typing import List, Optional, Literal, Dict
from dataclasses import dataclass, field
from src.blockchain import get_helius_url
from src.token_addresses import RAYDIUM_AMM_PROGRAMS


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
    Currently looks for add liquidity,
    Args:
        tx_json (dict): The transaction dictionary

    Returns:
        transaction_type (str): A string representing the type of transaction (tx_type)
    """

    if "meta" not in tx_json or tx_json["meta"].get("err"):
        return "failed"

    logs = tx_json["meta"].get("logMessages", [])
    inner = tx_json["meta"].get("innerInstructions", [])

    # Collect all program IDs used in inner instructions
    all_program_ids = {
        ix.get("programId")
        for inner_ix in inner
        for ix in inner_ix.get("instructions", [])
        if "programId" in ix
    }

    is_liquidity_add = any(
        pid in RAYDIUM_AMM_PROGRAMS for pid in all_program_ids
    ) or any("liquidity:" in log or "vault_" in log for log in logs)

    if any("Instruction: Swap" in log for log in logs):
        return "token_swap"

    if any("Instruction: Burn" in log for log in logs):
        return "token_burn"

    if is_liquidity_add:
        return "add_liquidity"

    if any(
        "Instruction: InitializeMint" in log or "InitializeMint2" in log for log in logs
    ):
        return "token_mint"

    if any("Instruction: MintTo" in log for log in logs):
        # Disqualify LP token mints
        if not is_liquidity_add:
            return "token_mint"

    # Fallback: SOL transfer if lamports moved
    pre = tx_json["meta"].get("preBalances", [])
    post = tx_json["meta"].get("postBalances", [])
    if pre != post:
        return "transfer"

    return "other"


def parse_transactions(tx_json) -> List[ParsedTransaction]:
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
                wallet=key,
                direction=direction,
                input_token="SOL" if direction == "outbound" else None,
                input_amount=lamports if direction == "outbound" else None,
                input_ui_amount=sol if direction == "outbound" else None,
                output_token="SOL" if direction == "inbound" else None,
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
