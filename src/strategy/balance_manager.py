"""
For building strategies where one must track the balance of a strategy
"""

import logging
import datetime
import asyncio
from src.wallet.wallet_manager import WalletManager
from src.wallet.wallet import get_total_wallet_value
from src.blockchain import get_wallet_contents


class PositionManager:
    """
    This uses a static strategy to manage the bot's positions. The user can define a total amount of SOL to initialize,
    the maximum number of concurrent positions, and the maximum SOL to use per position.
    It will trade this fixed amount regardless of what the copy wallet is doing.
    """

    def __init__(
        self,
        initial_sol: float = 1.0,
        max_positions: int = 10,
        max_per_position: float = 2.0,
    ):
        """
        Args:
            initial_sol (float): Amount of SOL to initialize strategy with
            max_positions (int): The maximum number of concurrent positions
            max_per_position (float): The maximum SOL to use per position
        """
        self.total_free_sol = initial_sol  # Total unheld SOL
        self.max_positions = max_positions
        self.max_per_position = max_per_position
        self.positions = (
            {}
        )  # token -> {'amount': float}  # A dictionary holding the token and amount held (in SOL)
        logging.info(
            f"Position Manager initialized with {initial_sol} SOL, {max_positions} slots, {max_per_position} SOL limit per position"
        )

    def can_trade(self):
        """
        Checks whether a trade can take place. Must:
            1. Be less than max number of positions
            2. Have funds available for strategy (with a fudge factor)
        """
        return len(self.positions) < self.max_positions and self.total_free_sol >= 0.05

    def allocate(self, token: str) -> float | None:
        """
        This tracks balances for new SOL
        Returns the allocation for the position in SOL
        NOTE: this will fail if we already have a position and the person is edging in.
        """
        if (
            token in self.positions or not self.can_trade()
        ):  # do not add if already in positions or if can't trade
            logging.info(
                f"Skipping allocation of {token} to position manager. No funds, slots, or token is already in holdings"
            )
            print(
                f"Skipping allocation of {token} to position manager. No funds, slots, or token is already in holdings"
            )
            return None
        slots_left = self.max_positions - len(self.positions)
        allocation = min(self.total_free_sol / slots_left, self.max_per_position)
        self.positions[token] = {"amount": allocation}
        self.total_free_sol -= allocation  # Update available SOL
        logging.info(f"Allocated {allocation} SOL to holdings")
        return allocation

    def release(self, token: str, new_sol_returned: float):
        if token in self.positions:
            logging.info(
                f"Releasing {token} from position Manager. Returned {new_sol_returned} SOL"
            )
            self.total_free_sol += new_sol_returned  # Move amount back to available SOL
            del self.positions[token]
        else:
            logging.info(f"Token {token} not detected in holdings. Skipping SWAP")
