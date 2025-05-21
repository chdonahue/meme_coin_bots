"""
Contains the wallet listening infrastructure that uses quicknode websocket connection
"""

import json
import time
import os
import asyncio
import websockets
import logging
import aiohttp
from typing import Union
from dotenv import load_dotenv

load_dotenv()


class WalletListener:
    """
    Class to use websockets to list to changes in accounts.
    Args:
        wallets (list): A list of wallets to track
        subscription_types (list): Right now supports logsSubscribe (can see SOL and account balance changes) and accountSubscribe (can be used to see SPL changes, but not tested yet)
    """

    def __init__(
        self,
        wallets: Union[str, list[str]],
        subscription_types: list[str] = ["logsSubscribe"],
    ):
        if isinstance(wallets, str):
            self.wallets = [wallets]
        else:
            self.wallets = wallets

        self.subscription_types = subscription_types
        self.uri = os.getenv("QUICKNODE_SOLANA_WEBSOCKET")
        self.queues = {wallet: asyncio.Queue() for wallet in self.wallets}
        self.last_seen_signature = {
            wallet: None for wallet in self.wallets
        }  # to fill in signatures if we get disconnected
        self.backfill_enabled = {
            wallet: False for wallet in self.wallets
        }  # flag to not backfill upon initialization
        self.tasks = []

    async def _subscribe(self, wallet: str, method: str, params: dict):
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.uri) as ws:
                    sub_req = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                        "params": [params, {"commitment": "finalized"}],
                    }
                    await ws.send(json.dumps(sub_req))
                    logging.info(f"✅ Subscribed ({method}) to wallet: {wallet}")

                    # Only backfill if this wallet has already seen at least one live signature
                    if self.backfill_enabled[wallet]:
                        await self.catch_up_missed_sigs(wallet)

                    # Reset backoff timer on success
                    backoff = 1
                    while True:
                        try:
                            response = await asyncio.wait_for(
                                ws.recv(), timeout=120
                            )  # Reconnect if not getting a connection
                        except asyncio.TimeoutError:
                            logging.warning(
                                f"🕒 WebSocket recv() timeout for {wallet}, reconnecting..."
                            )
                            break  # exit to reconnect
                        logging.debug(
                            f"[{wallet}] Received raw ws message: {response[:100]}"
                        )
                        data = json.loads(response)

                        if "params" not in data:
                            continue

                        result = data["params"]["result"]["value"]

                        if method == "logsSubscribe":
                            sig = result.get("signature")
                            if (
                                sig
                                == "1111111111111111111111111111111111111111111111111111111111111111"
                            ):
                                logging.debug(
                                    f"⚠️ Ignoring fake/system signature: {sig}"
                                )  # this is a solana edge case
                                continue
                            self.last_seen_signature[wallet] = sig
                            await self.queues[wallet].put(sig)

                            # Once we’ve seen a real-time sig, enable backfill for future reconnects
                            if not self.backfill_enabled[wallet]:
                                self.backfill_enabled[wallet] = True
                                logging.info(
                                    f"✅ Enabled backfill for {wallet} after receiving first live sig"
                                )

                        elif method == "accountSubscribe":
                            sig = (
                                f"balance-change:{wallet}:{result.get('lamports', '0')}"
                            )
                            await self.queues[wallet].put(sig)

            except Exception as e:
                logging.warning(f"⚠️ WebSocket error ({method}) for {wallet}: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)  # Exponential backoff up to 30s

    async def connect(self):
        # Initialize last_seen_signature to avoid old backfills
        for wallet in self.wallets:
            await self.initialize_last_seen_signature(wallet)

        for wallet in self.wallets:
            for method in self.subscription_types:
                params = {"mentions": [wallet]} if method == "logsSubscribe" else wallet
                self.tasks.append(
                    asyncio.create_task(self._subscribe(wallet, method, params))
                )

    async def add_wallet(self, wallet: str):
        if wallet in self.wallets:
            logging.info(f"ℹ️ Already tracking wallet: {wallet}")
            return

        self.wallets.append(wallet)
        self.queues[wallet] = asyncio.Queue()

        for method in self.subscription_types:
            params = {"mentions": [wallet]} if method == "logsSubscribe" else wallet
            self.tasks.append(
                asyncio.create_task(self._subscribe(wallet, method, params))
            )

        logging.info(f"➕ Now listening to new wallet: {wallet}")

    async def listen_signatures(self):
        last_heartbeat = time.time()
        heartbeat_interval = 60  # in seconds

        while True:
            try:
                for wallet, queue in self.queues.items():
                    if not queue.empty():
                        yield await queue.get()

                # Log heartbeat every `heartbeat_interval` seconds
                if time.time() - last_heartbeat > heartbeat_interval:
                    logging.info(
                        "💓 Listener heartbeat: still alive and checking queues..."
                    )
                    last_heartbeat = time.time()

                await asyncio.sleep(0.05)
            except Exception as e:
                logging.error(f"🔥 Signature listener crashed: {e}")
                await asyncio.sleep(1)

    async def get_token_accounts(self, wallet: str) -> list[str]:
        url = self.uri.replace("wss://", "https://")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"},
            ],
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    return [entry["pubkey"] for entry in data["result"]["value"]]
        except Exception as e:
            logging.error(f"[{wallet}] Failed to fetch token accounts: {e}")
            return []

    async def initialize_last_seen_signature(self, wallet: str):
        """Sets the latest signature from chain to avoid backfilling old activity."""
        url = self.uri.replace("wss://", "https://")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [wallet, {"limit": 1}],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    sigs = data.get("result", [])
                    if sigs:
                        self.last_seen_signature[wallet] = sigs[0]["signature"]
                        logging.info(
                            f"🧭 Initialized last_seen_signature for {wallet}: {sigs[0]['signature']}"
                        )
        except Exception as e:
            logging.error(f"[{wallet}] Failed to fetch initial signature: {e}")

    async def catch_up_missed_sigs(self, wallet: str):
        last_sig = self.last_seen_signature.get(wallet)
        if not last_sig:
            logging.info(f"🛑 No last_seen_signature for {wallet}, skipping backfill")
            return

        url = self.uri.replace("wss://", "https://")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [wallet, {"limit": 20}],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    sigs = data.get("result", [])

                    # If we can't find last_seen_signature, skip to avoid reprocessing
                    seen = [entry["signature"] for entry in sigs]
                    if seen and last_sig not in seen:
                        logging.warning(
                            f"[{wallet}] ❌ last_seen_signature {last_sig} not found. Skipping catch-up to avoid duplication."
                        )
                        return

                    # Add only newer signatures
                    new_sigs = []
                    for entry in sigs:
                        sig = entry["signature"]
                        if sig == last_sig:
                            break  # stop at known sig
                        new_sigs.append(sig)

                    # Oldest → newest
                    for sig in reversed(new_sigs):
                        logging.info(f"[{wallet}] Catch-up sig: {sig}")
                        await self.queues[wallet].put(sig)

        except Exception as e:
            logging.error(f"[{wallet}] Failed to backfill missed sigs: {e}")

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logging.info("🛑 Closed all wallet listeners.")
