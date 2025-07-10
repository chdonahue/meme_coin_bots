import asyncio
import logging
from dotenv import load_dotenv
from src.listeners.telegram_auth import authenticate_telegram
from src.listeners.telegram_listener import TelegramListener
from src.utils.token_memory import deduplicate_token_mentions
from src.db.supabase import (
    save_mention_to_supabase,
)  # You will create this similar to save_token_metadata_to_supabase
from src.utils.logging_utils import setup_logger

# === Load env ===
load_dotenv()
SESSION_ID = "telegram_mention_logger"
CHANNELS = [
    "@zen_call",
    "@hitm0nkey_degen_caller",
    "@silvestercall",
    "@lucastradee",
    "@insider_eca",
    "@degenpumpfunsig",
]


# === Handler function to save mention ===
async def handle_new_token_mention(token: str, timestamp: str, msg: dict):
    channel_name = str(msg.get("chat_id"))
    mention_data = {
        "token_mint": token,
        "timestamp": timestamp,
        "channel_name": channel_name,
    }
    await save_mention_to_supabase(mention_data)


# === Decorated message handler ===
@deduplicate_token_mentions(handle_new_token_mention)
async def handle_message(token, timestamp, msg):
    pass  # logic handled by decorator + handler


# === Main ===
async def main():
    setup_logger(SESSION_ID)
    logging.info("Starting Telegram mention logger")

    await authenticate_telegram(SESSION_ID)

    listener = TelegramListener(
        channels=CHANNELS,
        session_name=SESSION_ID,
        on_message=handle_message,
    )

    await listener.start()


if __name__ == "__main__":
    asyncio.run(main())
