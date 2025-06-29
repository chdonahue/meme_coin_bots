"""
Fetches images from supabase tables
"""

import os
import aiohttp
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

OUTPUT_DIR = "data/token_images"
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def fetch_and_save_images():
    """
    Fetch token image URLs from Supabase and save images locally. Saves to data/token_images
    """
    url = f"{SUPABASE_URL}/rest/v1/token_metadata"
    params = {"select": "mint,image_link"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS, params=params) as response:
            if response.status != 200:
                logging.warning(f"Failed to fetch image URLs: {response.status}")
                return

            data = await response.json()

            tasks = []
            for item in data:
                token_id = item["mint"]
                image_url = item["image_link"]
                tasks.append(download_image(session, token_id, image_url))

            await asyncio.gather(*tasks)


async def download_image(session, token_id, url):
    """
    Download a single image and save to OUTPUT_DIR
    """

    # Do not download if already exists:
    file_path = os.path.join(OUTPUT_DIR, f"{token_id}.png")
    if os.path.exists(file_path):
        logging.info(f"📝 Skipping {file_path} (already exists)")
        return

    try:
        async with session.get(url, timeout=10) as r:
            if r.status == 200:
                content = await r.read()
                file_path = os.path.join(OUTPUT_DIR, f"{token_id}.png")
                with open(file_path, "wb") as f:
                    f.write(content)
                logging.info(f"✅ Saved {file_path}")
            else:
                logging.warning(f"Failed to download {url}: {r.status}")
    except Exception as e:
        logging.warning(f"Error downloading {url}: {e}")


if __name__ == "__main__":
    asyncio.run(fetch_and_save_images())
