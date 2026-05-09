# POLYBOT 🤖 — Polymarket AI Trading Bot

Your personal AI-powered prediction market bot.  
Paper trades with real data. Zero real money until YOU say go.

---

## ⚡ QUICKSTART (5 Minutes)

### 1. Install Python 3.10+
Download from https://python.org if you don't have it.

### 2. Get your free Anthropic API key
Sign up at https://console.anthropic.com
Free tier gives you enough for testing (~$5 free credits)

### 3. Setup the bot
```bash
# Clone/download this folder, then:
cd polybot

# Install dependencies
pip install -r requirements.txt

# Create your config
cp .env.example .env

# Edit .env and add your Anthropic API key
# (open .env in any text editor)
```

### 4. Run the bot
```bash
# Paper trading mode (safe — no real money)
python main.py

# Single test cycle (good for first run)
python main.py --once
```

---

## 💰 REAL COST TO RUN THIS BOT

| Item | Cost |
|------|------|
| Anthropic API (Claude Haiku) | ~$0.25 per 1000 screen calls |
| Anthropic API (Claude Sonnet) | ~$3.00 per 1000 deep analyses |
| All data (RSS, Reddit, Metaculus, Manifold) | **FREE** |
| Database (SQLite local) | **FREE** |
| Your laptop electricity | ~$0.01/day |
| **Estimated monthly cost** | **$20–80/month** |

---

## 🏗️ PROJECT STRUCTURE

```
polybot/
├── main.py                    # ← START HERE. Run this.
├── requirements.txt
├── .env.example               # Copy to .env and fill in keys
│
├── config/
│   └── settings.py            # All bot parameters (tune here)
│
├── core/
│   ├── database.py            # SQLite storage layer
│   └── polymarket_client.py   # Polymarket API wrapper
│
├── intelligence/
│   └── gatherer.py            # News, Reddit, Metaculus, Manifold
│
├── models/
│   └── prediction_engine.py   # Claude AI prediction + calibration
│
├── trading/
│   ├── risk_manager.py        # Capital allocation + kill switches
│   └── paper_trader.py        # Simulated trade execution
│
└── data/
    └── polybot.db             # Auto-created SQLite database
```

---

## ⚙️ HOW THE BOT WORKS

```
Every 60 seconds:
  1. Fetch RSS news from 7 sources (Reuters, BBC, Politico, etc.)
  2. Scan 50 active Polymarket markets
  
  For each market:
  3. Score news relevance to that market
  4. Check Metaculus + Manifold for expert forecasts
  5. Detect divergence: where does Polymarket disagree with experts?
  6. Claude Haiku screens the market (cheap, fast)
  7. Claude Sonnet deep-analyzes promising markets (expensive, thorough)
  8. If edge > 8% AND confidence > 72% → calculate position size
  9. Kelly Criterion + risk matrix determines exact dollar amount
  10. Paper trade opened at real market price

Every 30 seconds:
  - Monitor open positions
  - Auto-exit on: +50% gain, -30% loss, market resolved, time expired

Continuously:
  - Track Brier Score (calibration quality)
  - Portfolio snapshots for charting
  - Kill switch: halt if daily drawdown > 5%
```

---

## 🎯 KEY PARAMETERS (in config/settings.py)

| Parameter | Default | What it does |
|-----------|---------|--------------|
| MIN_EDGE_THRESHOLD | 8% | Min gap between model and market to trade |
| MIN_CONFIDENCE | 72% | Min Claude confidence to enter trade |
| MAX_SINGLE_POSITION_PCT | 3% | Max $ per trade |
| DAILY_DRAWDOWN_KILL_PCT | 5% | Auto-halt threshold |
| CASH_RESERVE_PCT | 15% | Always keep in reserve |

---

## 📊 PHASES

**Phase 1 — NOW (Paper Trading)**
Run for 2 months. Need 200+ trades. Target: win rate > 60%.

**Phase 2 — Micro Live ($1,000 real)**
If Phase 1 hits targets. Add wallet private key to .env.

**Phase 3 — Scale Up**
Gradually increase capital based on Sharpe ratio performance.

---

## 🚨 IMPORTANT WARNINGS

1. **This is experimental software.** Prediction markets are risky.
2. **Paper trade for at least 2 months** before touching real money.
3. **The bot is NOT 100% accurate.** No bot is. Target is edge, not perfection.
4. **Polymarket may block IPs** in certain countries (US included). Use VPN if needed.
5. **Monitor the bot regularly.** Don't set and forget, especially in Phase 2+.

---

## 🔜 COMING NEXT (Future Sessions)

- [ ] Reinforcement learning self-improvement loop
- [ ] Web dashboard (Flask) for visual monitoring  
- [ ] Multi-agent specialist models per market category
- [ ] Arbitrage detector (Polymarket vs Kalshi vs Manifold)
- [ ] Telegram alerts for signals and P&L
- [ ] Backtesting engine on historical market data

---

## 🆘 TROUBLESHOOTING

**"No markets fetched"** → Check your internet connection. Polymarket API is free and public.

**"API key invalid"** → Recheck your ANTHROPIC_API_KEY in .env file.

**"Module not found"** → Run `pip install -r requirements.txt` again.

**Bot makes no trades** → Normal at first. Markets need sufficient news coverage + divergence.
Try lowering MIN_EDGE_THRESHOLD to 0.05 in settings.py to see more signals.
