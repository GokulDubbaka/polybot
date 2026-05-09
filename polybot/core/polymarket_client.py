"""
POLYBOT — Polymarket API Client
Wraps the Polymarket CLOB REST API and Gamma (markets discovery) API.
Handles auth, market fetching, order placement, and order book reading.
"""

import time
import requests
from typing import Optional

from config.settings import (
    POLYMARKET_HOST,
    POLYMARKET_GAMMA_HOST,
    POLYMARKET_WALLET_PK,
    TRADING_MODE,
    MIN_LIQUIDITY_USD,
)


class PolymarketClient:
    """
    Client for Polymarket public APIs.
    - Gamma API:  market discovery (no auth required)
    - CLOB API:   order book prices (no auth for reads; auth only for live orders)
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PolyBot/1.0",
            "Accept": "application/json",
        })
        print("[PolyClient] Initialized. Mode:", TRADING_MODE)

    # ─────────────────────────────────────────
    # MARKET DISCOVERY
    # ─────────────────────────────────────────

    def get_markets(self, limit: int = 50) -> list[dict]:
        """
        Fetch active binary markets from Gamma API.
        Returns list of enriched market dicts with yes_price and no_price.
        """
        try:
            resp = self.session.get(
                f"{POLYMARKET_GAMMA_HOST}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                    "order": "volume",
                    "ascending": "false",
                },
                timeout=15,
            )
            resp.raise_for_status()
            raw_markets = resp.json()

            markets = []
            for m in raw_markets:
                parsed = self._parse_market(m)
                if parsed:
                    markets.append(parsed)

            return markets

        except requests.exceptions.RequestException as e:
            print(f"[PolyClient] Error fetching markets: {e}")
            return []

    def get_market(self, condition_id: str) -> Optional[dict]:
        """
        Look up a single market by condition_id.
        Used by paper_trader to get current exit price.
        """
        try:
            resp = self.session.get(
                f"{POLYMARKET_GAMMA_HOST}/markets",
                params={"conditionId": condition_id, "limit": 1},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return self._parse_market(data[0])
            if isinstance(data, dict):
                return self._parse_market(data)
            return None
        except Exception as e:
            print(f"[PolyClient] get_market error: {e}")
            return None

    def _parse_market(self, raw: dict) -> Optional[dict]:
        """Parse and validate a raw Gamma market object."""
        import json
        
        try:
            outcomes = json.loads(raw.get("outcomes", "[]"))
            prices = json.loads(raw.get("outcomePrices", "[]"))
            tokens = json.loads(raw.get("clobTokenIds", "[]"))
        except Exception:
            return None

        # Must be a binary (YES/NO) market with both prices
        yes_idx, no_idx = None, None
        for i, o in enumerate(outcomes):
            if str(o).upper() == "YES": yes_idx = i
            elif str(o).upper() == "NO": no_idx = i
            
        if yes_idx is None or no_idx is None:
            return None
            
        if len(prices) <= max(yes_idx, no_idx) or len(tokens) <= max(yes_idx, no_idx):
            return None

        yes_price = self._safe_float(prices[yes_idx])
        no_price  = self._safe_float(prices[no_idx])

        if yes_price is None or no_price is None:
            return None

        # Filter illiquid markets
        liquidity = self._safe_float(raw.get("liquidityNum", 0)) or self._safe_float(raw.get("liquidity", 0)) or 0
        if liquidity < MIN_LIQUIDITY_USD:
            return None

        return {
            "condition_id":    raw.get("conditionId", ""),
            "question":        raw.get("question", ""),
            "description":     raw.get("description", ""),
            "category":        raw.get("groupItemTitle") or raw.get("category") or "general",
            "yes_price":       yes_price,
            "no_price":        no_price,
            "volume_24hr":     self._safe_float(raw.get("volume24hr", 0)) or 0,
            "end_date":        raw.get("endDate", ""),
            "yes_token_id":    tokens[yes_idx],
            "no_token_id":     tokens[no_idx],
        }

    # ─────────────────────────────────────────
    # ORDER BOOK
    # ─────────────────────────────────────────

    def get_orderbook(self, token_id: str) -> Optional[dict]:
        """Fetch L2 order book for a specific outcome token."""
        try:
            resp = self.session.get(
                f"{POLYMARKET_HOST}/book",
                params={"token_id": token_id},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[PolyClient] Orderbook fetch error: {e}")
            return None

    def get_best_price(self, token_id: str, side: str = "BUY") -> Optional[float]:
        """Get best available price for a given side (BUY/SELL)."""
        book = self.get_orderbook(token_id)
        if not book:
            return None

        orders = book.get("asks" if side == "BUY" else "bids", [])
        if not orders:
            return None

        best = sorted(orders, key=lambda x: float(x.get("price", 0)))[0]
        return float(best.get("price", 0))

    # ─────────────────────────────────────────
    # MARKET CLASSIFICATION
    # ─────────────────────────────────────────

    def classify_time_horizon(self, market: dict) -> str:
        """
        Estimate the time horizon of a market based on its end date.
        Returns: '5min' | '15min' | '4hour' | '1day' | '1week'
        """
        from datetime import datetime, timezone
        end_date_str = market.get("end_date", "")
        if not end_date_str:
            return "1day"  # default

        try:
            end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            now    = datetime.now(timezone.utc)
            delta  = end_dt - now
            hours  = delta.total_seconds() / 3600

            if hours <= 0.1:   return "5min"
            if hours <= 0.25:  return "15min"
            if hours <= 5:     return "4hour"
            if hours <= 26:    return "1day"
            return "1week"
        except Exception:
            return "1day"

    # ─────────────────────────────────────────
    # LIVE TRADING (CLOB ORDER PLACEMENT)
    # ─────────────────────────────────────────

    def place_order(self, token_id: str, side: str, size_usd: float, price: float) -> Optional[dict]:
        """
        Place a live limit order on Polymarket CLOB.
        Only called in LIVE mode — requires wallet private key.
        Paper mode returns a simulated result.
        """
        if TRADING_MODE != "LIVE":
            # Paper mode — simulate order fill
            return {
                "order_id":   f"PAPER-{int(time.time())}",
                "status":     "filled",
                "fill_price": price,
                "size_usd":   size_usd,
            }

        if not POLYMARKET_WALLET_PK:
            print("[PolyClient] ERROR: POLYMARKET_PRIVATE_KEY not set. Cannot place live orders.")
            return None

        # Live mode: Polymarket CLOB uses EIP-712 signed orders.
        # Full implementation requires py-clob-client from Polymarket.
        # Install: pip install py-clob-client
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.constants import POLYGON
            from py_clob_client.clob_types import OrderArgs, OrderType

            client = ClobClient(
                host=POLYMARKET_HOST,
                key=POLYMARKET_WALLET_PK,
                chain_id=POLYGON,
            )
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=round(size_usd / price, 2),
                side=side,
            )
            resp = client.create_and_post_order(order_args)
            return resp

        except ImportError:
            print("[PolyClient] py-clob-client not installed. Run: pip install py-clob-client")
            return None
        except Exception as e:
            print(f"[PolyClient] Live order error: {e}")
            return None

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
