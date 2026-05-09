<div align="center">

# 🤖 PolyBot

**AI-powered prediction market trading engine for Polymarket.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Claude AI](https://img.shields.io/badge/Powered%20by-Claude%20AI-orange)](https://anthropic.com)
[![Trading Mode](https://img.shields.io/badge/Default%20Mode-Paper%20Trading-yellow)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

*Scan → Predict → Size → Execute → Monitor — all autonomously.*

[Features](#-features) · [Architecture](#-architecture) · [Quick Start](#-quick-start) · [Configuration](#-configuration) · [Disclaimer](#-disclaimer)

</div>

---

## ✨ Features

- 📡 **Real-time market scanning** — Continuously monitors 50+ active Polymarket prediction markets
- 🧠 **LLM intelligence** — Uses Claude (claude-opus) for deep probabilistic reasoning on each market
- 📰 **Multi-source signal fusion** — RSS news, Reddit sentiment, Metaculus calibration data, Manifold Markets
- 📊 **Brier Score calibration** — Tracks model accuracy over rolling window; halts if accuracy degrades
- 💰 **Dynamic position sizing** — Capital allocation matrix across 5 time horizons × 3 risk levels
- 🛡️ **Multi-layer risk management** — Daily drawdown kill switch, category exposure caps, liquidity filters
- 📄 **Paper trading mode** — Full simulation with P&L tracking, Sharpe ratio, win rate — no real money needed
- 🔁 **Live trading mode** — Real execution on Polymarket CLOB with private key (use with caution)

---

## 🏗️ Architecture

```
polybot/
├── main.py                   # 🚀 Entry point — PolyBot orchestrator
├── config/
│   └── settings.py           # All configuration (loaded from .env)
├── core/
│   ├── database.py           # SQLite persistence (trades, snapshots)
│   └── polymarket_client.py  # Polymarket CLOB & Gamma API client
├── intelligence/
│   └── gatherer.py           # News RSS, Reddit, Metaculus data fusion
├── models/
│   └── prediction_engine.py  # Claude LLM prediction + Brier calibration
├── trading/
│   ├── risk_manager.py       # Position sizing, drawdown, exposure limits
│   └── paper_trader.py       # Paper trade execution & position monitoring
└── data/
    └── polybot.db            # SQLite database (auto-created)
```

**Full cycle flow:**

```
News RSS + Reddit + Metaculus
          ↓
    IntelligenceGatherer
          ↓
    PredictionEngine (Claude LLM)
    → probability estimate
    → edge calculation
    → trade signal
          ↓
    RiskManager
    → position sizing
    → exposure checks
    → kill switch check
          ↓
    PaperTrader / LiveTrader
    → order execution
    → position monitoring
    → P&L tracking
```

---

## ⚡ Quick Start

### Prerequisites
- Python 3.10+
- An Anthropic API key ([get one here](https://console.anthropic.com))

### Install

```bash
git clone https://github.com/YOUR_USERNAME/polybot.git
cd polybot

# Install dependencies
pip install -r polybot/requirements.txt

# Configure environment
cp polybot/.env.example polybot/.env
# Edit polybot/.env with your API keys
```

### Run (Paper Trading — No Real Money)

```bash
cd polybot
python main.py
```

### Run a single test cycle

```bash
python main.py --once
```

### Live Trading (Real Money — Use With Extreme Caution)

```bash
python main.py --live
# You will be prompted to type 'CONFIRM LIVE' to proceed
```

---

## ⚙️ Configuration

Copy `polybot/.env.example` to `polybot/.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Yes | Your Anthropic Claude API key |
| `OPENAI_API_KEY` | Optional | Fallback LLM (not required) |
| `POLYMARKET_PRIVATE_KEY` | Live mode only | Your Polymarket wallet private key |
| `TRADING_MODE` | No | `PAPER` (default) or `LIVE` |

All risk parameters (`MAX_SINGLE_POSITION_PCT`, `DAILY_DRAWDOWN_KILL_PCT`, etc.) can be tuned in `polybot/config/settings.py`.

---

## 📈 Trading Logic

1. **Market Discovery** — Fetches 50 active binary markets from Polymarket CLOB every 60 seconds
2. **Context Building** — Matches each market against recent news headlines using keyword similarity
3. **LLM Prediction** — Sends market question + news context to Claude for probabilistic reasoning
4. **Edge Calculation** — `edge = |model_prob - market_prob|`. Only trades when edge ≥ 8%
5. **Risk Gating** — Position must pass liquidity, exposure, and drawdown checks
6. **Execution** — Paper trader logs the trade; live trader submits to Polymarket CLOB
7. **Monitoring** — Open positions checked every 30s; auto-exit on resolve or stop loss

---

## 🛡️ Risk Management

| Parameter | Default | Description |
|---|---|---|
| Max single position | 3% | Max % of capital per trade |
| Max category exposure | 20% | Max across one market category |
| Daily drawdown kill | 5% | Bot halts if daily loss exceeds this |
| Min edge | 8% | Minimum model vs. market probability gap |
| Min confidence | 72% | Minimum model confidence to enter |
| Min liquidity | $5,000 | Skip illiquid markets |
| Cash reserve | 15% | Always kept as dry powder |

---

## ⚠️ Disclaimer

This software is for **educational and research purposes only**. Prediction market trading involves significant financial risk. Past performance does not guarantee future results. **Never trade with money you cannot afford to lose.** The authors accept no responsibility for financial losses.

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📄 License

MIT — see [LICENSE](LICENSE)
