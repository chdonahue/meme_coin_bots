"""Tests for token mapping."""

from src.data.tokens import get_mint_address


class TestGetMintAddress:
    """Test token symbol to mint address lookup."""

    def test_sol_returns_mint_address(self):
        """SOL returns correct mint address."""
        result = get_mint_address("SOL")
        assert result == "So11111111111111111111111111111111111111112"

    def test_usdc_returns_mint_address(self):
        """USDC returns correct mint address."""
        result = get_mint_address("USDC")
        assert result == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    def test_unknown_token_returns_none(self):
        """Unknown token returns None."""
        result = get_mint_address("UNKNOWN")
        assert result is None

    def test_case_insensitive(self):
        """Lookup is case-insensitive."""
        assert get_mint_address("sol") == get_mint_address("SOL")
        assert get_mint_address("Sol") == get_mint_address("SOL")
