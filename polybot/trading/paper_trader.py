"""
POLYBOT — Paper Trader
Simulates trades against real Polymarket prices.
Your money never moves until YOU flip the mode to LIVE.
"""

from datetime import datetime, timezone
from core.database import open_trade, close_trade, get_open_trades, save_rl_experience
from core.polymarket_client import PolymarketClient
from config.settings import TRADING_MODE


class PaperTrader:
    """
    Paper trading engine — 100% real data, 0% real money.
    Tracks performance identically to how live trading would behave.
    """

    def __init__(self, risk_manager, poly_client: PolymarketClient):
        self.risk     = risk_manager
        self.poly     = poly_client
        self.mode     = TRADING_MODE  # PAPER by default
        self.trade_log= []

    # ─────────────────────────────────────────
    # ENTER TRADE
    # ─────────────────────────────────────────

    def enter_trade(self, market: dict, prediction: dict,
                     sizing: dict) -> dict | None:
        """
        Open a paper position. Records entry at current real market price.
        """
        if self.mode == "LIVE":
            print("[Trader] ⚠️  LIVE MODE — real money would be used here")
            # TODO: Add actual Polymarket order execution
            return None

        direction    = prediction["direction"]
        entry_price  = (market["yes_price"] if direction == "YES"
                        else market["no_price"])

        if not entry_price or entry_price <= 0:
            print(f"[Trader] Invalid entry price for {market['condition_id']}")
            return None

        size_usd = sizing["size_usd"]
        shares   = size_usd / entry_price

        # Simulate slippage on large orders
        orderbook = self.poly.get_orderbook(
            market.get("yes_token_id", "") if direction == "YES"
            else market.get("no_token_id", "")
        )
        # Simple inline slippage estimate: 0.5% for orders under $1k, 1% above
        slippage = 0.005 if size_usd < 1000 else 0.01
        if slippage > 0.05:
            print(f"[Trader] Skipping — slippage too high: {slippage:.1%}")
            return None

        # Adjust entry for slippage
        effective_entry = entry_price * (1 + slippage)

        trade = {
            "condition_id": market["condition_id"],
            "prediction_id":prediction.get("prediction_id"),
            "direction":     direction,
            "time_horizon":  sizing["time_horizon"],
            "risk_level":    sizing["risk_level"],
            "entry_price":   round(effective_entry, 5),
            "size_usd":      round(size_usd, 2),
            "shares":        round(shares, 4),
            "mode":          self.mode,
            "category":      market.get("category", "other"),
        }

        trade_id = open_trade(trade)
        trade["id"] = trade_id

        print(f"[Trader] 📈 PAPER TRADE OPENED")
        print(f"  Market:  {market['question'][:60]}")
        print(f"  Side:    {direction} @ {effective_entry:.3f}")
        print(f"  Size:    ${size_usd:,.0f} ({shares:.1f} shares)")
        print(f"  Edge:    {prediction.get('edge',0):.1%}")
        print(f"  Conf:    {prediction.get('confidence',0):.1%}")

        self.trade_log.append(trade)
        return trade

    # ─────────────────────────────────────────
    # EXIT TRADE
    # ─────────────────────────────────────────

    def exit_trade(self, trade: dict, reason: str = "signal") -> dict | None:
        """Close a paper position at current market price."""
        market = self.poly.get_market(trade["condition_id"])
        if not market:
            print(f"[Trader] Can't exit — market not found: {trade['condition_id']}")
            return None

        direction   = trade["direction"]
        exit_price  = (market["yes_price"] if direction == "YES"
                       else market["no_price"])

        if not exit_price:
            return None

        # Calculate P&L locally
        entry_price = trade.get("entry_price", exit_price)
        shares      = trade.get("shares",
                        trade.get("size_usd", 0) / max(entry_price, 0.0001))
        pnl_usd     = (exit_price - entry_price) * shares
        pnl_pct     = (exit_price - entry_price) / max(entry_price, 0.0001) * 100

        close_trade(trade["id"], exit_price, round(pnl_usd, 2), reason)
        self.risk.record_trade_result(pnl_usd)

        result = {"pnl_usd": pnl_usd, "pnl_pct": pnl_pct, "exit_price": exit_price}

        status = "✅ WIN" if pnl_usd > 0 else "❌ LOSS"
        print(f"[Trader] {status} TRADE CLOSED")
        print(f"  Market:  {market['question'][:60]}")
        print(f"  P&L:     ${result['pnl_usd']:+,.2f} ({result['pnl_pct']:+.1f}%)")
        print(f"  Reason:  {reason}")

        return result

    # ─────────────────────────────────────────
    # POSITION MONITORING
    # ─────────────────────────────────────────

    def monitor_open_positions(self) -> list[dict]:
        """
        Check all open positions for exit signals:
        - Market resolving
        - Stop loss hit
        - Target reached
        - Time decay
        """
        open_trades = get_open_trades()
        actions     = []

        for trade in open_trades:
            market = self.poly.get_market(trade["condition_id"])
            if not market:
                continue

            direction   = trade["direction"]
            entry_price = trade["entry_price"]
            current_price = (market["yes_price"] if direction == "YES"
                             else market["no_price"])

            if not current_price:
                continue

            unrealized_pnl_pct = (current_price - entry_price) / entry_price * 100

            # 1. Market resolved (price at 0.99 or 0.01)
            if current_price >= 0.99:
                result = self.exit_trade(trade, reason="market_resolved_win")
                actions.append({"trade": trade, "action": "WIN_EXIT", "result": result})
                continue

            if current_price <= 0.01:
                result = self.exit_trade(trade, reason="market_resolved_loss")
                actions.append({"trade": trade, "action": "LOSS_EXIT", "result": result})
                continue

            # 2. Take profit: +50% on position
            if unrealized_pnl_pct >= 50:
                result = self.exit_trade(trade, reason="take_profit_50pct")
                actions.append({"trade": trade, "action": "TAKE_PROFIT", "result": result})
                continue

            # 3. Stop loss: -30% on position
            if unrealized_pnl_pct <= -30:
                result = self.exit_trade(trade, reason="stop_loss_30pct")
                actions.append({"trade": trade, "action": "STOP_LOSS", "result": result})
                continue

            # 4. Time-based exit check
            time_horizon = trade.get("time_horizon", "1day")
            opened_at    = datetime.fromisoformat(trade["opened_at"])
            age_hours    = (datetime.now(timezone.utc) - opened_at.replace(
                            tzinfo=timezone.utc)).total_seconds() / 3600

            horizon_hours = {"5min": 0.083, "15min": 0.25, "4hour": 4,
                             "1day": 24, "1week": 168}
            max_age = horizon_hours.get(time_horizon, 24) * 1.5  # 1.5x grace period

            if age_hours > max_age:
                result = self.exit_trade(trade, reason="time_expired")
                actions.append({"trade": trade, "action": "TIME_EXIT", "result": result})

        return actions

    # ─────────────────────────────────────────
    # SESSION SUMMARY
    # ─────────────────────────────────────────

    def session_summary(self) -> dict:
        """Print a clean summary of today's trades."""
        from core.database import get_trade_stats
        stats = get_trade_stats()

        summary = {
            "mode":       self.mode,
            "timestamp":  datetime.now().isoformat(),
            **stats,
            "capital":    self.risk.capital,
        }

        print("\n" + "═"*50)
        print("  POLYBOT SESSION SUMMARY")
        print("═"*50)
        print(f"  Mode:        {self.mode}")
        print(f"  Capital:     ${self.risk.capital:>12,.2f}")
        print(f"  Total Trades:{stats.get('total', 0):>6}")
        print(f"  Win Rate:    {stats.get('win_rate', 0):>6.1f}%")
        print(f"  Total P&L:   ${stats.get('total_pnl', 0):>+12,.2f}")
        print(f"  Best Trade:  ${stats.get('best_trade', 0):>+12,.2f}")
        print(f"  Worst Trade: ${stats.get('worst_trade', 0):>+12,.2f}")
        print("═"*50 + "\n")

        return summary
