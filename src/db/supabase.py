import asyncpg
import os
import pandas as pd
from dotenv import load_dotenv
import aiohttp

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
                    print(f"Successfully saved quote data to Supabase")
                    return response
                else:
                    response_text = await response.text()
                    print(
                        f"Error saving to Supabase: {response.status} - {response_text}"
                    )
                    return None

    except Exception as e:
        print(f"Exception saving to Supabase: {e}")
        return None


async def save_token_metadata_to_supabase(data: dict):
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
                    print(f"✅ Saved metadata for {mint}")
                    return response
                else:
                    response_text = await response.text()
                    print(f"[!] Supabase error: {response.status} - {response_text}")
                    return None
    except Exception as e:
        print(f"[!] Exception saving metadata: {e}")
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


async def load_quotes_from_supabase() -> pd.DataFrame:
    """
    Connects to Supabase via REST API and loads the entire quotes table as a Pandas DataFrame.
    """
    # Replace 'quotes' with your actual table name if different
    table_name = "quotes"

    # Supabase REST API endpoint for your table
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table_name}"

    # Add query parameters for ordering
    params = {
        "order": "timestamp.asc",  # Order by timestamp ascending
        "select": "*",  # Select all columns
    }

    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:

                if response.status == 200:
                    # Get JSON data
                    data = await response.json()

                    # Convert to DataFrame
                    df = pd.DataFrame(data)

                    # Optional: parse timestamps if needed
                    if "timestamp" in df.columns and not df.empty:
                        df["timestamp"] = pd.to_datetime(df["timestamp"])

                    print(f"✅ Loaded {len(df)} rows from Supabase")
                    return df

                else:
                    response_text = await response.text()
                    print(
                        f"❌ Error loading from Supabase: {response.status} - {response_text}"
                    )
                    return pd.DataFrame()  # Return empty DataFrame on error

    except Exception as e:
        print(f"❌ Exception loading from Supabase: {e}")
        import traceback

        traceback.print_exc()
        return pd.DataFrame()  # Return empty DataFrame on error
