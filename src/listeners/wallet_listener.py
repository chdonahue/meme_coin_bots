"""
Will have the infrastructure used for copy trading
"""
import json
import os
import asyncio
import websockets
import logging
from dotenv import load_dotenv

load_dotenv()

class WalletListener:
    def __init__(self, wallet: str, max_retries: int = 10):
        """
        Args:
            wallet (str): Wallet Address to Listen to
            max_retries (int): The number of times to try to reestablish a connection if we get dropped
        """
        self.wallet = wallet
        self.uri = os.getenv("QUICKNODE_SOLANA_WEBSOCKET")
        self.ws = None
        self.running = False
        self.max_retries = max_retries
        self.retries = 0

    async def connect(self):
        try:
            self.ws = await websockets.connect(self.uri)
            sub_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [self.wallet]},
                    {"commitment": "finalized"}
                ]
            }
            await self.ws.send(json.dumps(sub_req))
            self.running = True
            self.retries = 0
            logging.info(f"✅ Subscribed to logs for wallet: {self.wallet}")
        except Exception as e:
            self.running = False
            logging.info(f"❌ Failed to connect: {e}")

    async def reconnect(self, backoff=5):
        if self.retries >= self.max_retries:
            logging.info("🛑 Max retries exceeded. Stopping listener.")
            self.running = False
            return
        logging.info(f"🔁 Attempting reconnect in {backoff} seconds... (retry {self.retries+1}/{self.max_retries})")
        await asyncio.sleep(backoff)
        self.retries += 1
        await self.connect()

    async def listen_signatures(self):
        """Yield transaction signatures in real time, with reconnection."""
        while True:
            if not self.running:
                await self.reconnect()
                if not self.running:
                    break  # give up

            try:
                response = await self.ws.recv()
                data = json.loads(response)

                if "result" in data:
                    continue

                sig = data["params"]["result"]["value"]["signature"]
                yield sig

            except websockets.exceptions.ConnectionClosed:
                logging.info("⚠️ WebSocket closed unexpectedly.")
                self.running = False
            except Exception as e:
                logging.info(f"❌ Listener error: {e}")
                self.running = False

    async def close(self):
        self.running = False
        if self.ws:
            await self.ws.close()
            logging.info("webSocket connection closed")
