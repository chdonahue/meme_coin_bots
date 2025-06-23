import sqlite3
import aiosqlite
import pandas as pd


def init_local_db(db_path="quotes.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            input_mint TEXT NOT NULL,
            output_mint TEXT NOT NULL,
            input_amount INTEGER NOT NULL,
            output_amount INTEGER NOT NULL,
            price_impact_pct FLOAT NOT NULL
        );
    """
    )
    conn.commit()
    conn.close()


async def save_quote_to_sqlite(data: dict, db_path="quotes.db"):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO quotes (timestamp, input_mint, output_mint, input_amount, output_amount, price_impact_pct)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                data["timestamp"],
                data["input_mint"],
                data["output_mint"],
                data.get("input_amount", 0),
                data["output_amount"],
                data.get("price_impact_pct", 0.0),
            ),
        )
        await db.commit()


def load_quotes_from_sqlite(db_path="quotes.db") -> pd.DataFrame:
    """
    Loads all quote records from the local SQLite database into a Pandas DataFrame.
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM quotes", conn)
    conn.close()
    return df
