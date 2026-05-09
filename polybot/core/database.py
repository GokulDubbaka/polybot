"""
POLYBOT — Database Layer (SQLite via stdlib sqlite3)
Handles all trade records, portfolio snapshots, and prediction logs.
No ORM needed — raw sqlite3 for zero extra dependencies.
"""

import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

from config.settings import DB_PATH


# ─────────────────────────────────────────
# CONNECTION HELPER
# ─────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─────────────────────────────────────────
# SCHEMA INIT
# ─────────────────────────────────────────

def init_db():
    """Create all tables if they don't exist."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                condition_id    TEXT NOT NULL,
                question        TEXT NOT NULL,
                direction       TEXT NOT NULL,        -- YES | NO
                entry_price     REAL NOT NULL,
                size_usd        REAL NOT NULL,
                model_prob      REAL NOT NULL,
                market_prob     REAL NOT NULL,
                edge            REAL NOT NULL,
                confidence      REAL NOT NULL,
                time_horizon    TEXT NOT NULL,
                status          TEXT DEFAULT 'OPEN',  -- OPEN | CLOSED
                exit_price      REAL,
                pnl_usd         REAL,
                exit_reason     TEXT,
                exit_timestamp  TEXT,
                mode            TEXT DEFAULT 'PAPER'
            );

            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                total_value     REAL NOT NULL,
                cash_balance    REAL NOT NULL,
                open_positions  INTEGER NOT NULL,
                daily_pnl       REAL NOT NULL,
                total_pnl       REAL NOT NULL,
                sharpe_ratio    REAL,
                win_rate        REAL
            );

            CREATE TABLE IF NOT EXISTS predictions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                condition_id    TEXT NOT NULL,
                question        TEXT NOT NULL,
                model_prob      REAL NOT NULL,
                market_prob     REAL NOT NULL,
                edge            REAL NOT NULL,
                confidence      REAL NOT NULL,
                direction       TEXT,
                trade_signal    INTEGER,
                actual_outcome  REAL,           -- filled in after resolution
                brier_score     REAL            -- filled in after resolution
            );
        """)
    print(f"[DB] Initialized at {DB_PATH}")


# ─────────────────────────────────────────
# TRADES
# ─────────────────────────────────────────

def save_trade(trade: dict) -> int:
    """Insert a new trade record. Returns the new row ID."""
    with _get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO trades (
                timestamp, condition_id, question, direction,
                entry_price, size_usd, model_prob, market_prob,
                edge, confidence, time_horizon, status, mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            trade["condition_id"],
            trade["question"],
            trade["direction"],
            trade["entry_price"],
            trade["size_usd"],
            trade["model_prob"],
            trade["market_prob"],
            trade["edge"],
            trade["confidence"],
            trade["time_horizon"],
            trade.get("mode", "PAPER"),
        ))
        return cur.lastrowid


def close_trade(trade_id: int, exit_price: float, pnl_usd: float, reason: str):
    """Mark a trade as CLOSED with P&L."""
    with _get_conn() as conn:
        conn.execute("""
            UPDATE trades
            SET status = 'CLOSED',
                exit_price = ?,
                pnl_usd = ?,
                exit_reason = ?,
                exit_timestamp = ?
            WHERE id = ?
        """, (exit_price, pnl_usd, reason,
              datetime.now(timezone.utc).isoformat(), trade_id))


def get_open_trades() -> list[dict]:
    """Return all currently open trades."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY timestamp DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_closed_trades(limit: int = 200) -> list[dict]:
    """Return recent closed trades for performance analysis."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_trade(trade_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None


def open_trade(trade: dict) -> int:
    """Alias for save_trade — opens a new paper position."""
    return save_trade(trade)


def get_trade_stats() -> dict:
    """Aggregate statistics across all closed trades."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT pnl_usd FROM trades WHERE status = 'CLOSED'"
        ).fetchall()

    if not rows:
        return {
            "total": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "total_pnl": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "avg_pnl": 0.0,
        }

    pnls     = [r[0] for r in rows if r[0] is not None]
    wins     = sum(1 for p in pnls if p > 0)
    losses   = sum(1 for p in pnls if p <= 0)
    total    = len(pnls)

    return {
        "total":       total,
        "wins":        wins,
        "losses":      losses,
        "win_rate":    round(wins / total * 100, 1) if total > 0 else 0.0,
        "total_pnl":   round(sum(pnls), 2),
        "best_trade":  round(max(pnls), 2) if pnls else 0.0,
        "worst_trade": round(min(pnls), 2) if pnls else 0.0,
        "avg_pnl":     round(sum(pnls) / total, 2) if total > 0 else 0.0,
    }


# ─────────────────────────────────────────
# RL EXPERIENCES
# ─────────────────────────────────────────

def save_rl_experience(experience: dict):
    """Store a reinforcement-learning (state, action, reward) tuple."""
    with _get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS rl_experiences (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            trade_id    INTEGER,
            state_json  TEXT,
            action      TEXT,
            reward      REAL,
            done        INTEGER DEFAULT 0
        )""")
        conn.execute("""
            INSERT INTO rl_experiences (timestamp, trade_id, state_json, action, reward, done)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            experience.get("trade_id"),
            str(experience.get("state", {})),
            experience.get("action", ""),
            experience.get("reward", 0.0),
            1 if experience.get("done") else 0,
        ))


# ─────────────────────────────────────────
# PORTFOLIO SNAPSHOTS
# ─────────────────────────────────────────

def save_snapshot(snapshot: dict):
    """Persist a portfolio snapshot for charting."""
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO portfolio_snapshots (
                timestamp, total_value, cash_balance,
                open_positions, daily_pnl, total_pnl,
                sharpe_ratio, win_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            snapshot.get("total_value", 0),
            snapshot.get("cash_balance", 0),
            snapshot.get("open_positions", 0),
            snapshot.get("daily_pnl", 0),
            snapshot.get("total_pnl", 0),
            snapshot.get("sharpe_ratio"),
            snapshot.get("win_rate"),
        ))


def get_snapshots(limit: int = 500) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────
# PREDICTIONS
# ─────────────────────────────────────────

def save_prediction(pred: dict) -> int:
    with _get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO predictions (
                timestamp, condition_id, question,
                model_prob, market_prob, edge, confidence,
                direction, trade_signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            pred.get("condition_id", ""),
            pred.get("question", ""),
            pred.get("model_prob", 0.5),
            pred.get("market_prob", 0.5),
            pred.get("edge", 0),
            pred.get("confidence", 0),
            pred.get("direction"),
            1 if pred.get("trade_signal") else 0,
        ))
        return cur.lastrowid


def get_recent_predictions(limit: int = 100) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE actual_outcome IS NOT NULL ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
