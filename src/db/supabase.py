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


async def load_quotes_from_supabase(dsn: str) -> pd.DataFrame:
    """
    Connects to a Supabase PostgreSQL database and loads the entire quotes table as a Pandas DataFrame.
    """
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)

    async with pool.acquire() as conn:
        records = await conn.fetch("SELECT * FROM quotes ORDER BY timestamp ASC")

    await pool.close()

    # Convert asyncpg Record objects into a list of dictionaries
    rows = [dict(record) for record in records]

    # Convert to DataFrame
    df = pd.DataFrame(rows)

    # Optional: parse timestamps if needed
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    return df
