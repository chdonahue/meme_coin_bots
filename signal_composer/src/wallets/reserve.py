"""Reserve protection logic for trading wallets."""

from decimal import Decimal

# Minimum SOL to keep in wallet (covers rent-exempt + buffer)
RESERVE_SOL = Decimal("0.002")


def get_available_capital(on_chain_balance: Decimal) -> Decimal:
    """Calculate capital available for trading.

    Protects reserve amount from being traded away.

    Args:
        on_chain_balance: Current SOL balance from RPC

    Returns:
        Available capital (balance - reserve), minimum 0
    """
    return max(on_chain_balance - RESERVE_SOL, Decimal("0"))
