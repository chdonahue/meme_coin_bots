"""
Contains the wallet listening infrastructure that uses quicknode websocket connection
"""

import json
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
        max_retries (int): Number of times to retry a connection
    """

    def __init__(
        self,
        wallets: Union[str, list[str]],
        subscription_types: list[str] = ["logsSubscribe"],
        max_retries: int = 10,
    ):
        if isinstance(wallets, str):
            self.wallets = [wallets]
        else:
            self.wallets = wallets

        self.subscription_types = subscription_types
        self.uri = os.getenv("QUICKNODE_SOLANA_WEBSOCKET")
        self.max_retries = max_retries
        self.queues = {wallet: asyncio.Queue() for wallet in self.wallets}
        self.tasks = []

    async def _subscribe(self, wallet: str, method: str, params: dict):
        retries = 0
        while retries < self.max_retries:
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

                    while True:
                        response = await ws.recv()
                        data = json.loads(response)

                        if "params" not in data:
                            continue

                        result = data["params"]["result"]["value"]

                        if method == "logsSubscribe":
                            sig = result.get("signature")
                            if sig:
                                await self.queues[wallet].put(sig)

                        elif method == "accountSubscribe":
                            sig = (
                                f"balance-change:{wallet}:{result.get('lamports', '0')}"
                            )
                            await self.queues[wallet].put(sig)

            except Exception as e:
                logging.warning(f"⚠️ WebSocket error ({method}) for {wallet}: {e}")

            retries += 1
            await asyncio.sleep(min(2**retries, 30))

    async def connect(self):
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
        while True:
            for wallet, queue in self.queues.items():
                if not queue.empty():
                    yield await queue.get()
            await asyncio.sleep(0.05)

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

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logging.info("🛑 Closed all wallet listeners.")
