# 🚀 Solana Meme Coin Trading Bots

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.13+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Solana](https://img.shields.io/badge/Solana-9945ff?style=for-the-badge&logo=solana&logoColor=white)](https://solana.com)
[![Jupiter](https://img.shields.io/badge/Jupiter-00D4AA?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMTIgMjJDMTcuNTIyOCAyMiAyMiAxNy41MjI4IDIyIDEyQzIyIDYuNDc3MTUgMTcuNTIyOCAyIDEyIDJDNi40NzcxNSAyIDIgNi40NzcxNSAyIDEyQzIgMTcuNTIyOCA2LjQ3NzE1IDIyIDEyIDIyWiIgZmlsbD0iIzAwRDRBQSIvPjwvc3ZnPg==)](https://jup.ag)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge)](https://github.com/psf/black)

*Automated trading infrastructure for Solana meme coins with real-time monitoring, copy trading capabilities, and risk management.*

</div>

## 📊 Overview

This project implements multiple trading strategies, real-time market monitoring, and robust risk management.



## ✨ Features

### 🤖 Trading Strategies
- **Copy Trading**: Mirror whale wallet transactions with intelligent position sizing
- **Time-Based Execution**: Automated trading at predetermined times (Solambo strategy)
- **Signal-Based Trading**: Telegram channel integration for community-driven trades
- **Manual Override**: Keyboard controls for real-time intervention

### 🔐 Wallet Management
- **HD Wallet Support**: Generate unlimited wallets from a single mnemonic phrase
- **Multi-Wallet Architecture**: Separate base and trading wallets for security
- **Automated Transfers**: Smart fund allocation and profit extraction

### 📡 Real-Time Monitoring
- **Wallet Listeners**: Track transaction signatures and balance changes
- **Telegram Integration**: Process signals from multiple channels
- **Market Data**: Jupiter API integration for quotes and liquidity analysis

### 🛡️ Risk Management
- **Position Sizing**: Automated allocation based on portfolio percentage
- **Stop Losses**: Configurable percentage-based exits
- **Take Profits**: Partial and full profit-taking strategies
- **Slippage Protection**: Dynamic slippage adjustment under market stress

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- Solana wallet with SOL for trading
- API keys for Helius, Jupiter, and Telegram (optional)

### Installation

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Set up pre-commit hooks
pre-commit install
```

### Configuration

1. **Environment Setup**:
```bash
# Edit .env with your API keys and mnemonic phrases (see below)
```

2. **Generate Wallet Mnemonic**:
```bash
python scripts/create_mnemonic_phrase.py
```

3. **Telegram Setup** (Optional):
```bash
python scripts/telegram_setup.py
```


## 🏗️ Architecture

### Core Components

```
src/
├── blockchain.py          # Solana RPC interactions & Jupiter integration
├── wallet/               # HD wallet management & operations
├── strategy/             # Trading strategies & risk management
├── listeners/            # Real-time monitoring (WebSocket, Telegram)
├── polling/              # Market data collection
├── db/                   # Database integrations (Supabase, SQLite)
└── utils/                # Utilities & helpers
```

### Bot Implementations

```
bots/
├── solambo.py           # Telegram pump-dump strategy
├── test_bot.py          # Strategy testing & validation
└── copy_trader.py       # Whale wallet copy trading
```




## 📚 Documentation

### Trading Strategies

#### 1. Copy Trading
Mirror whale wallet transactions with intelligent scaling based on portfolio size:

```python
from src.strategy.copy_trader import CopyTradeExecutor

executor = CopyTradeExecutor(
    whale_wallet_address="...",
    bot_wallet=wallet_manager,
    slippage_bps=300,
    simulation_mode=False
)
```

#### 2. Signal-Based Trading
Process Telegram signals with deduplication and risk management:

```python
from src.listeners.telegram_listener import TelegramListener

listener = TelegramListener(
    channels=["@crypto_signals"],
    on_message=process_signal
)
```

### Risk Management
Configure sophisticated exit conditions:

```python
exit_rules = ExitRules(
    max_duration_s=600,      # Maximum hold time
    take_half_at=30,         # Take 50% profit at 30% gain
    take_all_at=100,         # Exit completely at 100% gain
    stop_out_at=-25,         # Stop loss at 25% loss
    polling_interval=5       # Check every 5 seconds
)
```

## Examples


### Transaction Analysis
```python
# Analyze wallet transactions
from src.transaction_parser import parse_transaction, classify_transaction

tx_data = await get_transaction_json(signature)
tx_type = classify_transaction(tx_data)
parsed_txs = parse_transaction(tx_data)
```

### Market Data Collection
```python
# Set up automated quote polling
from src.polling.quote_poller import QuotePoller

poller = QuotePoller(
    input_mint=SOL,
    output_mint=target_token,
    input_amount=1_000_000_000,  # 1 SOL
    duration_s=3600,             # 1 hour
    save_callback=save_to_database
)
```

