"""
POLYBOT — Configuration Settings
All keys loaded from environment variables. Never hardcode keys.
"""

import os
from dataclasses import dataclass, field
from typing import Dict

# ─────────────────────────────────────────
# API KEYS  (set these in your .env file)
# ─────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")       # Required
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")          # Optional fallback

# ─────────────────────────────────────────
# POLYMARKET
# ─────────────────────────────────────────
POLYMARKET_HOST       = "https://clob.polymarket.com"
POLYMARKET_GAMMA_HOST = "https://gamma-api.polymarket.com"
POLYMARKET_WALLET_PK  = os.getenv("POLYMARKET_PRIVATE_KEY", "")  # For live trading only

# ─────────────────────────────────────────
# TRADING MODE
# ─────────────────────────────────────────
TRADING_MODE = os.getenv("TRADING_MODE", "PAPER")   # PAPER | LIVE
STARTING_PAPER_CAPITAL = 10_000_000.0                # $10M paper capital

# ─────────────────────────────────────────
# RISK PARAMETERS
# ─────────────────────────────────────────
MAX_SINGLE_POSITION_PCT   = 0.03    # 3% of capital max per trade
MAX_CATEGORY_EXPOSURE_PCT = 0.20    # 20% per market category
DAILY_DRAWDOWN_KILL_PCT   = 0.05    # 5% daily loss = halt all trading
MIN_EDGE_THRESHOLD        = 0.08    # Min 8% edge (model_prob - market_prob)
MIN_CONFIDENCE            = 0.72    # Min model confidence to enter trade
MIN_LIQUIDITY_USD         = 5000    # Skip markets below $5K liquidity

# ─────────────────────────────────────────
# CAPITAL ALLOCATION MATRIX
# {(time_horizon, risk_level): portfolio_pct}
# ─────────────────────────────────────────
CAPITAL_MATRIX: Dict[tuple, float] = {
    ("5min",   "low"):    0.02,
    ("5min",   "medium"): 0.01,
    ("5min",   "high"):   0.005,
    ("15min",  "low"):    0.03,
    ("15min",  "medium"): 0.02,
    ("15min",  "high"):   0.01,
    ("4hour",  "low"):    0.08,
    ("4hour",  "medium"): 0.05,
    ("4hour",  "high"):   0.03,
    ("1day",   "low"):    0.10,
    ("1day",   "medium"): 0.07,
    ("1day",   "high"):   0.04,
    ("1week",  "low"):    0.12,
    ("1week",  "medium"): 0.08,
    ("1week",  "high"):   0.05,
}
CASH_RESERVE_PCT = 0.15   # Always keep 15% as dry powder

# ─────────────────────────────────────────
# INTELLIGENCE SOURCES
# ─────────────────────────────────────────
RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/topNews",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.cnn.com/rss/edition.rss",
    "https://feeds.npr.org/1001/rss.xml",
    "https://www.politico.com/rss/politicopicks.xml",
    "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "https://cryptopanic.com/news/rss/",
]

REDDIT_SUBREDDITS = [
    "politics", "worldnews", "economics", "PredictionMarkets",
    "geopolitics", "investing", "wallstreetbets", "Crypto",
    "sports", "nba", "nfl", "soccer"
]

# Metaculus API (free, excellent calibration source)
METACULUS_API = "https://www.metaculus.com/api2/questions/"

# Manifold Markets API (free)
MANIFOLD_API = "https://api.manifold.markets/v0"

# ─────────────────────────────────────────
# MODEL SETTINGS
# ─────────────────────────────────────────
LLM_MODEL          = "claude-opus-4-6"   # Primary intelligence model
LLM_FAST_MODEL     = "claude-haiku-4-5-20251001"  # Fast/cheap for screening
MAX_TOKENS         = 2000
BRIER_SCORE_WINDOW = 100     # Last N predictions for calibration tracking
MIN_BRIER_SCORE    = 0.25    # Above this = model degraded, alert triggered

# ─────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "../data/polybot.db")

# ─────────────────────────────────────────
# SCAN INTERVALS
# ─────────────────────────────────────────
MARKET_SCAN_INTERVAL_SECS    = 60      # Scan for new markets every 60s
NEWS_FETCH_INTERVAL_SECS     = 120     # Fetch news every 2 min
POSITION_CHECK_INTERVAL_SECS = 30     # Check open positions every 30s
RL_TRAIN_INTERVAL_TRADES     = 50     # Retrain RL every 50 trades
