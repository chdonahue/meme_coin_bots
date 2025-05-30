import asyncio
import os
import logging
from typing import Callable, List, Optional

from telethon import TelegramClient, events
from dotenv import load_dotenv

load_dotenv()


class TelegramListener:
    def __init__(
        self,
        channels: List[str],
        on_message: Callable[[dict], None],
        session_name: str = "test",
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
    ):
        self.channels = channels
        self.on_message = on_message
        self.session_name = session_name
        self.api_id = api_id or int(os.getenv("TELEGRAM_API_KEY"))
        self.api_hash = api_hash or os.getenv("TELEGRAM_API_HASH")
        self.client = TelegramClient(session_name, self.api_id, self.api_hash)

    async def verify_channels(self):
        print("\n🔍 Verifying channels...")
        for username in self.channels:
            try:
                entity = await self.client.get_entity(username)
                title = getattr(entity, "title", None) or getattr(
                    entity, "first_name", "Unknown"
                )
                print(f"✅ Found: {username} → {title} (ID: {entity.id})")
            except Exception as e:
                print(f"❌ Could not access '{username}': {e}")

    async def start(self):
        await self.client.start()
        logging.info("Telegram client started.")

        # Verify access to channels before registering handler
        await self.verify_channels()

        @self.client.on(events.NewMessage(chats=self.channels))
        async def handler(event):
            try:
                message_data = {
                    "text": event.raw_text,
                    "chat_id": event.chat_id,
                    "sender_id": event.sender_id,
                    "timestamp": event.message.date.isoformat(),
                }
                self.on_message(message_data)
            except Exception as e:
                logging.error(f"Error in message handler: {e}")

        await self.client.run_until_disconnected()


# Example usage
if __name__ == "__main__":

    def print_message(msg):
        print(f"[{msg['timestamp']}] {msg['chat_id']}: {msg['text']}")

    listener = TelegramListener(
        channels=[
            "@degenpump_crypto_pump_signals",
            "@hitm0nkey_degen_caller",
        ],  # or channel ID
        on_message=print_message,
    )
    asyncio.run(listener.start())
