"""
This carries utility functions to authenticate telegram sessions.
Needed to avoid having to reauthenticate.
Since each session needs a separate .session file, this can generate unique .session files for each bot
"""

import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv

load_dotenv()


async def authenticate_telegram(session_name="test.session"):
    api_id = int(os.getenv("TELEGRAM_API_KEY") or input("Enter API ID: "))
    api_hash = os.getenv("TELEGRAM_API_HASH") or input("Enter API HASH: ")

    client = TelegramClient(session_name, api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("Enter your phone number (e.g., +123456789): ")
        await client.send_code_request(phone)
        code = input("Enter the code you received: ")

        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("Enter your 2FA password: ")
            await client.sign_in(password=password)

    if await client.is_user_authorized():
        print(f"✅ Auth successful! Session saved as {session_name}.session")
    else:
        print("❌ Authentication failed.")

    await client.disconnect()
