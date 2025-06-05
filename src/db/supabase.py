import asyncpg
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


async def get_supabase_pool():
    return await asyncpg.create_pool(
        dsn=os.getenv("SUPABASE_URL"),  # Put full connection string here
        min_size=1,
        max_size=5,
    )


async def save_quote_to_supabase(data: dict, pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO quotes (
                timestamp, input_mint, output_mint,
                input_amount, output_amount, price_impact_pct
            ) VALUES ($1, $2, $3, $4, $5, $6)
        """,
            data["timestamp"],
            data["input_mint"],
            data["output_mint"],
            data["input_amount"],
            data["output_amount"],
            data.get("price_impact_pct"),
        )


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
