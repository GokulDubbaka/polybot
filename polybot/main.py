"""
POLYBOT — Main Orchestrator
The master controller. Run this file to start the bot.

Usage:
  python main.py           # Run in paper trading mode
  python main.py --live    # Run in live mode (DANGEROUS — real money)
  python main.py --once    # Single scan cycle (good for testing)
"""

import time
import argparse
import traceback
import sys
import io
from datetime import datetime

# Force UTF-8 output on Windows to avoid codec errors
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from config.settings import (
    MARKET_SCAN_INTERVAL_SECS, NEWS_FETCH_INTERVAL_SECS,
    POSITION_CHECK_INTERVAL_SECS, MIN_LIQUIDITY_USD, TRADING_MODE
)
from core.database import init_db, save_snapshot
from core.polymarket_client import PolymarketClient
from core.mempool_sniper import mempool_sniper
from intelligence.gatherer import IntelligenceGatherer
from models.prediction_engine import PredictionEngine
from trading.risk_manager import RiskManager
from trading.paper_trader import PaperTrader


class PolyBot:
    """
    Main bot orchestrator.
    Coordinates all agents in a continuous loop.
    """

    def __init__(self, mode: str = "PAPER"):
        print(f"\n{'='*50}")
        print(f"  POLYBOT v1.0 — {mode} MODE")
        print(f"  Starting: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*50}\n")

        # Initialize database
        init_db()

        # Initialize agents
        self.poly       = PolymarketClient()
        self.intel      = IntelligenceGatherer()
        self.predictor  = PredictionEngine()
        self.risk       = RiskManager(mode=mode)
        self.trader     = PaperTrader(self.risk, self.poly)

        # State
        self.mode       = mode
        self.running    = False
        self.cycle      = 0
        self.last_news  = []
        self.last_news_fetch  = 0
        self.last_market_scan = 0
        self.last_position_check = 0

        print(f"[Bot] All agents initialized ✅")
        print(f"[Bot] Starting capital: ${self.risk.capital:,.0f}")

    # ─────────────────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────────────────

    def run(self, single_cycle: bool = False):
        """Start the main bot loop."""
        self.running = True
        print(f"[Bot] Starting main loop. Press Ctrl+C to stop.\n")

        try:
            while self.running:
                self.cycle += 1
                print(f"\n{'─'*40}")
                print(f"[Bot] Cycle #{self.cycle} — {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'─'*40}")

                # 1. Refresh news (every 2 minutes)
                now = time.time()
                if now - self.last_news_fetch >= NEWS_FETCH_INTERVAL_SECS:
                    self._refresh_news()
                    self.last_news_fetch = now

                # 2. Scan markets and predict (every 60 seconds)
                if now - self.last_market_scan >= MARKET_SCAN_INTERVAL_SECS:
                    self._scan_and_trade()
                    self.last_market_scan = now

                # 3. Monitor open positions (every 30 seconds)
                if now - self.last_position_check >= POSITION_CHECK_INTERVAL_SECS:
                    self._monitor_positions()
                    self.last_position_check = now

                # 4. Portfolio snapshot
                self._snapshot_portfolio()

                # 5. Print status
                self._print_status()

                if single_cycle:
                    print("\n[Bot] Single cycle complete.")
                    break

                time.sleep(15)  # 15s between main loop iterations

        except KeyboardInterrupt:
            print("\n[Bot] Stopped by user.")
        except Exception as e:
            print(f"[Bot] CRITICAL ERROR: {e}")
            traceback.print_exc()
        finally:
            self.trader.session_summary()

    # ─────────────────────────────────────────
    # INTELLIGENCE REFRESH
    # ─────────────────────────────────────────

    def _refresh_news(self):
        """Pull fresh news from all RSS sources."""
        print("[Bot] Fetching news...")
        try:
            self.last_news = self.intel.fetch_rss_news(max_age_hours=4)
            print(f"[Bot] News refreshed: {len(self.last_news)} items")
        except Exception as e:
            print(f"[Bot] News fetch error: {e}")

    # ─────────────────────────────────────────
    # MARKET SCAN
    # ─────────────────────────────────────────

    def _scan_and_trade(self):
        """Scan markets, predict, and enter positions if signal found."""
        print("[Bot] Scanning markets...")

        if self.risk.halted:
            print(f"[Bot] ⛔ HALTED — {self.risk.halt_reason}")
            return

        try:
            # Fetch active markets
            markets = self.poly.get_markets(limit=50)
            if not markets:
                print("[Bot] No markets fetched")
                return

            print(f"[Bot] Analyzing {len(markets)} markets...")

            trade_signals = []
            for market in markets:
                try:
                    signal = self._analyze_market(market)
                    if signal:
                        trade_signals.append(signal)
                except Exception as e:
                    print(f"[Bot] Market analysis error: {e}")
                    continue

                time.sleep(0.5)  # Rate limit on API calls

            # Sort by edge (highest edge first)
            trade_signals.sort(key=lambda x: x["edge"], reverse=True)

            # Execute top signals
            executed = 0
            for signal in trade_signals[:3]:  # Max 3 new trades per cycle
                result = self._execute_signal(signal)
                if result:
                    executed += 1

            print(f"[Bot] Scan complete. Signals: {len(trade_signals)}, Executed: {executed}")

        except Exception as e:
            print(f"[Bot] Scan error: {e}")
            traceback.print_exc()

    def _analyze_market(self, market: dict) -> dict | None:
        """Full analysis pipeline for a single market."""
        # Skip markets with missing prices (non-binary/multi-outcome markets)
        yes_price = market.get("yes_price")
        no_price  = market.get("no_price")
        if yes_price is None or no_price is None:
            return None
        if not (0.01 <= yes_price <= 0.99):
            return None

        # Build context
        context = self.intel.build_market_context(market, self.last_news)
        if not context or not context.get("market_prob_yes"):
            return None
        context["condition_id"] = market["condition_id"]
        
        # [WORLD-CLASS] Mempool Sniping 
        # Attempt to intercept massive pending transactions before analyzing standard models.
        pending_whale_tx = mempool_sniper.scan_mempool(market["condition_id"])
        if pending_whale_tx:
            # If a whale is buying YES, we assume insider knowledge and front-run them immediately.
            direction = "YES" if "BUY_YES" in pending_whale_tx["action"] else "NO"
            mempool_sniper.execute_front_run(pending_whale_tx)
            prediction = {
                "trade_signal": True,
                "direction": direction,
                "confidence": 0.99,
                "edge": 0.20,
                "model_version": "mempool_sniper_v1"
            }
        else:
            # Standard Prediction
            prediction = self.predictor.predict(context)
            
        if not prediction:
            return None

        if not prediction.get("trade_signal"):
            return None

        # Get position sizing
        time_horizon = self.poly.classify_time_horizon(market)
        sizing       = self.risk.calculate_position_size(prediction, time_horizon)

        if not sizing.get("approved"):
            return None

        return {
            "market":     market,
            "prediction": prediction,
            "sizing":     sizing,
            "edge":       prediction.get("edge", 0),
        }

    def _execute_signal(self, signal: dict) -> bool:
        """Execute a validated trade signal."""
        market     = signal["market"]
        prediction = signal["prediction"]
        sizing     = signal["sizing"]

        print(f"\n[Bot] 🎯 SIGNAL FOUND:")
        print(f"  Q: {market['question'][:70]}")
        print(f"  Direction: {prediction['direction']}")
        print(f"  Edge: {prediction['edge']:.1%}")
        print(f"  Confidence: {prediction['confidence']:.1%}")
        print(f"  Size: ${sizing['size_usd']:,.0f}")

        trade = self.trader.enter_trade(market, prediction, sizing)
        return trade is not None

    # ─────────────────────────────────────────
    # POSITION MONITORING
    # ─────────────────────────────────────────

    def _monitor_positions(self):
        """Check all open positions for exits."""
        from core.database import get_open_trades
        open_count = len(get_open_trades())
        if open_count == 0:
            return

        print(f"[Bot] Monitoring {open_count} open position(s)...")
        actions = self.trader.monitor_open_positions()

        if actions:
            for a in actions:
                result = a.get("result", {})
                print(f"[Bot] Position closed: {a['action']} | "
                      f"P&L: ${result.get('pnl_usd', 0):+,.2f}")

    # ─────────────────────────────────────────
    # STATUS & SNAPSHOT
    # ─────────────────────────────────────────

    def _snapshot_portfolio(self):
        """Save portfolio snapshot for charting / analysis."""
        try:
            status = self.risk.get_portfolio_status()
            save_snapshot({
                "total_value":    status["total_capital"],
                "cash_balance":   status["available"],
                "open_positions": status["open_positions"],
                "daily_pnl":      status["daily_pnl"],
                "total_pnl":      status["total_pnl"],
                "sharpe_ratio":   status["sharpe_ratio"],
                "win_rate":       status["win_rate"],
            })
        except Exception:
            pass

    def _print_status(self):
        """Clean status printout every cycle."""
        status = self.risk.get_portfolio_status()
        cal    = self.predictor.get_calibration_report()

        print(f"\n[Status] {status['health']}")
        print(f"  Capital:     ${status['total_capital']:>12,.2f}")
        print(f"  Daily P&L:   ${status['daily_pnl']:>+12,.2f} ({status['daily_pnl_pct']:+.2f}%)")
        print(f"  Total P&L:   ${status['total_pnl']:>+12,.2f} ({status['total_pnl_pct']:+.2f}%)")
        print(f"  Positions:   {status['open_positions']}")
        print(f"  Win Rate:    {status['win_rate']:.1f}% ({status['total_trades']} trades)")
        print(f"  Sharpe:      {status['sharpe_ratio']:.2f}")
        print(f"  Brier Score: {cal.get('brier_score', 'N/A')} {cal.get('model_status', '')}")


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PolyBot — Prediction Market Trading Bot")
    parser.add_argument("--live",  action="store_true", help="Enable live trading (USE WITH CAUTION)")
    parser.add_argument("--once",  action="store_true", help="Run a single scan cycle")
    args = parser.parse_args()

    if args.live:
        print("⚠️  WARNING: LIVE MODE ENABLED — Real money at risk")
        confirm = input("Type 'CONFIRM LIVE' to proceed: ")
        if confirm != "CONFIRM LIVE":
            print("Cancelled.")
            exit(0)
        mode = "LIVE"
    else:
        mode = "PAPER"

    bot = PolyBot(mode=mode)
    bot.run(single_cycle=args.once)
