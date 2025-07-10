import os
import aiohttp
import logging
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
from typing import Union

load_dotenv()


async def save_quote_to_supabase(data):
    """
    Save quote data using Supabase REST API

    Args:
        data (dict): Quote data to save
    """
    # Replace 'quotes' with your actual table name
    table_name = "quotes"  # Change this to your actual table name

    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table_name}"
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # Convert datetime to ISO string for JSON serialization
    if "timestamp" in data and hasattr(data["timestamp"], "isoformat"):
        data["timestamp"] = data["timestamp"].isoformat()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as response:

                if response.status in [200, 201]:
                    now = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                    logging.info(f"{now} Successfully saved quote data to Supabase")
                    return response
                else:
                    response_text = await response.text()
                    logging.warning(
                        f"Error saving to Supabase: {response.status} - {response_text}"
                    )
                    return None

    except Exception as e:
        logging.warning(f"Exception saving to Supabase: {e}")
        return None


async def save_token_metadata_to_supabase(data: dict):
    """
    Saves the token metadata dict from helius to the supabase schema
    """
    table_name = "token_metadata"
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table_name}"
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # Safe accessors
    creators = data.get("onChainData", {}).get("data", {}).get("creators") or []
    update_authority = data.get("onChainData", {}).get("updateAuthority")
    twitter_link = data.get("offChainData", {}).get("twitter")
    telegram_link = data.get("offChainData", {}).get("telegram")
    website_link = data.get("offChainData", {}).get("website")
    image_link = data.get("offChainData", {}).get("image")
    description = data.get("offChainData", {}).get("description")
    token_name = data.get("onChainData", {}).get("data", {}).get("name")
    token_symbol = data.get("onChainData", {}).get("data", {}).get("symbol")
    seller_fee = data.get("onChainData", {}).get("data", {}).get("sellerFeeBasisPoints")
    mint = data.get("mint")

    row = {
        "mint": mint,
        "token_name": token_name,
        "token_symbol": token_symbol,
        "update_authority": update_authority,
        "seller_fee": seller_fee,
        "creators": creators,
        "image_link": image_link,
        "description": description,
        "twitter_link": twitter_link,
        "telegram_link": telegram_link,
        "website_link": website_link,
        "metadata": data,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=row, headers=headers) as response:
                if response.status in [200, 201]:
                    logging.info(f"✅ Saved metadata for {mint}")
                    return response
                else:
                    response_text = await response.text()
                    logging.warning(
                        f"[!] Supabase error: {response.status} - {response_text}"
                    )
                    return None
    except Exception as e:
        logging.warning(f"[!] Exception saving metadata: {e}")
        return None


async def test_supabase_connection():
    """Test the Supabase REST API connection"""
    print("Testing Supabase connection...")
    print(f"SUPABASE_URL: {os.getenv('SUPABASE_URL')}")
    print(
        f"SUPABASE_KEY: {os.getenv('SUPABASE_KEY')[:20]}..."
        if os.getenv("SUPABASE_KEY")
        else "SUPABASE_KEY: Not found"
    )

    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/"
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
    }

    # Debug: Check for None values in headers
    print(f"Headers: {headers}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    print("✅ Supabase REST API connection successful!")
                    return True
                else:
                    response_text = await response.text()
                    print(
                        f"❌ Supabase connection failed: {response.status} - {response_text}"
                    )
                    return False
    except Exception as e:
        print(f"❌ Exception testing Supabase: {e}")
        import traceback

        traceback.print_exc()
        return False


async def load_quotes_from_supabase(
    token_addresses: Union[str, list[str], None] = None,
    filter_field: str = "output_mint",
) -> pd.DataFrame:
    """
    TODO: add pagination and concatenate so that df can exceed 1000 rows
    TODO: Some quotes are not being saved. Why?
    Connects to Supabase via REST API and loads the quotes table as a Pandas DataFrame.
    Optionally filters rows where filter_field is in token_addresses.

    Args:
        token_addresses: List of token mint addresses to filter by.
        filter_field: Column name to apply the filter on. Defaults to "output_mint".

    Returns:
        A Pandas DataFrame containing the filtered quotes.
    """
    if isinstance(token_addresses, str):
        token_addresses = [token_addresses]

    table_name = "quotes"
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table_name}"
    # Build query parameters
    params = {
        "order": "timestamp.asc",
        "select": "*",
    }

    if token_addresses:
        addresses_str = ",".join([addr.strip() for addr in token_addresses])
        params[f"{filter_field}"] = f"in.({addresses_str})"
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    df = pd.DataFrame(data)

                    if "timestamp" in df.columns and not df.empty:
                        df["timestamp"] = pd.to_datetime(df["timestamp"])

                    print(f"✅ Loaded {len(df)} rows from Supabase")
                    return df
                else:
                    response_text = await response.text()
                    print(
                        f"❌ Error loading from Supabase: {response.status} - {response_text}"
                    )
                    return pd.DataFrame()

    except Exception as e:
        print(f"❌ Exception loading from Supabase: {e}")
        import traceback

        traceback.print_exc()
        return pd.DataFrame()


async def load_token_metadata(
    start_timestamp: str,
    end_timestamp: str,
    page_size: int = 1000,
) -> pd.DataFrame:
    """
    TODO: check into pagination. For some reason I'm still limited at 1000.
    Loads all rows from the 'token_metadata' table where inserted_at is between start and end timestamps.
    Automatically handles pagination to retrieve all rows.

    Args:
        start_timestamp: Start of the time range (inclusive), ISO format.
        end_timestamp: End of the time range (exclusive), ISO format.
        page_size: Number of rows per page fetch (default 1000).

    Returns:
        A Pandas DataFrame containing all matching rows.
    """
    table_name = "token_metadata"
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table_name}"

    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
        "Content-Type": "application/json",
        "Range-Unit": "items",
    }

    # To collect all rows across pages
    all_rows = []
    offset = 0

    try:
        async with aiohttp.ClientSession() as session:
            while True:
                # Build params for current page and filters
                params = [
                    ("inserted_at", f"gte.{start_timestamp}"),
                    ("inserted_at", f"lt.{end_timestamp}"),
                    ("order", "inserted_at.asc"),
                    ("select", "*"),
                ]

                # Set range header for pagination
                headers["Range"] = f"{offset}-{offset + page_size - 1}"

                async with session.get(url, headers=headers, params=params) as response:
                    if response.status in [200, 206]:  # 206 = Partial Content
                        data = await response.json()
                        if not data:
                            break  # No more data returned

                        all_rows.extend(data)

                        if len(data) < page_size:
                            break  # Last page fetched

                        offset += page_size  # Increment offset for next page

                        print(
                            f"✅ Fetched {len(data)} rows (total so far: {len(all_rows)})"
                        )
                    else:
                        response_text = await response.text()
                        print(
                            f"❌ Error loading from Supabase: {response.status} - {response_text}"
                        )
                        break

        # Convert to DataFrame
        df = pd.DataFrame(all_rows)

        # Parse timestamps if relevant
        if "inserted_at" in df.columns and not df.empty:
            df["inserted_at"] = pd.to_datetime(df["inserted_at"])

        print(f"✅ Loaded {len(df)} total rows from Supabase")
        return df

    except Exception as e:
        print(f"❌ Exception loading from Supabase: {e}")
        import traceback

        traceback.print_exc()
        return pd.DataFrame()


async def save_mention_to_supabase(data: dict):
    """
    Save Telegram mention data to the telegram_mentions table in Supabase.

    Args:
        data (dict): Must include 'token_mint', 'timestamp', and 'channel_name'.
    """
    table_name = "telegram_mentions"  # Adjust if you use a different table name

    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table_name}"
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # Convert datetime to ISO string for JSON serialization
    if "timestamp" in data and hasattr(data["timestamp"], "isoformat"):
        data["timestamp"] = data["timestamp"].isoformat()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as response:
                if response.status in [200, 201]:
                    now = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                    logging.info(
                        f"{now} ✅ Successfully saved mention data to Supabase"
                    )
                    return response
                else:
                    response_text = await response.text()
                    logging.warning(
                        f"[!] Error saving mention to Supabase: {response.status} - {response_text}"
                    )
                    return None

    except Exception as e:
        logging.warning(f"[!] Exception saving mention to Supabase: {e}")
        return None
