"""Token symbol to mint address mapping."""

# Solana token mint addresses
TOKEN_MINTS: dict[str, str] = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
}


def get_mint_address(symbol: str) -> str | None:
    """
    Get mint address for a token symbol.

    Args:
        symbol: Token symbol (e.g., "SOL", "USDC")

    Returns:
        Mint address string or None if not found
    """
    return TOKEN_MINTS.get(symbol.upper())
