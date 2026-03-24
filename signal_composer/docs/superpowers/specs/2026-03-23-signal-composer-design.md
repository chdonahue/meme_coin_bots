# SignalComposer: Strategy Marketplace Design Spec

**Date:** 2026-03-23
**Status:** Draft
**Author:** Claude (with human collaboration)

---

## Executive Summary

SignalComposer is a marketplace for composable trading strategies on Solana. Users build strategies using a visual interface that generates a constrained DSL (JSON). Strategies execute against real market data in paper-trading mode, with performance displayed on public leaderboards. Users can "invest" in strategies by buying shares, receiving proportional returns from a pooled capital model.

**MVP Scope:** Paper trading with simulated portfolios to validate marketplace mechanics.
**Phase 2:** Real capital via Solana smart contracts (escrow pools).
**Phase 3:** Confidential computing (AWS Nitro Enclaves) so platform cannot see strategy logic.

---

## Problem Statement

1. **Strategy creators** have alpha but limited capital. They want to monetize strategies without revealing the logic.
2. **Investors** want exposure to diverse trading strategies without building them. They want transparency on performance, not implementation.
3. **Trust problem:** How do you prove a strategy works without revealing it? How do investors trust a black box?

**SignalComposer's answer:** Transparent performance metrics, creator skin-in-the-game signals, and eventually cryptographic guarantees via confidential computing.

---

## Core Concepts

### Strategy DSL

Strategies are JSON documents, not arbitrary code. This enables:
- Validation and safety checks
- Deterministic execution
- Future migration to secure enclaves
- Non-programmers can build via visual UI

### Composable Building Blocks

| Category | Primitives |
|----------|-----------|
| **Metrics** | `price`, `price_change_pct`, `volume`, `volume_change_pct`, `position_gain_pct`, `position_size` |
| **Windows** | `1m`, `5m`, `15m`, `1h`, `4h`, `1d` |
| **Operators** | `>`, `<`, `>=`, `<=`, `==`, `crosses_above`, `crosses_below` |
| **Combinators** | `all` (AND), `any` (OR), `not` |
| **Actions** | `buy`, `sell`, `sell_all` |
| **Amount types** | `amount_pct` (% of capital), `amount_fixed` (fixed USD) |

### Derived Streams

Users can define computed metrics from raw data:

| Type | Parameters | Output |
|------|-----------|--------|
| `moving_average` | token, metric, window | Rolling average |
| `ema` | token, metric, window | Exponential MA |
| `rsi` | token, periods | Relative strength index |
| `volatility` | token, window | Standard deviation |
| `price_delta` | token, window | Price change over window |

Derived streams are private to each strategy in MVP. Future: shareable indicator marketplace with micropayments.

### Pooled Capital Model (Phase 2)

- Creator defines strategy, sets number of shares available
- Investors buy shares, contributing capital to pool
- Strategy executes once against pooled capital (no timing disadvantage)
- Profits/losses distributed proportionally
- Creator takes performance fee
- Creator skin-in-the-game is transparent (% of pool they own)

---

## Strategy DSL Specification

### Full Example

```json
{
  "id": "strategy_abc123",
  "name": "SOL Momentum Rider",
  "description": "Buys SOL dips, takes profit on rebounds",
  "version": 1,
  "tokens": ["SOL", "BONK", "WIF"],

  "derived_streams": [
    {
      "id": "sol_ma_4h",
      "name": "SOL 4-Hour MA",
      "type": "moving_average",
      "token": "SOL",
      "metric": "price",
      "window": "4h"
    },
    {
      "id": "sol_ma_48h",
      "name": "SOL 48-Hour MA",
      "type": "moving_average",
      "token": "SOL",
      "metric": "price",
      "window": "48h"
    }
  ],

  "triggers": [
    {
      "id": "golden_cross",
      "when": {
        "metric": "sol_ma_4h",
        "op": "crosses_above",
        "compare_to": "sol_ma_48h"
      },
      "action": {
        "type": "buy",
        "token": "SOL",
        "amount_pct": 30
      }
    },
    {
      "id": "buy_the_dip",
      "when": {
        "all": [
          { "metric": "price_change_pct", "token": "SOL", "window": "15m", "op": "<", "value": -5 },
          { "metric": "volume", "token": "SOL", "window": "15m", "op": ">", "value": 1000000 }
        ]
      },
      "action": {
        "type": "buy",
        "token": "SOL",
        "amount_pct": 25
      }
    },
    {
      "id": "take_profit",
      "when": {
        "metric": "position_gain_pct",
        "token": "SOL",
        "op": ">",
        "value": 10
      },
      "action": {
        "type": "sell",
        "token": "SOL",
        "amount_pct": 50
      }
    }
  ],

  "risk_rules": {
    "stop_loss_pct": -15,
    "max_position_pct": 40,
    "max_trades_per_day": 10,
    "slippage_limit_bps": 300
  }
}
```

### Risk Rules (Mandatory)

Every strategy must define:
- `stop_loss_pct`: Exit position if loss exceeds this %
- `max_position_pct`: Maximum % of portfolio in single token
- `max_trades_per_day`: Rate limiting
- `slippage_limit_bps`: Maximum acceptable slippage

---

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        MARKETPLACE UI                           │
│         (Browse strategies, leaderboard, create/edit)           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API SERVER                               │
│     (Strategy CRUD, user accounts, portfolio management)         │
└─────────────────────────────────────────────────────────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
    │  STRATEGY    │    │    DATA      │    │  SIMULATION  │
    │   ENGINE     │    │   STREAMS    │    │    ENGINE    │
    │              │    │              │    │              │
    │ DSL Parser   │◄───│ Price feeds  │───►│ Paper trades │
    │ Validator    │    │ Volume       │    │ P&L tracking │
    │ Executor     │    │ On-chain     │    │ Metrics calc │
    └──────────────┘    └──────────────┘    └──────────────┘
                                │
                                ▼
                        ┌──────────────┐
                        │   DATABASE   │
                        │              │
                        │ Strategies   │
                        │ Users        │
                        │ Performance  │
                        │ Trade history│
                        └──────────────┘
```

### Data Streams Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      EXTERNAL DATA SOURCES                       │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Jupiter API   │   Birdeye API   │   Helius (on-chain events)  │
│   - Quotes      │   - OHLCV       │   - Wallet activity         │
│   - Liquidity   │   - Token stats │   - Swap events             │
└────────┬────────┴────────┬────────┴──────────────┬──────────────┘
         │                 │                       │
         └─────────────────┼───────────────────────┘
                           ▼
              ┌─────────────────────────┐
              │     DATA INGESTION      │
              │                         │
              │  - Normalize formats    │
              │  - Validate/clean       │
              │  - Rate limit handling  │
              └───────────┬─────────────┘
                          ▼
              ┌─────────────────────────┐
              │    TIME-SERIES STORE    │
              │                         │
              │  Raw streams:           │
              │  - price (per token)    │
              │  - volume (per token)   │
              │  - liquidity            │
              │                         │
              │  Resolution: 30s ticks  │
              │  (configurable to 15s)  │
              └───────────┬─────────────┘
                          ▼
              ┌─────────────────────────┐
              │  DERIVED STREAM ENGINE  │
              │                         │
              │  Computes on-demand:    │
              │  - Moving averages      │
              │  - RSI, volatility      │
              │  - Custom indicators    │
              │                         │
              │  Caches hot streams     │
              └───────────┬─────────────┘
                          ▼
              ┌─────────────────────────┐
              │    STRATEGY ENGINE      │
              │                         │
              │  Evaluates triggers     │
              │  against stream values  │
              └─────────────────────────┘
```

### Data Stream Types

**Type 1: Structured (Price/Volume)**
- Continuous time-series (30s ticks)
- Stored for tokens in active universe
- Full backtest support

**Type 2: Event-Based (Social/Mentions)**
- Discrete events, not continuous
- Schema: `{timestamp, source, token, event_type, metadata}`
- Limited backtest support (honest about limitations)

### Event-Based Social Signals

```json
{
  "timestamp": "2024-03-15T10:23:45Z",
  "source": "telegram",
  "channel": "whale_alerts",
  "token_mentioned": "NEWMEME123...",
  "event_type": "mention",
  "metadata": {
    "message_snippet": "NEWMEME looking ready...",
    "sentiment": "bullish",
    "has_ca": true
  }
}
```

**Derived metrics from events:**
- `mentions_count`: Mentions in last N minutes
- `mention_velocity`: Rate of change
- `first_mention`: Is this first mention ever?
- `channel_sentiment`: Aggregated sentiment

**Backtest limitation notice:**
> "This strategy uses social signals. Backtest simulates historical events we captured, but cannot replay signals we didn't observe. Results are indicative, not definitive."

### Tiered Token Storage

| Tier | Tokens | Price Data | Social Events | Retention |
|------|--------|------------|---------------|-----------|
| Core | Top 50 by liquidity | Full 30s | All mentions | 1 year |
| Active | Currently traded by any strategy | Full 30s | All mentions | While active + 30 days |
| Ephemeral | Random meme coins | None (fetch on-demand) | Trigger event only | 7 days |

### Execution Architecture (Scalability)

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA TICK                                 │
│            (New price/volume data arrives)                       │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MESSAGE QUEUE (Redis)                        │
│                                                                  │
│   "tick:SOL" → {price: 150.23, volume: 1.2M, timestamp: ...}    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  EVAL WORKER 1    │ │  EVAL WORKER 2    │ │  EVAL WORKER N    │
│  Strategies 1-500 │ │  Strategies 501+  │ │  Strategies ...   │
└─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ACTION QUEUE (Redis)                         │
│   {strategy: "abc", action: "buy", token: "SOL", amount: 25%}   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  EXEC WORKER 1    │ │  EXEC WORKER 2    │ │  EXEC WORKER N    │
│  MVP: DB writes   │ │  MVP: DB writes   │ │  MVP: DB writes   │
│  Phase 2: Solana  │ │  Phase 2: Solana  │ │  Phase 2: Solana  │
└───────────────────┘ └───────────────────┘ └───────────────────┘
```

**Design decisions:**

| Decision | Choice | Why |
|----------|--------|-----|
| Message broker | Redis Streams | Fast, simple, Kafka overkill for MVP |
| Worker partitioning | By strategy ID range | Even distribution, horizontally scalable |
| Evaluation | Stateless workers | Any worker can evaluate any strategy |
| Derived streams | Pre-computed + cached | Incremental updates, not full recompute |
| Action deduplication | Idempotency keys | Prevent double-execution |

**Performance targets (MVP):**

| Metric | Target |
|--------|--------|
| Strategies evaluated per tick | 10,000+ |
| Tick-to-action latency | < 500ms |
| Concurrent paper trades | Unlimited (DB writes) |

---

## Database Schema

### Core Entities

```
┌─────────────────┐       ┌─────────────────┐
│     USERS       │       │   STRATEGIES    │
├─────────────────┤       ├─────────────────┤
│ id              │──┐    │ id              │
│ wallet_address  │  │    │ creator_id (FK) │──┐
│ username        │  │    │ name            │  │
│ created_at      │  │    │ dsl_json        │  │
└─────────────────┘  │    │ status          │  │
                     │    │ is_public       │  │
┌─────────────────┐  │    └─────────────────┘  │
│   PORTFOLIOS    │  │                         │
├─────────────────┤  │    ┌─────────────────┐  │
│ id              │  │    │  STRATEGY_PERF  │  │
│ user_id (FK)    │◄─┘    ├─────────────────┤  │
│ strategy_id(FK) │◄──────│ strategy_id(FK) │◄─┘
│ shares_owned    │       │ date            │
│ entry_value     │       │ total_return    │
│ current_value   │       │ sharpe_ratio    │
└─────────────────┘       │ max_drawdown    │
                          └─────────────────┘

┌─────────────────┐       ┌─────────────────┐
│  PAPER_TRADES   │       │   PRICE_DATA    │
├─────────────────┤       ├─────────────────┤
│ id              │       │ token           │
│ strategy_id(FK) │       │ timestamp       │
│ token           │       │ price           │
│ action          │       │ volume          │
│ amount          │       │ source          │
│ price_at_exec   │       └─────────────────┘
│ timestamp       │
└─────────────────┘
```

### Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Relational data | PostgreSQL | Users, strategies, portfolios |
| Time-series | TimescaleDB extension | Price data, performance snapshots |
| Cache | Redis | Hot data, message queues |
| Auth | Solana wallet signatures | Web3-native, no passwords |

### Data Retention for Backtesting

| Resolution | Retention | Purpose |
|------------|-----------|---------|
| 30s candles | 1 year | Full-fidelity backtesting |
| 5m candles | 3 years | Longer backtests, lighter storage |
| 1h candles | Forever | Long-term analysis |

---

## Marketplace & Leaderboard

### Leaderboard Ranking

| Metric | Weight | Why |
|--------|--------|-----|
| Total return | 30% | Raw performance |
| Sharpe ratio | 25% | Risk-adjusted returns |
| Max drawdown | 20% | Penalize volatility |
| Strategy age | 15% | Longevity = trust |
| Consistency | 10% | Steady > lucky |

### Anti-Gaming Measures

- Minimum 14 days before appearing on leaderboard
- Outlier detection (one lucky trade shouldn't dominate)
- Drawdown penalties
- Track both all-time and rolling windows (30d, 90d)

### Trust Signals

| Signal | What it shows |
|--------|---------------|
| Creator skin-in-the-game | % of pool owned by creator |
| Strategy age | How long it's been running |
| Trade count | Activity level |
| Shares sold | Social proof |
| Max drawdown | Risk profile |

### Backtesting Engine

```
┌─────────────────────────────────────────────────────────────────┐
│                      BACKTEST REQUEST                            │
│  Strategy DSL + Date Range + Initial Capital                     │
└─────────────────────────────┬───────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    HISTORICAL DATA REPLAY                        │
│                                                                  │
│  For each 30s tick in range:                                    │
│    1. Load price/volume state                                   │
│    2. Compute derived streams                                   │
│    3. Evaluate triggers                                         │
│    4. Simulate fills (with slippage model)                      │
│    5. Update portfolio state                                    │
└─────────────────────────────┬───────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKTEST RESULTS                            │
│  - Equity curve                                                 │
│  - Trade log                                                    │
│  - Performance metrics                                          │
│  - Warnings (overfitting, low sample size)                      │
└─────────────────────────────────────────────────────────────────┘
```

**Safeguards:**
- Slippage modeling based on historical volume
- Lookahead bias prevention
- Overfitting warnings
- Out-of-sample testing encouragement

---

## Phased Roadmap

### Phase 1: MVP (Paper Trading)

**Build:**
1. Strategy DSL parser and validator
2. Visual strategy builder UI
3. Data ingestion (Jupiter, Birdeye, Helius)
4. Derived stream engine
5. Event-based social triggers (Telegram)
6. Paper trading simulation engine
7. Backtesting engine
8. Marketplace UI with leaderboard
9. "Follow" strategies (simulated portfolios)
10. Performance metrics and trust signals

**Validate:**
- Do users create strategies?
- Do users engage with the leaderboard?
- Is the DSL expressive enough?
- What features are missing?

### Phase 2: Real Capital (Smart Contracts)

**Add:**
- Solana escrow contracts (per-strategy pools)
- Share purchase/redemption on-chain
- Real trading via Jupiter
- Performance fee distribution
- Smart contract audits

**Architecture:**
- Pool Contract holds capital in escrow
- Only strategy executor can trade
- Users deposit/withdraw permissionlessly
- Share accounting on-chain

### Phase 3: Confidential Computing

**Add:**
- Strategy execution in AWS Nitro Enclaves
- Strategy DSL encrypted at rest
- Remote attestation for verification
- Open-source enclave code

**Trust model shifts:**
- Platform cannot see strategy logic
- Users verify via cryptographic attestation
- Trust Intel/AWS hardware, not platform operator

---

## Future Considerations

### Derived Stream Marketplace

Creators publish indicators (derived streams). Others use them in strategies. Micropayments per evaluation tick via Solana.

```
┌─────────────────────────────────────────────────────────────────┐
│  INDICATOR MARKETPLACE                                           │
├─────────────────────────────────────────────────────────────────┤
│  "Whale Wallet Momentum"         by quant_guru                  │
│  Used by 847 strategies │ $0.0001/use │ Earned: $423            │
├─────────────────────────────────────────────────────────────────┤
│  "Social Velocity Index"         by degen_scientist             │
│  Used by 312 strategies │ $0.0002/use │ Earned: $891            │
└─────────────────────────────────────────────────────────────────┘
```

### Other Future Ideas

| Idea | Notes |
|------|-------|
| Multi-asset expansion | Stocks (Alpaca), sports betting - post PMF |
| Strategy composition | Meta-strategies combining other strategies |
| Social features | Comments, ratings, creator profiles |
| Mobile app | Push notifications for strategy events |
| API access | Programmatic strategy building for power users |

---

## Repository Structure

```
meme_coin_bots/
│
├── legacy/                        # Existing code preserved
│   ├── bots/
│   ├── src/
│   ├── notebooks/
│   └── ...
│
├── signal_composer/               # New project
│   ├── src/
│   │   ├── api/                   # API server
│   │   ├── engine/                # DSL parser, executor
│   │   ├── data/                  # Data ingestion, streams
│   │   ├── simulation/            # Paper trading, backtesting
│   │   ├── marketplace/           # Leaderboard, discovery
│   │   └── db/                    # Database models
│   ├── web/                       # Frontend
│   ├── contracts/                 # Future: Solana programs
│   ├── tests/
│   └── docs/
│
└── README.md
```

### Reusable from Legacy

| File | What to reuse |
|------|---------------|
| `legacy/src/blockchain.py` | Jupiter integration, swap functions |
| `legacy/src/wallet/` | HD wallet management |
| `legacy/src/listeners/telegram_listener.py` | Telegram parsing |
| `legacy/src/polling/quote_poller.py` | Price polling patterns |
| `legacy/src/transaction_parser.py` | Solana tx parsing |

---

## Open Questions

1. **Pricing model:** How does the platform make money? Transaction fees? Premium features? Subscription?
2. **Token universe management:** How do tokens get added/removed from Core tier?
3. **Strategy versioning:** What happens when a creator updates their strategy? New strategy or version history?
4. **Dispute resolution:** What if a strategy performs differently than expected due to bugs?

---

## Appendix: Why Crypto First

| Asset Class | Execution Complexity | Regulatory Burden |
|-------------|---------------------|-------------------|
| Crypto (Solana DEXs) | On-chain swaps, no intermediary | Minimal (no broker-dealer) |
| Stocks | Broker integration required | SEC/FINRA registration |
| Sports betting | State-by-state gambling licenses | Heavy |

Crypto allows MVP validation without regulatory overhead. Multi-asset expansion comes after product-market fit.
