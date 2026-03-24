# Simulation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add paper trading simulation with portfolio tracking, P&L calculation, performance metrics, and backtesting.

**Architecture:** Portfolio holds positions and cash balance. PaperTradeExecutor simulates fills with slippage. PerformanceCalculator computes metrics. BacktestEngine replays historical data through strategy executor.

**Tech Stack:** Python, SQLAlchemy (async), existing DSL executor from Plan 1

**Dependencies:** Plan 1 (Core Engine) must be complete.

**Required modules from Plan 1:**
- `signal_composer.src.engine.dsl.types` - Strategy, Action, ActionType, RiskRules, etc.
- `signal_composer.src.engine.dsl.parser` - parse_strategy, parse_strategy_file
- `signal_composer.src.engine.dsl.executor` - StrategyExecutor
- `signal_composer.src.engine.streams.derived` - DerivedStreamCalculator
- `signal_composer.src.db.models` - SQLAlchemy models (User, Strategy, PaperTrade, etc.)

**Working directory:** `C:\Users\donah\Desktop\projects\meme_coin_bots`

---

## File Structure

```
signal_composer/src/
├── simulation/
│   ├── __init__.py
│   ├── portfolio.py          # Portfolio state management
│   ├── executor.py           # Paper trade execution with slippage
│   ├── metrics.py            # Performance metric calculations
│   └── backtest.py           # Backtesting engine
├── db/
│   └── models.py             # Add Portfolio model (modify existing)
└── tests/
    └── simulation/
        ├── __init__.py
        ├── test_portfolio.py
        ├── test_executor.py
        ├── test_metrics.py
        └── test_backtest.py
```

---

## Task 1: Portfolio Model

**Files:**
- Create: `signal_composer/src/simulation/__init__.py`
- Create: `signal_composer/src/simulation/portfolio.py`
- Create: `signal_composer/tests/simulation/__init__.py`
- Create: `signal_composer/tests/simulation/test_portfolio.py`

- [ ] **Step 1: Write failing tests for Portfolio**

```python
# signal_composer/tests/simulation/test_portfolio.py
"""Tests for portfolio management."""
import pytest
from decimal import Decimal


class TestPortfolio:
    """Test portfolio state management."""

    def test_initial_balance(self):
        """Portfolio starts with initial cash balance."""
        from signal_composer.src.simulation.portfolio import Portfolio

        portfolio = Portfolio(initial_balance=10000.0)

        assert portfolio.cash_balance == 10000.0
        assert portfolio.positions == {}
        assert portfolio.total_value == 10000.0

    def test_buy_creates_position(self):
        """Buying creates a new position."""
        from signal_composer.src.simulation.portfolio import Portfolio

        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=150.0)

        assert "SOL" in portfolio.positions
        assert portfolio.positions["SOL"].quantity == pytest.approx(6.6666, rel=0.01)
        assert portfolio.positions["SOL"].avg_entry_price == 150.0
        assert portfolio.cash_balance == 9000.0

    def test_buy_adds_to_existing_position(self):
        """Buying more of same token updates average entry price."""
        from signal_composer.src.simulation.portfolio import Portfolio

        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=100.0)  # 10 SOL
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=200.0)  # 5 SOL

        # 15 SOL total, avg price = (1000 + 1000) / 15 = 133.33
        assert portfolio.positions["SOL"].quantity == pytest.approx(15.0, rel=0.01)
        assert portfolio.positions["SOL"].avg_entry_price == pytest.approx(133.33, rel=0.01)
        assert portfolio.cash_balance == 8000.0

    def test_sell_reduces_position(self):
        """Selling reduces position quantity."""
        from signal_composer.src.simulation.portfolio import Portfolio

        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1500.0, price=150.0)  # 10 SOL
        portfolio.execute_sell(token="SOL", quantity=5.0, price=160.0)  # Sell 5 SOL

        assert portfolio.positions["SOL"].quantity == pytest.approx(5.0)
        assert portfolio.cash_balance == pytest.approx(8500.0 + 800.0)  # 8500 + 5*160

    def test_sell_all_removes_position(self):
        """Selling all removes position from portfolio."""
        from signal_composer.src.simulation.portfolio import Portfolio

        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=100.0)  # 10 SOL
        portfolio.execute_sell_all(token="SOL", price=120.0)  # Sell all at profit

        assert "SOL" not in portfolio.positions
        assert portfolio.cash_balance == pytest.approx(9000.0 + 1200.0)  # Profit!

    def test_total_value_includes_positions(self):
        """Total value = cash + sum of position values."""
        from signal_composer.src.simulation.portfolio import Portfolio

        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=3000.0, price=150.0)  # 20 SOL

        # At current price $150: value = 7000 cash + 20*150 = 10000
        assert portfolio.total_value_at_prices({"SOL": 150.0}) == pytest.approx(10000.0)
        # Price goes up to $200: value = 7000 + 20*200 = 11000
        assert portfolio.total_value_at_prices({"SOL": 200.0}) == pytest.approx(11000.0)

    def test_unrealized_pnl(self):
        """Calculate unrealized P&L on positions."""
        from signal_composer.src.simulation.portfolio import Portfolio

        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=100.0)  # 10 SOL

        # Price up 20%
        pnl = portfolio.unrealized_pnl({"SOL": 120.0})
        assert pnl == pytest.approx(200.0)  # 10 * (120 - 100) = 200

    def test_cannot_buy_more_than_cash(self):
        """Cannot buy more than available cash."""
        from signal_composer.src.simulation.portfolio import Portfolio, InsufficientFundsError

        portfolio = Portfolio(initial_balance=1000.0)

        with pytest.raises(InsufficientFundsError):
            portfolio.execute_buy(token="SOL", amount_usd=2000.0, price=100.0)

    def test_cannot_sell_more_than_owned(self):
        """Cannot sell more than position size."""
        from signal_composer.src.simulation.portfolio import Portfolio, InsufficientPositionError

        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=100.0)  # 10 SOL

        with pytest.raises(InsufficientPositionError):
            portfolio.execute_sell(token="SOL", quantity=20.0, price=100.0)

    def test_position_pct(self):
        """Calculate what percentage of portfolio a position represents."""
        from signal_composer.src.simulation.portfolio import Portfolio

        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=4000.0, price=100.0)  # 40 SOL

        # At $100, position = 4000, total = 10000, pct = 40%
        assert portfolio.position_pct("SOL", {"SOL": 100.0}) == pytest.approx(40.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/simulation/test_portfolio.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Portfolio**

```python
# signal_composer/src/simulation/__init__.py
"""Simulation engine for paper trading."""
from .portfolio import Portfolio, Position, InsufficientFundsError, InsufficientPositionError

__all__ = ["Portfolio", "Position", "InsufficientFundsError", "InsufficientPositionError"]
```

```python
# signal_composer/src/simulation/portfolio.py
"""Portfolio management for paper trading."""
from dataclasses import dataclass, field
from typing import Dict


class InsufficientFundsError(Exception):
    """Raised when trying to buy with insufficient cash."""
    pass


class InsufficientPositionError(Exception):
    """Raised when trying to sell more than owned."""
    pass


@dataclass
class Position:
    """A token position in the portfolio."""
    token: str
    quantity: float
    avg_entry_price: float
    total_cost: float = 0.0

    def __post_init__(self):
        if self.total_cost == 0.0:
            self.total_cost = self.quantity * self.avg_entry_price

    def add(self, quantity: float, price: float) -> None:
        """Add to position, updating average entry price."""
        new_cost = quantity * price
        self.total_cost += new_cost
        self.quantity += quantity
        self.avg_entry_price = self.total_cost / self.quantity

    def remove(self, quantity: float) -> float:
        """Remove from position. Returns cost basis of removed shares."""
        if quantity > self.quantity:
            raise InsufficientPositionError(
                f"Cannot sell {quantity} {self.token}, only have {self.quantity}"
            )
        cost_basis = quantity * self.avg_entry_price
        self.quantity -= quantity
        self.total_cost -= cost_basis
        return cost_basis

    def value_at(self, price: float) -> float:
        """Current value at given price."""
        return self.quantity * price

    def unrealized_pnl_at(self, price: float) -> float:
        """Unrealized P&L at given price."""
        return self.value_at(price) - self.total_cost


@dataclass
class Portfolio:
    """Paper trading portfolio tracking positions and cash."""
    initial_balance: float
    cash_balance: float = field(init=False)
    positions: Dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0

    def __post_init__(self):
        self.cash_balance = self.initial_balance

    @property
    def total_value(self) -> float:
        """Total portfolio value at entry prices (no mark-to-market)."""
        position_value = sum(p.total_cost for p in self.positions.values())
        return self.cash_balance + position_value

    def total_value_at_prices(self, prices: Dict[str, float]) -> float:
        """Total portfolio value at current market prices."""
        position_value = sum(
            p.value_at(prices.get(p.token, p.avg_entry_price))
            for p in self.positions.values()
        )
        return self.cash_balance + position_value

    def unrealized_pnl(self, prices: Dict[str, float]) -> float:
        """Total unrealized P&L across all positions."""
        return sum(
            p.unrealized_pnl_at(prices.get(p.token, p.avg_entry_price))
            for p in self.positions.values()
        )

    def position_pct(self, token: str, prices: Dict[str, float]) -> float:
        """Percentage of portfolio in a given token."""
        if token not in self.positions:
            return 0.0
        total = self.total_value_at_prices(prices)
        if total == 0:
            return 0.0
        position_value = self.positions[token].value_at(prices[token])
        return (position_value / total) * 100

    def execute_buy(self, token: str, amount_usd: float, price: float) -> float:
        """
        Buy token with USD amount.

        Returns: quantity purchased
        Raises: InsufficientFundsError if not enough cash
        """
        if amount_usd > self.cash_balance:
            raise InsufficientFundsError(
                f"Cannot buy ${amount_usd}, only have ${self.cash_balance}"
            )

        quantity = amount_usd / price
        self.cash_balance -= amount_usd

        if token in self.positions:
            self.positions[token].add(quantity, price)
        else:
            self.positions[token] = Position(
                token=token,
                quantity=quantity,
                avg_entry_price=price,
            )

        return quantity

    def execute_sell(self, token: str, quantity: float, price: float) -> float:
        """
        Sell specific quantity of token.

        Returns: USD proceeds
        Raises: InsufficientPositionError if not enough tokens
        """
        if token not in self.positions:
            raise InsufficientPositionError(f"No position in {token}")

        position = self.positions[token]
        cost_basis = position.remove(quantity)
        proceeds = quantity * price
        self.cash_balance += proceeds
        self.realized_pnl += proceeds - cost_basis

        # Remove position if fully sold
        if position.quantity <= 0:
            del self.positions[token]

        return proceeds

    def execute_sell_all(self, token: str, price: float) -> float:
        """
        Sell entire position in token.

        Returns: USD proceeds
        """
        if token not in self.positions:
            return 0.0

        quantity = self.positions[token].quantity
        return self.execute_sell(token, quantity, price)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/simulation/test_portfolio.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal_composer/
git commit -m "feat(simulation): add portfolio management with position tracking"
```

---

## Task 2: Paper Trade Executor

**Files:**
- Create: `signal_composer/src/simulation/executor.py`
- Create: `signal_composer/tests/simulation/test_executor.py`

- [ ] **Step 1: Write failing tests for PaperTradeExecutor**

```python
# signal_composer/tests/simulation/test_executor.py
"""Tests for paper trade execution."""
import pytest
from datetime import datetime, timezone


class TestPaperTradeExecutor:
    """Test paper trade execution with slippage."""

    def test_execute_buy_action(self):
        """Execute a buy action from strategy trigger."""
        from signal_composer.src.simulation.portfolio import Portfolio
        from signal_composer.src.simulation.executor import PaperTradeExecutor
        from signal_composer.src.engine.dsl.types import Action, ActionType

        portfolio = Portfolio(initial_balance=10000.0)
        executor = PaperTradeExecutor(portfolio, slippage_bps=100)  # 1% slippage

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=10)
        prices = {"SOL": 100.0}

        trade = executor.execute(action, prices)

        assert trade is not None
        assert trade.action == "buy"
        assert trade.token == "SOL"
        assert trade.amount == pytest.approx(1000.0)  # 10% of 10000
        # Slippage: buy at worse price (higher)
        assert trade.price_at_exec == pytest.approx(101.0)  # 100 * 1.01
        assert portfolio.cash_balance < 10000.0

    def test_execute_sell_action(self):
        """Execute a sell action."""
        from signal_composer.src.simulation.portfolio import Portfolio
        from signal_composer.src.simulation.executor import PaperTradeExecutor
        from signal_composer.src.engine.dsl.types import Action, ActionType

        portfolio = Portfolio(initial_balance=10000.0)
        executor = PaperTradeExecutor(portfolio, slippage_bps=100)

        # First buy some SOL
        portfolio.execute_buy(token="SOL", amount_usd=2000.0, price=100.0)  # 20 SOL

        action = Action(type=ActionType.SELL, token="SOL", amount_pct=50)  # Sell 50% of position
        prices = {"SOL": 120.0}

        trade = executor.execute(action, prices)

        assert trade.action == "sell"
        assert trade.amount == pytest.approx(10.0)  # 50% of 20 SOL
        # Slippage: sell at worse price (lower)
        assert trade.price_at_exec == pytest.approx(118.8)  # 120 * 0.99

    def test_execute_sell_all_action(self):
        """Execute sell_all action."""
        from signal_composer.src.simulation.portfolio import Portfolio
        from signal_composer.src.simulation.executor import PaperTradeExecutor
        from signal_composer.src.engine.dsl.types import Action, ActionType

        portfolio = Portfolio(initial_balance=10000.0)
        executor = PaperTradeExecutor(portfolio, slippage_bps=50)

        portfolio.execute_buy(token="SOL", amount_usd=3000.0, price=150.0)  # 20 SOL

        action = Action(type=ActionType.SELL_ALL, token="SOL")
        prices = {"SOL": 150.0}

        trade = executor.execute(action, prices)

        assert trade.action == "sell_all"
        assert trade.amount == pytest.approx(20.0)
        assert "SOL" not in portfolio.positions

    def test_respects_max_position_pct(self):
        """Buy is capped by max_position_pct risk rule."""
        from signal_composer.src.simulation.portfolio import Portfolio
        from signal_composer.src.simulation.executor import PaperTradeExecutor
        from signal_composer.src.engine.dsl.types import Action, ActionType, RiskRules

        portfolio = Portfolio(initial_balance=10000.0)
        risk_rules = RiskRules(
            stop_loss_pct=-10,
            max_position_pct=30,  # Max 30% in any token
            max_trades_per_day=10,
            slippage_limit_bps=100,
        )
        executor = PaperTradeExecutor(portfolio, slippage_bps=100, risk_rules=risk_rules)

        # Try to buy 50% but should be capped at 30%
        action = Action(type=ActionType.BUY, token="SOL", amount_pct=50)
        prices = {"SOL": 100.0}

        trade = executor.execute(action, prices)

        # Should be capped at 30%
        assert trade.amount == pytest.approx(3000.0, rel=0.05)  # ~30% of 10000

    def test_skip_if_slippage_exceeds_limit(self):
        """Skip trade if slippage exceeds risk rule limit."""
        from signal_composer.src.simulation.portfolio import Portfolio
        from signal_composer.src.simulation.executor import PaperTradeExecutor
        from signal_composer.src.engine.dsl.types import Action, ActionType, RiskRules

        portfolio = Portfolio(initial_balance=10000.0)
        risk_rules = RiskRules(
            stop_loss_pct=-10,
            max_position_pct=50,
            max_trades_per_day=10,
            slippage_limit_bps=50,  # Max 0.5% slippage
        )
        # Executor with 2% slippage (exceeds limit)
        executor = PaperTradeExecutor(portfolio, slippage_bps=200, risk_rules=risk_rules)

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=10)
        prices = {"SOL": 100.0}

        trade = executor.execute(action, prices)

        assert trade is None  # Trade skipped

    def test_daily_trade_limit(self):
        """Respects max_trades_per_day limit."""
        from signal_composer.src.simulation.portfolio import Portfolio
        from signal_composer.src.simulation.executor import PaperTradeExecutor
        from signal_composer.src.engine.dsl.types import Action, ActionType, RiskRules

        portfolio = Portfolio(initial_balance=10000.0)
        risk_rules = RiskRules(
            stop_loss_pct=-10,
            max_position_pct=50,
            max_trades_per_day=2,  # Only 2 trades per day
            slippage_limit_bps=100,
        )
        executor = PaperTradeExecutor(portfolio, slippage_bps=50, risk_rules=risk_rules)

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=5)
        prices = {"SOL": 100.0}

        # First two trades succeed
        assert executor.execute(action, prices) is not None
        assert executor.execute(action, prices) is not None

        # Third trade is blocked
        assert executor.execute(action, prices) is None

    def test_trade_record_has_timestamp(self):
        """Trade record includes execution timestamp."""
        from signal_composer.src.simulation.portfolio import Portfolio
        from signal_composer.src.simulation.executor import PaperTradeExecutor
        from signal_composer.src.engine.dsl.types import Action, ActionType

        portfolio = Portfolio(initial_balance=10000.0)
        executor = PaperTradeExecutor(portfolio, slippage_bps=100)

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=10)
        prices = {"SOL": 100.0}

        trade = executor.execute(action, prices)

        assert trade.timestamp is not None
        assert isinstance(trade.timestamp, datetime)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/simulation/test_executor.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement PaperTradeExecutor**

```python
# signal_composer/src/simulation/executor.py
"""Paper trade execution with slippage simulation."""
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Dict, Optional
from collections import defaultdict

from ..engine.dsl.types import Action, ActionType, RiskRules
from .portfolio import Portfolio


@dataclass
class TradeRecord:
    """Record of an executed paper trade."""
    action: str  # "buy", "sell", "sell_all"
    token: str
    amount: float  # USD for buy, quantity for sell
    price_at_exec: float
    timestamp: datetime
    trigger_id: Optional[str] = None
    slippage_bps: int = 0


@dataclass
class PaperTradeExecutor:
    """
    Executes paper trades against a portfolio with slippage simulation.

    Applies risk rules to cap position sizes, limit trades per day,
    and skip trades that would exceed slippage limits.
    """
    portfolio: Portfolio
    slippage_bps: int = 100  # Default 1% slippage
    risk_rules: Optional[RiskRules] = None
    _daily_trade_counts: Dict[date, int] = field(default_factory=lambda: defaultdict(int))

    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        """Apply slippage to price. Buys get worse (higher), sells get worse (lower)."""
        slippage_multiplier = self.slippage_bps / 10000
        if is_buy:
            return price * (1 + slippage_multiplier)
        else:
            return price * (1 - slippage_multiplier)

    def _check_slippage_limit(self) -> bool:
        """Check if current slippage exceeds risk rule limit."""
        if self.risk_rules and self.slippage_bps > self.risk_rules.slippage_limit_bps:
            return False
        return True

    def _check_daily_limit(self) -> bool:
        """Check if daily trade limit has been reached."""
        if not self.risk_rules:
            return True
        today = date.today()
        return self._daily_trade_counts[today] < self.risk_rules.max_trades_per_day

    def _increment_daily_count(self) -> None:
        """Increment today's trade count."""
        today = date.today()
        self._daily_trade_counts[today] += 1

    def _calculate_buy_amount(
        self,
        action: Action,
        prices: Dict[str, float],
    ) -> float:
        """Calculate USD amount to buy, respecting position limits."""
        total_value = self.portfolio.total_value_at_prices(prices)
        target_amount = total_value * (action.amount_pct / 100)

        if not self.risk_rules:
            return min(target_amount, self.portfolio.cash_balance)

        # Check max position limit
        max_position_value = total_value * (self.risk_rules.max_position_pct / 100)
        current_position_value = 0.0
        if action.token in self.portfolio.positions:
            current_position_value = self.portfolio.positions[action.token].value_at(
                prices[action.token]
            )

        # Cap the buy to not exceed max position
        max_additional = max_position_value - current_position_value
        target_amount = min(target_amount, max_additional)

        # Also cap to available cash
        return min(target_amount, self.portfolio.cash_balance)

    def _calculate_sell_quantity(
        self,
        action: Action,
    ) -> float:
        """Calculate quantity to sell based on action."""
        if action.token not in self.portfolio.positions:
            return 0.0

        position = self.portfolio.positions[action.token]

        if action.type == ActionType.SELL_ALL:
            return position.quantity

        # Sell percentage of position
        return position.quantity * (action.amount_pct / 100)

    def execute(
        self,
        action: Action,
        prices: Dict[str, float],
        trigger_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> Optional[TradeRecord]:
        """
        Execute a paper trade based on action.

        Args:
            action: The trading action to execute
            prices: Current market prices
            trigger_id: ID of trigger that generated this action
            timestamp: Execution timestamp (defaults to now)

        Returns:
            TradeRecord if trade executed, None if skipped (risk rules)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        # Check slippage limit
        if not self._check_slippage_limit():
            return None

        # Check daily trade limit
        if not self._check_daily_limit():
            return None

        if action.token not in prices:
            return None  # Cannot trade without price

        is_buy = action.type == ActionType.BUY
        exec_price = self._apply_slippage(prices[action.token], is_buy)

        if action.type == ActionType.BUY:
            amount_usd = self._calculate_buy_amount(action, prices)
            if amount_usd <= 0:
                return None

            self.portfolio.execute_buy(action.token, amount_usd, exec_price)
            self._increment_daily_count()

            return TradeRecord(
                action="buy",
                token=action.token,
                amount=amount_usd,
                price_at_exec=exec_price,
                timestamp=timestamp,
                trigger_id=trigger_id,
                slippage_bps=self.slippage_bps,
            )

        elif action.type in (ActionType.SELL, ActionType.SELL_ALL):
            quantity = self._calculate_sell_quantity(action)
            if quantity <= 0:
                return None

            self.portfolio.execute_sell(action.token, quantity, exec_price)
            self._increment_daily_count()

            return TradeRecord(
                action="sell_all" if action.type == ActionType.SELL_ALL else "sell",
                token=action.token,
                amount=quantity,
                price_at_exec=exec_price,
                timestamp=timestamp,
                trigger_id=trigger_id,
                slippage_bps=self.slippage_bps,
            )

        return None
```

- [ ] **Step 4: Update simulation __init__.py**

```python
# signal_composer/src/simulation/__init__.py
"""Simulation engine for paper trading."""
from .portfolio import Portfolio, Position, InsufficientFundsError, InsufficientPositionError
from .executor import PaperTradeExecutor, TradeRecord

__all__ = [
    "Portfolio",
    "Position",
    "InsufficientFundsError",
    "InsufficientPositionError",
    "PaperTradeExecutor",
    "TradeRecord",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/simulation/test_executor.py -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add signal_composer/
git commit -m "feat(simulation): add paper trade executor with slippage and risk rules"
```

---

## Task 3: Performance Metrics Calculator

**Files:**
- Create: `signal_composer/src/simulation/metrics.py`
- Create: `signal_composer/tests/simulation/test_metrics.py`

- [ ] **Step 1: Write failing tests for metrics**

```python
# signal_composer/tests/simulation/test_metrics.py
"""Tests for performance metrics calculation."""
import pytest
from datetime import datetime, timezone, timedelta


class TestPerformanceMetrics:
    """Test performance metric calculations."""

    def test_total_return_pct(self):
        """Calculate total return percentage."""
        from signal_composer.src.simulation.metrics import PerformanceCalculator

        # Started with 10000, now worth 12000 = 20% return
        calc = PerformanceCalculator(initial_value=10000.0)

        assert calc.total_return_pct(current_value=12000.0) == pytest.approx(20.0)
        assert calc.total_return_pct(current_value=8000.0) == pytest.approx(-20.0)
        assert calc.total_return_pct(current_value=10000.0) == pytest.approx(0.0)

    def test_sharpe_ratio(self):
        """Calculate Sharpe ratio from daily returns."""
        from signal_composer.src.simulation.metrics import PerformanceCalculator

        calc = PerformanceCalculator(initial_value=10000.0)

        # Consistent positive returns = high Sharpe
        daily_returns = [0.01, 0.01, 0.01, 0.01, 0.01]  # 1% daily
        sharpe = calc.sharpe_ratio(daily_returns, risk_free_rate=0.0)
        assert sharpe > 2.0  # Very high Sharpe for consistent returns

        # Volatile returns = lower Sharpe
        volatile_returns = [0.05, -0.03, 0.04, -0.02, 0.01]
        sharpe_volatile = calc.sharpe_ratio(volatile_returns, risk_free_rate=0.0)
        assert sharpe_volatile < sharpe

    def test_max_drawdown(self):
        """Calculate maximum drawdown from equity curve."""
        from signal_composer.src.simulation.metrics import PerformanceCalculator

        calc = PerformanceCalculator(initial_value=10000.0)

        # Equity curve: up to 12000, down to 9000, back to 11000
        equity_curve = [10000, 11000, 12000, 10000, 9000, 10500, 11000]

        # Max drawdown: from 12000 to 9000 = -25%
        mdd = calc.max_drawdown(equity_curve)
        assert mdd == pytest.approx(-25.0)

    def test_win_rate(self):
        """Calculate win rate from trades."""
        from signal_composer.src.simulation.metrics import PerformanceCalculator
        from signal_composer.src.simulation.executor import TradeRecord

        calc = PerformanceCalculator(initial_value=10000.0)

        now = datetime.now(timezone.utc)
        trades = [
            # Buy at 100, sell at 110 = win
            TradeRecord(action="buy", token="SOL", amount=1000, price_at_exec=100, timestamp=now),
            TradeRecord(action="sell", token="SOL", amount=10, price_at_exec=110, timestamp=now),
            # Buy at 100, sell at 90 = loss
            TradeRecord(action="buy", token="SOL", amount=1000, price_at_exec=100, timestamp=now),
            TradeRecord(action="sell", token="SOL", amount=10, price_at_exec=90, timestamp=now),
        ]

        win_rate = calc.win_rate(trades)
        assert win_rate == pytest.approx(50.0)  # 1 win, 1 loss

    def test_trade_count(self):
        """Count total trades."""
        from signal_composer.src.simulation.metrics import PerformanceCalculator
        from signal_composer.src.simulation.executor import TradeRecord

        calc = PerformanceCalculator(initial_value=10000.0)
        now = datetime.now(timezone.utc)

        trades = [
            TradeRecord(action="buy", token="SOL", amount=1000, price_at_exec=100, timestamp=now),
            TradeRecord(action="sell", token="SOL", amount=10, price_at_exec=110, timestamp=now),
            TradeRecord(action="buy", token="SOL", amount=500, price_at_exec=105, timestamp=now),
        ]

        assert calc.trade_count(trades) == 3

    def test_daily_returns_from_equity(self):
        """Calculate daily returns from equity curve."""
        from signal_composer.src.simulation.metrics import PerformanceCalculator

        calc = PerformanceCalculator(initial_value=10000.0)

        equity_curve = [10000, 10100, 10302, 10199]
        daily_returns = calc.daily_returns_from_equity(equity_curve)

        assert len(daily_returns) == 3
        assert daily_returns[0] == pytest.approx(0.01)  # 10000 -> 10100 = 1%
        assert daily_returns[1] == pytest.approx(0.02, rel=0.01)  # 10100 -> 10302 = ~2%

    def test_performance_snapshot(self):
        """Generate complete performance snapshot."""
        from signal_composer.src.simulation.metrics import PerformanceCalculator
        from signal_composer.src.simulation.executor import TradeRecord

        calc = PerformanceCalculator(initial_value=10000.0)
        now = datetime.now(timezone.utc)

        equity_curve = [10000, 10500, 11000, 10500, 11500]
        trades = [
            TradeRecord(action="buy", token="SOL", amount=1000, price_at_exec=100, timestamp=now),
            TradeRecord(action="sell", token="SOL", amount=10, price_at_exec=115, timestamp=now),
        ]

        snapshot = calc.snapshot(
            current_value=11500.0,
            equity_curve=equity_curve,
            trades=trades,
        )

        assert snapshot.total_return_pct == pytest.approx(15.0)
        assert snapshot.max_drawdown_pct < 0  # Should have some drawdown
        assert snapshot.trade_count == 2
        assert snapshot.sharpe_ratio is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/simulation/test_metrics.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement PerformanceCalculator**

```python
# signal_composer/src/simulation/metrics.py
"""Performance metrics calculation."""
from dataclasses import dataclass
from typing import List, Optional
import math

from .executor import TradeRecord


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance metrics."""
    total_return_pct: float
    sharpe_ratio: Optional[float]
    max_drawdown_pct: float
    trade_count: int
    win_rate: Optional[float]


@dataclass
class PerformanceCalculator:
    """Calculate performance metrics for a strategy."""
    initial_value: float

    def total_return_pct(self, current_value: float) -> float:
        """Calculate total return as percentage."""
        if self.initial_value == 0:
            return 0.0
        return ((current_value - self.initial_value) / self.initial_value) * 100

    def daily_returns_from_equity(self, equity_curve: List[float]) -> List[float]:
        """Calculate daily returns from equity curve."""
        if len(equity_curve) < 2:
            return []

        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] == 0:
                returns.append(0.0)
            else:
                daily_return = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                returns.append(daily_return)
        return returns

    def sharpe_ratio(
        self,
        daily_returns: List[float],
        risk_free_rate: float = 0.0,
        annualize: bool = True,
    ) -> Optional[float]:
        """
        Calculate Sharpe ratio.

        Args:
            daily_returns: List of daily return percentages (as decimals, e.g., 0.01 = 1%)
            risk_free_rate: Daily risk-free rate
            annualize: Whether to annualize the ratio

        Returns:
            Sharpe ratio, or None if insufficient data
        """
        if len(daily_returns) < 2:
            return None

        excess_returns = [r - risk_free_rate for r in daily_returns]
        mean_return = sum(excess_returns) / len(excess_returns)

        # Calculate standard deviation
        variance = sum((r - mean_return) ** 2 for r in excess_returns) / len(excess_returns)
        std_dev = math.sqrt(variance)

        if std_dev == 0:
            return float('inf') if mean_return > 0 else 0.0

        sharpe = mean_return / std_dev

        if annualize:
            # Annualize assuming 252 trading days
            sharpe *= math.sqrt(252)

        return sharpe

    def max_drawdown(self, equity_curve: List[float]) -> float:
        """
        Calculate maximum drawdown as percentage.

        Returns: Negative percentage (e.g., -25.0 for 25% drawdown)
        """
        if len(equity_curve) < 2:
            return 0.0

        peak = equity_curve[0]
        max_dd = 0.0

        for value in equity_curve:
            if value > peak:
                peak = value

            if peak > 0:
                drawdown = (value - peak) / peak * 100
                max_dd = min(max_dd, drawdown)

        return max_dd

    def win_rate(self, trades: List[TradeRecord]) -> Optional[float]:
        """
        Calculate win rate from completed round-trip trades.

        Groups buy/sell pairs and calculates % that were profitable.
        """
        # Match buys with subsequent sells for the same token
        open_positions: dict = {}  # token -> (quantity, cost)
        wins = 0
        losses = 0

        for trade in trades:
            if trade.action == "buy":
                token = trade.token
                quantity = trade.amount / trade.price_at_exec
                cost = trade.amount

                if token in open_positions:
                    existing_qty, existing_cost = open_positions[token]
                    open_positions[token] = (existing_qty + quantity, existing_cost + cost)
                else:
                    open_positions[token] = (quantity, cost)

            elif trade.action in ("sell", "sell_all"):
                token = trade.token
                if token not in open_positions:
                    continue

                qty, cost = open_positions[token]
                avg_entry = cost / qty if qty > 0 else 0

                # Check if this sale is profitable
                if trade.price_at_exec > avg_entry:
                    wins += 1
                else:
                    losses += 1

                # Update or remove position
                sold_qty = trade.amount
                if sold_qty >= qty:
                    del open_positions[token]
                else:
                    remaining_qty = qty - sold_qty
                    remaining_cost = remaining_qty * avg_entry
                    open_positions[token] = (remaining_qty, remaining_cost)

        total = wins + losses
        if total == 0:
            return None
        return (wins / total) * 100

    def trade_count(self, trades: List[TradeRecord]) -> int:
        """Count total number of trades."""
        return len(trades)

    def snapshot(
        self,
        current_value: float,
        equity_curve: List[float],
        trades: List[TradeRecord],
    ) -> PerformanceSnapshot:
        """Generate complete performance snapshot."""
        daily_returns = self.daily_returns_from_equity(equity_curve)

        return PerformanceSnapshot(
            total_return_pct=self.total_return_pct(current_value),
            sharpe_ratio=self.sharpe_ratio(daily_returns),
            max_drawdown_pct=self.max_drawdown(equity_curve),
            trade_count=self.trade_count(trades),
            win_rate=self.win_rate(trades),
        )
```

- [ ] **Step 4: Update simulation __init__.py**

```python
# signal_composer/src/simulation/__init__.py
"""Simulation engine for paper trading."""
from .portfolio import Portfolio, Position, InsufficientFundsError, InsufficientPositionError
from .executor import PaperTradeExecutor, TradeRecord
from .metrics import PerformanceCalculator, PerformanceSnapshot

__all__ = [
    "Portfolio",
    "Position",
    "InsufficientFundsError",
    "InsufficientPositionError",
    "PaperTradeExecutor",
    "TradeRecord",
    "PerformanceCalculator",
    "PerformanceSnapshot",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/simulation/test_metrics.py -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add signal_composer/
git commit -m "feat(simulation): add performance metrics calculator"
```

---

## Task 4: Backtesting Engine

**Files:**
- Create: `signal_composer/src/simulation/backtest.py`
- Create: `signal_composer/tests/simulation/test_backtest.py`

- [ ] **Step 1: Write failing tests for BacktestEngine**

```python
# signal_composer/tests/simulation/test_backtest.py
"""Tests for backtesting engine."""
import pytest
from datetime import datetime, timezone, timedelta


class TestBacktestEngine:
    """Test backtesting functionality."""

    def test_backtest_with_single_trigger(self):
        """Backtest a simple strategy over price history."""
        from signal_composer.src.simulation.backtest import BacktestEngine, BacktestResult
        from signal_composer.src.engine.dsl.types import (
            Strategy, Trigger, SimpleCondition, Action, ActionType, RiskRules, Operator
        )

        # Simple strategy: buy when price < 95
        strategy = Strategy(
            id="test_backtest",
            name="Dip Buyer",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="buy_dip",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.LT,
                        value=95.0,
                    ),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=20),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10,
                max_position_pct=50,
                max_trades_per_day=10,
                slippage_limit_bps=100,
            ),
        )

        # Price history: starts at 100, dips to 90, recovers to 110
        price_history = [
            {"timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc), "SOL": 100.0},
            {"timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc), "SOL": 98.0},
            {"timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc), "SOL": 94.0},  # Buy trigger
            {"timestamp": datetime(2024, 1, 4, tzinfo=timezone.utc), "SOL": 90.0},  # Buy again
            {"timestamp": datetime(2024, 1, 5, tzinfo=timezone.utc), "SOL": 95.0},
            {"timestamp": datetime(2024, 1, 6, tzinfo=timezone.utc), "SOL": 105.0},
            {"timestamp": datetime(2024, 1, 7, tzinfo=timezone.utc), "SOL": 110.0},
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=50)
        result = engine.run(strategy, price_history)

        assert result is not None
        assert result.total_return_pct > 0  # Should profit from dip buying
        assert len(result.trades) >= 2  # At least 2 buy triggers
        assert len(result.equity_curve) == len(price_history)

    def test_backtest_respects_risk_rules(self):
        """Backtest respects max position size."""
        from signal_composer.src.simulation.backtest import BacktestEngine
        from signal_composer.src.engine.dsl.types import (
            Strategy, Trigger, SimpleCondition, Action, ActionType, RiskRules, Operator
        )

        # Strategy: always buy
        strategy = Strategy(
            id="always_buy",
            name="Always Buy",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="always",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.GT,
                        value=0,  # Always true
                    ),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=30),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10,
                max_position_pct=40,  # Max 40%
                max_trades_per_day=10,
                slippage_limit_bps=100,
            ),
        )

        price_history = [
            {"timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc), "SOL": 100.0},
            {"timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc), "SOL": 100.0},
            {"timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc), "SOL": 100.0},
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=50)
        result = engine.run(strategy, price_history)

        # Position should be capped at ~40% even with 3 buy signals
        final_portfolio = result.final_portfolio
        position_pct = final_portfolio.position_pct("SOL", {"SOL": 100.0})
        assert position_pct <= 42.0  # Allow some tolerance for slippage

    def test_backtest_with_derived_streams(self):
        """Backtest using derived streams (MA crossover)."""
        from signal_composer.src.simulation.backtest import BacktestEngine
        from signal_composer.src.engine.dsl.types import (
            Strategy, Trigger, SimpleCondition, Action, ActionType,
            RiskRules, DerivedStream, Operator
        )

        # MA crossover strategy
        strategy = Strategy(
            id="ma_cross",
            name="MA Crossover",
            version=1,
            tokens=["SOL"],
            derived_streams=[
                DerivedStream(id="ma_short", type="moving_average", token="SOL", window="1h"),
                DerivedStream(id="ma_long", type="moving_average", token="SOL", window="4h"),
            ],
            triggers=[
                Trigger(
                    id="golden_cross",
                    when=SimpleCondition(
                        metric="ma_short",
                        op=Operator.CROSSES_ABOVE,
                        compare_to="ma_long",
                    ),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=25),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10,
                max_position_pct=50,
                max_trades_per_day=10,
                slippage_limit_bps=100,
            ),
        )

        # Need enough price history for derived streams
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        price_history = [
            {"timestamp": base_time + timedelta(hours=i), "SOL": 100.0 + (i % 10) - 5}
            for i in range(20)
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=50)
        result = engine.run(strategy, price_history)

        assert result is not None
        assert len(result.equity_curve) == len(price_history)

    def test_backtest_result_has_performance_metrics(self):
        """Backtest result includes performance metrics."""
        from signal_composer.src.simulation.backtest import BacktestEngine
        from signal_composer.src.engine.dsl.types import (
            Strategy, Trigger, SimpleCondition, Action, ActionType, RiskRules, Operator
        )

        strategy = Strategy(
            id="simple",
            name="Simple",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="buy",
                    when=SimpleCondition(metric="price", token="SOL", op=Operator.LT, value=95),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=20),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10, max_position_pct=50,
                max_trades_per_day=10, slippage_limit_bps=100
            ),
        )

        price_history = [
            {"timestamp": datetime(2024, 1, i, tzinfo=timezone.utc), "SOL": 100 - i}
            for i in range(1, 8)
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=50)
        result = engine.run(strategy, price_history)

        assert hasattr(result, 'total_return_pct')
        assert hasattr(result, 'sharpe_ratio')
        assert hasattr(result, 'max_drawdown_pct')
        assert hasattr(result, 'trade_count')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/simulation/test_backtest.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement BacktestEngine**

```python
# signal_composer/src/simulation/backtest.py
"""Backtesting engine for strategy simulation."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import deque

from ..engine.dsl.types import Strategy, DerivedStream
from ..engine.dsl.executor import StrategyExecutor
from ..engine.streams.derived import DerivedStreamCalculator
from .portfolio import Portfolio
from .executor import PaperTradeExecutor, TradeRecord
from .metrics import PerformanceCalculator, PerformanceSnapshot


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    total_return_pct: float
    sharpe_ratio: Optional[float]
    max_drawdown_pct: float
    trade_count: int
    win_rate: Optional[float]
    equity_curve: List[float]
    trades: List[TradeRecord]
    final_portfolio: Portfolio


# Window to tick count mapping (approximate)
WINDOW_TO_TICKS = {
    "1m": 2,
    "5m": 10,
    "15m": 30,
    "1h": 120,
    "4h": 480,
    "1d": 2880,  # 48 ticks per hour * 24 hours (30s ticks)
}


def _window_to_tick_count(window: str) -> int:
    """Convert window string to number of ticks needed."""
    return WINDOW_TO_TICKS.get(window, 120)  # Default to 1h


@dataclass
class BacktestEngine:
    """
    Run backtests by replaying price history through strategy executor.

    Computes derived streams on-the-fly and tracks portfolio state.
    """
    initial_capital: float = 10000.0
    slippage_bps: int = 100

    def _compute_derived_streams(
        self,
        derived_streams: List[DerivedStream],
        price_histories: Dict[str, deque],
        previous_derived: Dict[str, float],
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute derived stream values from price history.

        Returns dict like: {"ma_short": {"current": 100, "previous": 99}}
        """
        calculator = DerivedStreamCalculator()
        result = {}

        for ds in derived_streams:
            token = ds.token
            if token not in price_histories:
                continue

            prices = list(price_histories[token])
            tick_count = _window_to_tick_count(ds.window)

            # Use only the required window of prices
            window_prices = prices[-tick_count:] if len(prices) >= tick_count else prices

            current_value = calculator.calculate(ds.type, window_prices, tick_count)
            previous_value = previous_derived.get(ds.id, current_value)

            if current_value is not None:
                result[ds.id] = {
                    "current": current_value,
                    "previous": previous_value if previous_value else current_value,
                }

        return result

    def run(
        self,
        strategy: Strategy,
        price_history: List[Dict[str, Any]],
    ) -> BacktestResult:
        """
        Run backtest over price history.

        Args:
            strategy: Strategy to backtest
            price_history: List of price snapshots with 'timestamp' and token prices

        Returns:
            BacktestResult with performance metrics
        """
        portfolio = Portfolio(initial_balance=self.initial_capital)
        trade_executor = PaperTradeExecutor(
            portfolio=portfolio,
            slippage_bps=self.slippage_bps,
            risk_rules=strategy.risk_rules,
        )
        strategy_executor = StrategyExecutor(strategy)

        trades: List[TradeRecord] = []
        equity_curve: List[float] = []

        # Track price history for derived streams (rolling window)
        max_window_ticks = max(
            (_window_to_tick_count(ds.window) for ds in strategy.derived_streams),
            default=120
        )
        price_histories: Dict[str, deque] = {
            token: deque(maxlen=max_window_ticks) for token in strategy.tokens
        }
        previous_derived: Dict[str, float] = {}

        for tick in price_history:
            timestamp = tick.get("timestamp")
            prices = {k: v for k, v in tick.items() if k != "timestamp"}

            # Update price histories
            for token, price in prices.items():
                if token in price_histories:
                    price_histories[token].append(price)

            # Compute derived streams
            derived = self._compute_derived_streams(
                strategy.derived_streams,
                price_histories,
                previous_derived,
            )

            # Build market data for executor
            market_data: Dict[str, Any] = {}
            for token, price in prices.items():
                market_data[token] = {"price": price}

            if derived:
                market_data["_derived"] = derived

            # Evaluate strategy
            triggered_actions = strategy_executor.evaluate(market_data)

            # Execute triggered actions
            for ta in triggered_actions:
                trade = trade_executor.execute(
                    action=ta.action,
                    prices=prices,
                    trigger_id=ta.trigger_id,
                    timestamp=timestamp,
                )
                if trade:
                    trades.append(trade)

            # Record equity
            equity = portfolio.total_value_at_prices(prices)
            equity_curve.append(equity)

            # Update previous derived values
            for ds_id, values in derived.items():
                previous_derived[ds_id] = values["current"]

        # Calculate final metrics
        final_prices = {k: v for k, v in price_history[-1].items() if k != "timestamp"}
        final_value = portfolio.total_value_at_prices(final_prices)

        perf_calc = PerformanceCalculator(initial_value=self.initial_capital)
        snapshot = perf_calc.snapshot(
            current_value=final_value,
            equity_curve=equity_curve,
            trades=trades,
        )

        return BacktestResult(
            total_return_pct=snapshot.total_return_pct,
            sharpe_ratio=snapshot.sharpe_ratio,
            max_drawdown_pct=snapshot.max_drawdown_pct,
            trade_count=snapshot.trade_count,
            win_rate=snapshot.win_rate,
            equity_curve=equity_curve,
            trades=trades,
            final_portfolio=portfolio,
        )
```

- [ ] **Step 4: Update simulation __init__.py**

```python
# signal_composer/src/simulation/__init__.py
"""Simulation engine for paper trading."""
from .portfolio import Portfolio, Position, InsufficientFundsError, InsufficientPositionError
from .executor import PaperTradeExecutor, TradeRecord
from .metrics import PerformanceCalculator, PerformanceSnapshot
from .backtest import BacktestEngine, BacktestResult

__all__ = [
    "Portfolio",
    "Position",
    "InsufficientFundsError",
    "InsufficientPositionError",
    "PaperTradeExecutor",
    "TradeRecord",
    "PerformanceCalculator",
    "PerformanceSnapshot",
    "BacktestEngine",
    "BacktestResult",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/simulation/test_backtest.py -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add signal_composer/
git commit -m "feat(simulation): add backtesting engine with derived stream support"
```

---

## Task 5: Add Portfolio Database Model

**Files:**
- Modify: `signal_composer/src/db/models.py`
- Modify: `signal_composer/src/db/__init__.py`

- [ ] **Step 1: Add Portfolio model to models.py**

Add after `PriceData` class:

```python
# Add to signal_composer/src/db/models.py

class Portfolio(Base):
    """User's portfolio investment in a strategy."""
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    shares_owned: Mapped[float] = mapped_column(Float, default=0.0)
    entry_value: Mapped[float] = mapped_column(Float, default=0.0)  # Total invested
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_portfolio_user_strategy", "user_id", "strategy_id", unique=True),
    )
```

- [ ] **Step 2: Update __init__.py exports**

```python
# signal_composer/src/db/__init__.py
"""Database module."""
from .connection import get_session, init_db, drop_db
from .models import User, Strategy, StrategyPerformance, PaperTrade, PriceData, Portfolio

__all__ = [
    "get_session",
    "init_db",
    "drop_db",
    "User",
    "Strategy",
    "StrategyPerformance",
    "PaperTrade",
    "PriceData",
    "Portfolio",
]
```

- [ ] **Step 3: Commit**

```bash
git add signal_composer/
git commit -m "feat(db): add Portfolio model for user strategy investments"
```

---

## Task 6: CLI Backtest Command

**Files:**
- Modify: `signal_composer/src/cli.py`

- [ ] **Step 1: Add backtest command to CLI**

Add after `cmd_evaluate` function:

```python
# Add to signal_composer/src/cli.py

async def cmd_backtest(args: argparse.Namespace) -> int:
    """Run backtest with generated price history."""
    from datetime import datetime, timezone, timedelta
    import random

    try:
        strategy = parse_strategy_file(args.file)
        print(f"Backtesting strategy: {strategy.name}")
        print(f"Initial capital: ${args.capital:,.2f}")
        print(f"Days: {args.days}")
        print()

        # Generate synthetic price history for demo
        # In production, this would load from database
        base_price = 100.0
        base_time = datetime.now(timezone.utc) - timedelta(days=args.days)
        price_history = []

        for i in range(args.days * 48):  # 48 ticks per day (30 min intervals for demo)
            timestamp = base_time + timedelta(minutes=i * 30)
            # Random walk with drift
            change = random.gauss(0.001, 0.02)  # Slight upward drift
            base_price *= (1 + change)

            tick = {"timestamp": timestamp}
            for token in strategy.tokens:
                tick[token] = base_price * (1 + random.gauss(0, 0.01))
            price_history.append(tick)

        # Run backtest
        from .simulation.backtest import BacktestEngine

        engine = BacktestEngine(
            initial_capital=args.capital,
            slippage_bps=args.slippage,
        )
        result = engine.run(strategy, price_history)

        # Print results
        print("=" * 50)
        print("BACKTEST RESULTS")
        print("=" * 50)
        print(f"Total Return:   {result.total_return_pct:+.2f}%")
        print(f"Sharpe Ratio:   {result.sharpe_ratio:.2f}" if result.sharpe_ratio else "Sharpe Ratio:   N/A")
        print(f"Max Drawdown:   {result.max_drawdown_pct:.2f}%")
        print(f"Trade Count:    {result.trade_count}")
        print(f"Win Rate:       {result.win_rate:.1f}%" if result.win_rate else "Win Rate:       N/A")
        print()
        print(f"Final Value:    ${result.equity_curve[-1]:,.2f}")

        if args.verbose and result.trades:
            print()
            print("TRADE LOG (last 10):")
            print("-" * 50)
            for trade in result.trades[-10:]:
                print(f"  {trade.timestamp.strftime('%Y-%m-%d %H:%M')} | {trade.action.upper():8} | {trade.token} | ${trade.amount:.2f} @ ${trade.price_at_exec:.2f}")

        return 0

    except ParseError as e:
        print(f"✗ Parse error: {e.message}")
        return 1
```

- [ ] **Step 2: Add backtest subparser to main()**

In the `main()` function, add after the evaluate parser:

```python
    # backtest command
    backtest_parser = subparsers.add_parser("backtest", help="Run backtest on strategy")
    backtest_parser.add_argument("file", type=Path, help="Strategy JSON file")
    backtest_parser.add_argument("--capital", type=float, default=10000.0, help="Initial capital (default: 10000)")
    backtest_parser.add_argument("--days", type=int, default=30, help="Days to backtest (default: 30)")
    backtest_parser.add_argument("--slippage", type=int, default=100, help="Slippage in bps (default: 100)")
    backtest_parser.add_argument("-v", "--verbose", action="store_true", help="Show trade log")
```

- [ ] **Step 3: Add backtest handler in main()**

In the command dispatch section:

```python
    elif args.command == "backtest":
        return asyncio.run(cmd_backtest(args))
```

- [ ] **Step 4: Test backtest command**

Run:
```bash
cd signal_composer
signal-composer backtest examples/sample_strategy.json --days 30 -v
```

Expected: Backtest runs and shows results

- [ ] **Step 5: Commit**

```bash
git add signal_composer/
git commit -m "feat(cli): add backtest command for strategy simulation"
```

---

## Task 7: Integration Tests for Simulation

**Files:**
- Create: `signal_composer/tests/simulation/test_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# signal_composer/tests/simulation/test_integration.py
"""Integration tests for simulation engine."""
import pytest
from datetime import datetime, timezone, timedelta


class TestSimulationIntegration:
    """Test full simulation workflow."""

    def test_full_paper_trading_flow(self):
        """Test: parse strategy → create portfolio → execute trades → calculate metrics."""
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.simulation.portfolio import Portfolio
        from signal_composer.src.simulation.executor import PaperTradeExecutor
        from signal_composer.src.simulation.metrics import PerformanceCalculator
        from signal_composer.src.engine.dsl.executor import StrategyExecutor

        # Parse strategy
        strategy_json = {
            "id": "integration_test",
            "name": "Integration Test Strategy",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [],
            "triggers": [
                {
                    "id": "buy_dip",
                    "when": {"metric": "price_change_pct", "token": "SOL", "window": "15m", "op": "<", "value": -3},
                    "action": {"type": "buy", "token": "SOL", "amount_pct": 20},
                }
            ],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 5,
                "slippage_limit_bps": 100,
            },
        }
        strategy = parse_strategy(strategy_json)

        # Create portfolio and executors
        portfolio = Portfolio(initial_balance=10000.0)
        trade_executor = PaperTradeExecutor(
            portfolio=portfolio,
            slippage_bps=50,
            risk_rules=strategy.risk_rules,
        )
        strategy_executor = StrategyExecutor(strategy)

        # Simulate market dip
        market_data = {"SOL": {"price": 100.0, "price_change_pct": {"15m": -5.0}}}
        prices = {"SOL": 100.0}

        actions = strategy_executor.evaluate(market_data)
        assert len(actions) == 1

        trade = trade_executor.execute(actions[0].action, prices, actions[0].trigger_id)
        assert trade is not None
        assert trade.action == "buy"

        # Calculate metrics
        perf = PerformanceCalculator(initial_value=10000.0)
        equity_curve = [10000.0, portfolio.total_value_at_prices({"SOL": 110.0})]
        snapshot = perf.snapshot(
            current_value=equity_curve[-1],
            equity_curve=equity_curve,
            trades=[trade],
        )

        assert snapshot.total_return_pct > 0  # Price went up
        assert snapshot.trade_count == 1

    def test_backtest_matches_manual_simulation(self):
        """Backtest should produce same results as manual simulation."""
        from signal_composer.src.simulation.backtest import BacktestEngine
        from signal_composer.src.engine.dsl.types import (
            Strategy, Trigger, SimpleCondition, Action, ActionType, RiskRules, Operator
        )

        strategy = Strategy(
            id="consistency_test",
            name="Consistency Test",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="buy",
                    when=SimpleCondition(metric="price", token="SOL", op=Operator.LT, value=95),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=25),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10, max_position_pct=60,
                max_trades_per_day=5, slippage_limit_bps=100
            ),
        )

        price_history = [
            {"timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc), "SOL": 100.0},
            {"timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc), "SOL": 94.0},  # Buy
            {"timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc), "SOL": 92.0},  # Buy
            {"timestamp": datetime(2024, 1, 4, tzinfo=timezone.utc), "SOL": 98.0},
            {"timestamp": datetime(2024, 1, 5, tzinfo=timezone.utc), "SOL": 105.0},
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=50)
        result = engine.run(strategy, price_history)

        # Should have 2 buy trades (at 94 and 92)
        buy_trades = [t for t in result.trades if t.action == "buy"]
        assert len(buy_trades) == 2

        # Should be profitable (bought low, ended high)
        assert result.total_return_pct > 0
```

- [ ] **Step 2: Run all simulation tests**

Run: `cd signal_composer && pytest tests/simulation/ -v`

Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `cd signal_composer && pytest -v`

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add signal_composer/
git commit -m "test(simulation): add integration tests for paper trading flow"
```

---

## Summary

After completing all tasks, you will have:

1. **Portfolio Management** - Track positions, cash balance, P&L
2. **Paper Trade Executor** - Execute trades with slippage and risk rules
3. **Performance Metrics** - Sharpe ratio, max drawdown, win rate
4. **Backtesting Engine** - Run strategies against historical data
5. **Database Portfolio Model** - Store user investments
6. **CLI Backtest Command** - Test strategies from command line

**Next Plan:** Plan 3 (API & Authentication) will add REST API, SIWS auth, and strategy CRUD.
