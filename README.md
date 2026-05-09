# 🤖 PolyBot — Algorithmic Prediction Market Trading Engine

> **Status:** Paper-trading mode only · No live funds at risk · Seeking contributors

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> ⚠️ **Risk Warning:** Prediction market trading carries significant financial risk. This software is for research and educational purposes. Past paper-trading results do not guarantee live trading profits.

---

## 🎯 Vision

PolyBot aspires to compete with the most sophisticated algorithmic traders on [Polymarket](https://polymarket.com) — the world's largest decentralised prediction market:

**Reference benchmarks we study:**
- **Theo4** — High-conviction, large-position political expert who made tens of millions on the 2024 US election by using unconventional data (neighbour polling) that outperformed traditional polls. Our lesson: *information edge beats execution speed*
- **Fredi9999 / kch123 / Beachboy4** — Structural arbitrage and market-making bots that capture spread and cross-market price discrepancies at high frequency. Our lesson: *mathematical mispricing is more reliable than outcome prediction*
- **ascetic0x / T-Bot** — Research-driven accounts that focus on niche markets with low liquidity and high information asymmetry. Our lesson: *specialisation in a domain beats general trading*

**What we are building:** A modular engine that supports all three strategies — high-conviction position taking, structural arbitrage, and niche-market specialisation — starting in paper mode and graduating to live trading only after rigorous backtesting.

---

## ✅ What We Have Actually Built

| Component | Status | Notes |
|-----------|--------|-------|
| Polymarket CLOB client | ✅ Working | REST + WebSocket market data feed |
| Paper trader | ✅ Working | Simulates fills, tracks P&L, no real funds |
| Risk manager | ✅ Working | Kelly criterion position sizing, max drawdown circuit breaker, exposure limits |
| Intelligence gatherer | ✅ Working | RSS feeds, LLM summarisation, sentiment scoring |
| Prediction engine | ✅ Scaffold | Gradient boosting model stub, feature pipeline defined |
| Mempool sniper | ✅ Scaffold | On-chain event monitoring hook (Web3) |
| Order executor | ✅ Scaffold | Wired to paper trader, not live CLOB |
| SQLite trade journal | ✅ Working | Every simulated order logged with reasoning |
| Backtesting harness | ❌ Missing | No historical replay engine yet |

---

## ❌ What We Have NOT Yet Achieved

### 1. Profitable Live Trading
The bot has **never traded with real money**. Paper results are promising but unvalidated against live market microstructure (slippage, latency, partial fills, API rate limits).

**Why not yet:** Live trading on Polymarket requires the `py-clob-client` library, a funded wallet, and tested execution logic. We deliberately kept this locked behind paper mode until backtesting proves statistical edge.

### 2. Real Arbitrage Detection
Structural arbitrage (the strategy of Fredi9999-style bots) requires:
- Sub-second price feeds from multiple markets simultaneously
- Cross-platform arbitrage (Polymarket ↔ Kalshi ↔ Manifold)
- Order routing logic that accounts for transaction costs and settlement time

We have the architecture but not the execution speed or multi-platform feed integration.

### 3. High-Conviction Signal Generation
To replicate Theo4's edge we need:
- Proprietary data sources (polling, social sentiment, alternative data)
- Domain expert knowledge encoded as trading rules
- A validated backtesting framework to confirm edge before deployment

### 4. Production-Grade Reliability
No retry logic, no dead-letter queue, no alerting for position drift, no graceful shutdown for open positions.

---

## 🚀 Quick Start (Paper Mode)

```bash
git clone https://github.com/GokulDubbaka/polybot.git
cd polybot
pip install -r polybot/requirements.txt
cp polybot/.env.example polybot/.env    # fill in API keys (read-only for paper mode)
python polybot/main.py --mode paper
```

---

## 🤝 How You Can Help

### 📊 Quant / Strategy
- **Backtesting engine:** Build a historical replay system using Polymarket's public resolution data
- **Arbitrage detection:** Implement real-time cross-market price monitoring between Polymarket and Kalshi
- **Kelly position sizing:** Improve the risk model with dynamic Kelly fraction based on market liquidity depth
- **Signal research:** Identify new information sources (alternative data, on-chain metrics, political intel) that predict market resolution

### 🔧 Engineering
- **Live CLOB integration:** Wire the order executor to `py-clob-client` with proper error handling, retries, and position reconciliation
- **Latency optimisation:** Reduce order-to-fill latency using WebSocket streaming instead of REST polling
- **Multi-market monitoring:** Stream L2 order book updates for 50+ markets simultaneously without exceeding API rate limits

### 🤖 AI / ML
- **LLM market analyst:** Use LLMs to read news articles and output probability estimates for specific market questions
- **Calibration system:** Measure and improve the probability calibration of the prediction engine (Brier score, reliability diagrams)

> Start a Discussion or open an Issue to coordinate. All experience levels welcome.

---

## 📄 License

MIT — see [LICENSE](LICENSE)
