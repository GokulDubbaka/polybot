"""
POLYBOT — Risk Manager & Capital Allocator
Manages portfolio risk, position sizing, drawdown protection, and kill switches.
"""

from datetime import datetime, timezone, date
from config.settings import (
    STARTING_PAPER_CAPITAL, MAX_SINGLE_POSITION_PCT, MAX_CATEGORY_EXPOSURE_PCT,
    DAILY_DRAWDOWN_KILL_PCT, CASH_RESERVE_PCT, CAPITAL_MATRIX
)
from core.database import get_open_trades, get_trade_stats, get_snapshots


class RiskManager:
    """
    Portfolio risk guardian.
    Every trade must pass through this before execution.
    """

    def __init__(self, mode: str = "PAPER"):
        self.mode             = mode
        self.capital          = STARTING_PAPER_CAPITAL
        self.day_start_value  = STARTING_PAPER_CAPITAL
        self.halted           = False
        self.halt_reason      = ""
        self.daily_pnl        = 0.0
        self.last_reset_date  = date.today()

    # ─────────────────────────────────────────
    # DAILY RESET
    # ─────────────────────────────────────────

    def daily_reset(self):
        """Reset daily P&L counter at market open."""
        today = date.today()
        if today != self.last_reset_date:
            self.day_start_value = self.capital
            self.daily_pnl       = 0.0
            self.last_reset_date = today
            if self.halted:
                print("[Risk] Daily reset — clearing halt from yesterday")
                self.halted      = False
                self.halt_reason = ""
            print(f"[Risk] New day. Starting capital: ${self.capital:,.2f}")

    # ─────────────────────────────────────────
    # POSITION SIZING
    # ─────────────────────────────────────────

    def calculate_position_size(self, prediction: dict,
                                  time_horizon: str) -> dict:
        """
        Determine exactly how much to allocate to a trade.
        Uses: Capital Matrix + Kelly Criterion + Risk Limits
        """
        if self.halted:
            return {"approved": False, "reason": f"Bot halted: {self.halt_reason}"}

        risk_level    = prediction.get("risk_level", "high")
        kelly_fraction= prediction.get("kelly_fraction", 0.01)
        edge          = prediction.get("edge", 0)

        # 1. Get base allocation from Capital Matrix
        matrix_key    = (time_horizon, risk_level)
        base_pct      = CAPITAL_MATRIX.get(matrix_key, 0.01)

        # 2. Kelly-adjusted size
        kelly_size    = self.capital * kelly_fraction

        # 3. Matrix-based max size
        matrix_size   = self.capital * base_pct

        # 4. Hard maximum per trade
        max_size      = self.capital * MAX_SINGLE_POSITION_PCT

        # 5. Take the minimum of all three (conservative)
        position_size = min(kelly_size, matrix_size, max_size)

        # 6. Reserve check — never go below 15% cash
        available     = self.get_available_capital()
        if position_size > available:
            position_size = available * 0.5  # Use half of available

        if position_size < 100:  # Minimum trade size $100
            return {"approved": False, "reason": "Position too small (<$100)"}

        # 7. Category exposure check
        category_check = self._check_category_exposure(
            prediction.get("category", "other"), position_size
        )
        if not category_check["ok"]:
            return {"approved": False, "reason": category_check["reason"]}

        return {
            "approved":      True,
            "size_usd":      round(position_size, 2),
            "size_pct":      round(position_size / self.capital * 100, 3),
            "kelly_fraction":kelly_fraction,
            "risk_level":    risk_level,
            "time_horizon":  time_horizon,
            "method":        "kelly+matrix+hardcap",
        }

    def get_available_capital(self) -> float:
        """Capital available for new trades (after reserves)."""
        open_trades = get_open_trades()
        locked      = sum(t.get("size_usd", 0) for t in open_trades)
        reserve     = self.capital * CASH_RESERVE_PCT
        return max(0, self.capital - locked - reserve)

    def _check_category_exposure(self, category: str,
                                   new_size: float) -> dict:
        """Ensure no single category exceeds 20% of portfolio."""
        open_trades = get_open_trades()
        cat_exposure = sum(
            t.get("size_usd", 0)
            for t in open_trades
            if t.get("category") == category
        )
        max_allowed = self.capital * MAX_CATEGORY_EXPOSURE_PCT
        if cat_exposure + new_size > max_allowed:
            return {
                "ok":    False,
                "reason":f"Category '{category}' at limit: ${cat_exposure:,.0f}/{max_allowed:,.0f}"
            }
        return {"ok": True}

    # ─────────────────────────────────────────
    # P&L TRACKING
    # ─────────────────────────────────────────

    def record_trade_result(self, pnl_usd: float):
        """Update capital and daily P&L after trade closes."""
        self.capital   += pnl_usd
        self.daily_pnl += pnl_usd

        print(f"[Risk] Trade result: ${pnl_usd:+,.2f} | Capital: ${self.capital:,.2f}")

        # Check kill switches
        self._check_kill_switches()

    def _check_kill_switches(self):
        """Auto-halt if drawdown thresholds are breached."""
        # Daily drawdown check
        daily_drawdown = (self.capital - self.day_start_value) / self.day_start_value
        if daily_drawdown <= -DAILY_DRAWDOWN_KILL_PCT:
            self.halted      = True
            self.halt_reason = f"Daily drawdown {daily_drawdown:.1%} exceeded {DAILY_DRAWDOWN_KILL_PCT:.0%} limit"
            print(f"[Risk] 🚨 KILL SWITCH TRIGGERED: {self.halt_reason}")
            return

        # All-time drawdown check (20%)
        peak = STARTING_PAPER_CAPITAL  # In production, track rolling peak
        total_drawdown = (self.capital - peak) / peak
        if total_drawdown <= -0.20:
            self.halted      = True
            self.halt_reason = f"Total drawdown {total_drawdown:.1%} exceeded 20% limit"
            print(f"[Risk] 🚨 KILL SWITCH TRIGGERED: {self.halt_reason}")

    # ─────────────────────────────────────────
    # PORTFOLIO HEALTH
    # ─────────────────────────────────────────

    def get_portfolio_status(self) -> dict:
        """Full portfolio health snapshot."""
        self.daily_reset()
        open_trades = get_open_trades()
        stats       = get_trade_stats()

        locked_capital = sum(t.get("size_usd", 0) for t in open_trades)
        available      = self.get_available_capital()

        # Sharpe ratio (simplified)
        snapshots  = get_snapshots(limit=30)
        sharpe     = self._calc_sharpe(snapshots)

        daily_pnl_pct = (self.daily_pnl / self.day_start_value * 100) if self.day_start_value > 0 else 0
        total_pnl     = self.capital - STARTING_PAPER_CAPITAL
        total_pnl_pct = (total_pnl / STARTING_PAPER_CAPITAL * 100)

        return {
            "mode":            self.mode,
            "total_capital":   round(self.capital, 2),
            "available":       round(available, 2),
            "locked_in_trades":round(locked_capital, 2),
            "daily_pnl":       round(self.daily_pnl, 2),
            "daily_pnl_pct":   round(daily_pnl_pct, 2),
            "total_pnl":       round(total_pnl, 2),
            "total_pnl_pct":   round(total_pnl_pct, 2),
            "open_positions":  len(open_trades),
            "win_rate":        round(stats.get("win_rate", 0), 1),
            "total_trades":    stats.get("total", 0),
            "sharpe_ratio":    round(sharpe, 2),
            "is_halted":       self.halted,
            "halt_reason":     self.halt_reason,
            "health":          "🔴 HALTED" if self.halted
                               else "🟢 HEALTHY" if daily_pnl_pct >= 0
                               else "🟡 CAUTION",
        }

    def _calc_sharpe(self, snapshots: list) -> float:
        """Simplified Sharpe ratio from recent snapshots."""
        if len(snapshots) < 5:
            return 0.0
        returns = []
        for i in range(1, len(snapshots)):
            prev = snapshots[i]["total_value"]
            curr = snapshots[i-1]["total_value"]
            if prev > 0:
                returns.append((curr - prev) / prev)
        if not returns:
            return 0.0
        avg    = sum(returns) / len(returns)
        if len(returns) < 2:
            return 0.0
        variance = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
        std_dev  = variance ** 0.5
        if std_dev == 0:
            return 0.0
        return avg / std_dev * (252 ** 0.5)  # Annualized

    # ─────────────────────────────────────────
    # RL REWARD CALCULATOR
    # ─────────────────────────────────────────

    def calculate_rl_reward(self, trade: dict, prediction: dict) -> float:
        """
        RL reward function — punishes bad DECISIONS, not bad luck.
        This is the core of the self-improvement mechanism.
        """
        pnl_pct       = trade.get("pnl_pct", 0) / 100
        edge          = prediction.get("edge", 0)
        confidence    = prediction.get("confidence", 0.5)
        brier_contrib = (prediction.get("model_prob_yes", 0.5) -
                         (1 if trade.get("outcome") == "WIN" else 0)) ** 2

        # Reward components
        process_score  = edge * 0.4 + confidence * 0.3  # Was the decision sound?
        outcome_score  = pnl_pct * 0.3                   # Did it actually make money?
        calibration_penalty = -brier_contrib * 0.1        # Was probability estimate good?

        reward = process_score + outcome_score + calibration_penalty

        # Bonus for identifying manipulation correctly
        if prediction.get("manipulation_detected") and trade.get("outcome") != "WIN":
            reward += 0.1

        # Big penalty for ignoring kill switch logic
        if trade.get("override_risk"):
            reward -= 0.5

        return round(reward, 4)
