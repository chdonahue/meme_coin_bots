"""
Contains the wallet listening infrastructure that uses quicknode websocket connection
"""

import json
import os
import asyncio
import websockets
import logging
from typing import Union
from dotenv import load_dotenv

load_dotenv()


class WalletListener:
    """
    WalletListener can take a list of wallets to track and will return signatures whenever a
    finalized transaction is detected
    """

    def __init__(self, wallets: Union[str, list[str]], max_retries: int = 10):
        if isinstance(wallets, str):
            self.wallets = [wallets]
        elif isinstance(wallets, list):
            self.wallets = wallets
        else:
            raise ValueError("Wallets must be a string or a list of strings!")
        self.uri = os.getenv("QUICKNODE_SOLANA_WEBSOCKET")
        self.max_retries = max_retries
        self.queues = {wallet: asyncio.Queue() for wallet in self.wallets}
        self.tasks = []

    async def _listen_to_wallet(self, wallet: str):
        retries = 0
        while retries < self.max_retries:
            try:
                async with websockets.connect(self.uri) as ws:
                    sub_req = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "logsSubscribe",
                        "params": [{"mentions": [wallet]}, {"commitment": "finalized"}],
                    }
                    await ws.send(json.dumps(sub_req))
                    logging.info(f"✅ Subscribed to logs for wallet: {wallet}")

                    while True:
                        response = await ws.recv()
                        data = json.loads(response)

                        if not isinstance(data, dict) or "params" not in data:
                            continue

                        result = (
                            data.get("params", {}).get("result", {}).get("value", {})
                        )
                        sig = result.get("signature")
                        if sig:
                            await self.queues[wallet].put(sig)
                        else:
                            logging.debug(f"[{wallet}] Ignored message: {data}")
            except websockets.exceptions.ConnectionClosed:
                logging.warning(f"⚠️ WebSocket closed for wallet: {wallet}")
            except Exception as e:
                logging.error(f"❌ Error for wallet {wallet}: {e}")

            retries += 1
            backoff = min(2**retries, 30)
            logging.info(
                f"🔁 Reconnecting to {wallet} in {backoff}s (retry {retries}/{self.max_retries})"
            )
            await asyncio.sleep(backoff)

    async def connect(self):
        self.tasks = [
            asyncio.create_task(self._listen_to_wallet(wallet))
            for wallet in self.wallets
        ]

    async def listen_signatures(self):
        while True:
            for wallet, queue in self.queues.items():
                if not queue.empty():
                    yield await queue.get()
            await asyncio.sleep(0.05)  # prevent busy loop

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logging.info("🛑 Closed all wallet listeners.")
