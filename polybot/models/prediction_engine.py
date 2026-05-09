"""
POLYBOT — AI Prediction Engine
Uses Claude API to analyze markets and generate calibrated probability estimates.
Cost: ~$0.002 per prediction with Haiku. ~$0.02 with Sonnet.
"""

import json
import math
import requests
from datetime import datetime
from config.settings import (
    ANTHROPIC_API_KEY, LLM_MODEL, LLM_FAST_MODEL,
    MAX_TOKENS, MIN_EDGE_THRESHOLD, MIN_CONFIDENCE, BRIER_SCORE_WINDOW
)


class PredictionEngine:
    """
    Multi-model prediction stack:
    1. Fast screen (Haiku) — cheap, filters obvious non-trades
    2. Deep analysis (Sonnet) — thorough, only for screened markets
    3. Calibration — Brier scoring to track model accuracy over time
    """

    def __init__(self):
        self.api_url    = "https://api.anthropic.com/v1/messages"
        self.headers    = {
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json"
        }
        self.brier_history  = []  # Track calibration over time
        self.prediction_log = []  # For RL reward calculation

    # ─────────────────────────────────────────
    # MAIN PREDICTION PIPELINE
    # ─────────────────────────────────────────

    def predict(self, market_context: dict) -> dict | None:
        """
        Full prediction pipeline for a single market.
        Returns prediction dict or None if market should be skipped.
        """
        # Step 1: Fast screen — is this worth deeper analysis?
        screen = self._fast_screen(market_context)
        if not screen.get("worth_analyzing"):
            return None

        # Step 2: Deep analysis — get calibrated probability
        prediction = self._deep_analysis(market_context)
        if not prediction:
            return None

        # Step 3: Apply cross-market calibration adjustment
        prediction = self._apply_cross_market_adjustment(prediction, market_context)

        # Step 4: Calculate edge and decide if trade is valid
        prediction = self._calculate_edge(prediction, market_context)

        return prediction

    # ─────────────────────────────────────────
    # STEP 1: FAST SCREEN (cheap Haiku)
    # ─────────────────────────────────────────

    def _fast_screen(self, ctx: dict) -> dict:
        """
        Quick check: Is there enough data and potential edge to analyze?
        Uses cheapest model to save costs.
        """
        question    = ctx.get("market_question", "")
        yes_price   = ctx.get("market_prob_yes", 0.5)
        news_count  = len(ctx.get("relevant_news", []))
        data_quality= ctx.get("data_quality", "low")

        prompt = f"""You are a prediction market screener. 
        
Market: "{question}"
Current YES price: {yes_price:.2%}
Available news items: {news_count}
Data quality: {data_quality}
Cross-market divergence: {ctx.get('cross_market', {}).get('abs_divergence', 0):.2%}

Reply ONLY with valid JSON:
{{
  "worth_analyzing": true/false,
  "reason": "one sentence",
  "quick_edge_estimate": 0.0-1.0
}}

worth_analyzing = true if: there's news data available, OR significant cross-market divergence > 5%, OR market is near resolution with unexpected odds."""

        response = self._call_api(prompt, model=LLM_FAST_MODEL, max_tokens=200)
        if not response:
            return {"worth_analyzing": False, "reason": "API call failed"}

        try:
            return json.loads(response.strip().strip("```json").strip("```"))
        except json.JSONDecodeError:
            # Fallback: analyze anyway if data quality is high
            return {"worth_analyzing": data_quality == "high", "reason": "Parse error"}

    # ─────────────────────────────────────────
    # STEP 2: DEEP ANALYSIS (Sonnet)
    # ─────────────────────────────────────────

    def _deep_analysis(self, ctx: dict) -> dict | None:
        """
        Thorough LLM analysis. Provides calibrated probability + reasoning.
        """
        question   = ctx.get("market_question", "")
        yes_price  = ctx.get("market_prob_yes")
        if yes_price is None:
            return None
        yes_price  = float(yes_price)
        if not (0.01 <= yes_price <= 0.99):
            return None
        news_items = ctx.get("relevant_news", [])
        reddit     = ctx.get("reddit_signals", [])
        cross      = ctx.get("cross_market", {})

        # Build evidence summary
        news_text   = "\n".join([
            f"- [{n['source']}] {n['headline']}"
            for n in news_items[:5]
        ]) or "No recent news found."

        reddit_text = "\n".join([
            f"- r/{r['subreddit']}: {r['title'][:100]} (score: {r['score']})"
            for r in reddit[:3]
        ]) or "No Reddit signals."

        cross_text = ""
        if cross.get("signals"):
            cross_text = f"""
Cross-market forecaster consensus: {cross.get('consensus_prob', 'N/A')}
Divergence from Polymarket: {cross.get('divergence', 0):.2%}
External recommendation: {cross.get('recommendation', 'NEUTRAL')}
Sources: {', '.join([s['source'] for s in cross.get('signals', [])])}"""

        prompt = f"""You are an expert prediction market analyst with a strong track record of calibrated forecasting.

MARKET: "{question}"
POLYMARKET CURRENT ODDS: YES = {yes_price:.2%}, NO = {1-yes_price:.2%}

RECENT NEWS:
{news_text}

REDDIT / SOCIAL SIGNALS:
{reddit_text}

CROSS-MARKET INTELLIGENCE:
{cross_text}

YOUR TASK:
1. Analyze all evidence systematically
2. Identify the BASE RATE for this type of event
3. Update the base rate based on current evidence  
4. Provide a CALIBRATED probability for YES outcome
5. Identify the single biggest risk to your prediction

CRITICAL: Be a good Bayesian. Don't over-update on weak evidence.
Flag if any news appears manipulated or misleading.

Respond ONLY with this JSON (no markdown, no explanation outside JSON):
{{
  "model_prob_yes": 0.00,
  "confidence": 0.00,
  "direction": "YES" or "NO" or "SKIP",
  "base_rate": 0.00,
  "key_evidence": ["evidence 1", "evidence 2", "evidence 3"],
  "biggest_risk": "what could make this prediction wrong",
  "manipulation_detected": false,
  "reasoning": "2-3 sentence summary of your analysis"
}}

Rules:
- model_prob_yes: 0.0 to 1.0 (your calibrated probability)
- confidence: 0.0 to 1.0 (how confident you are in your estimate)
- If data is insufficient, set confidence < 0.5 and direction = "SKIP"
- If manipulation detected, set direction = "SKIP"
"""

        response = self._call_api(prompt, model=LLM_MODEL, max_tokens=600)
        if not response:
            return None

        try:
            # Strip any markdown code fences
            clean = response.strip().strip("```json").strip("```").strip()
            result = json.loads(clean)

            return {
                "condition_id":   ctx.get("condition_id", ""),
                "market_question":question,
                "model_prob_yes": float(result.get("model_prob_yes", 0.5)),
                "market_prob_yes":yes_price,
                "confidence":     float(result.get("confidence", 0.5)),
                "direction":      result.get("direction", "SKIP"),
                "base_rate":      float(result.get("base_rate", 0.5)),
                "key_evidence":   result.get("key_evidence", []),
                "biggest_risk":   result.get("biggest_risk", ""),
                "manipulation_detected": result.get("manipulation_detected", False),
                "reasoning":      result.get("reasoning", ""),
                "sources":        [n["url"] for n in news_items[:3]],
                "analyzed_at":    datetime.now().isoformat(),
            }
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[Prediction] Parse error: {e}\nResponse: {response[:200]}")
            return None

    # ─────────────────────────────────────────
    # STEP 3: CROSS-MARKET CALIBRATION
    # ─────────────────────────────────────────

    def _apply_cross_market_adjustment(self, pred: dict, ctx: dict) -> dict:
        """
        Adjust model probability using expert forecaster consensus.
        If Metaculus/Manifold strongly disagree with our model, we blend.
        """
        cross = ctx.get("cross_market", {})
        consensus = cross.get("consensus_prob")

        if consensus is None:
            return pred

        # Blend: 70% our model, 30% external consensus
        blended = pred["model_prob_yes"] * 0.70 + consensus * 0.30
        pred["model_prob_yes_raw"]      = pred["model_prob_yes"]
        pred["model_prob_yes"]          = round(blended, 4)
        pred["consensus_prob_external"] = consensus
        pred["blend_applied"]           = True

        return pred

    # ─────────────────────────────────────────
    # STEP 4: EDGE CALCULATION
    # ─────────────────────────────────────────

    def _calculate_edge(self, pred: dict, ctx: dict) -> dict:
        """
        Calculate trading edge and determine if trade should be executed.
        Edge = |model_prob - market_prob|
        """
        model_prob  = pred.get("model_prob_yes")
        market_prob = pred.get("market_prob_yes")

        # Guard: skip if prices are missing
        if model_prob is None or market_prob is None:
            pred.update({"edge": 0, "edge_yes": 0, "edge_no": 0,
                         "kelly_fraction": 0, "risk_level": "high",
                         "trade_signal": False})
            return pred

        model_prob  = float(model_prob)
        market_prob = float(market_prob)

        edge_yes = model_prob - market_prob    # Positive = YES is underpriced
        edge_no  = market_prob - model_prob    # Positive = NO is underpriced

        # Use the direction predicted
        if pred["direction"] == "YES":
            edge = edge_yes
        elif pred["direction"] == "NO":
            edge = edge_no
        else:
            edge = 0

        # Kelly Criterion: optimal bet fraction
        # f* = (bp - q) / b  where b = odds, p = win prob, q = 1-p
        kelly_fraction = self._kelly_fraction(model_prob, market_prob, pred["direction"])

        # Risk classification
        risk_level = self._classify_risk(edge, pred["confidence"],
                                          ctx.get("liquidity_usd", 0))

        pred.update({
            "edge":            round(edge, 4),
            "edge_yes":        round(edge_yes, 4),
            "edge_no":         round(edge_no, 4),
            "kelly_fraction":  round(kelly_fraction, 4),
            "risk_level":      risk_level,
            "trade_signal":    (
                edge >= MIN_EDGE_THRESHOLD and
                pred["confidence"] >= MIN_CONFIDENCE and
                pred["direction"] != "SKIP" and
                not pred.get("manipulation_detected", False)
            )
        })

        return pred

    def _kelly_fraction(self, model_prob: float, market_prob: float,
                         direction: str) -> float:
        """
        Kelly Criterion for optimal position sizing.
        We use 25% Kelly (fractional Kelly) to be conservative.
        """
        if direction == "YES":
            p = model_prob
            b = (1 - market_prob) / market_prob  # Decimal odds
        elif direction == "NO":
            p = 1 - model_prob
            b = (1 - (1 - market_prob)) / (1 - market_prob)
        else:
            return 0.0

        q = 1 - p
        if b <= 0:
            return 0.0

        kelly = (b * p - q) / b
        fractional_kelly = max(0, kelly * 0.25)  # 25% Kelly — conservative
        return min(fractional_kelly, 0.05)  # Never bet more than 5% Kelly

    def _classify_risk(self, edge: float, confidence: float,
                        liquidity: float) -> str:
        """Classify trade into low/medium/high risk."""
        risk_score = 0

        # Edge component
        if edge > 0.20:    risk_score += 1   # Large edge = lower risk
        elif edge < 0.10:  risk_score += 3   # Thin edge = higher risk
        else:              risk_score += 2

        # Confidence component
        if confidence > 0.85:   risk_score += 1
        elif confidence < 0.70: risk_score += 3
        else:                   risk_score += 2

        # Liquidity component
        if liquidity > 100_000: risk_score += 1
        elif liquidity < 20_000:risk_score += 3
        else:                   risk_score += 2

        if risk_score <= 4:   return "low"
        if risk_score <= 7:   return "medium"
        return "high"

    # ─────────────────────────────────────────
    # CALIBRATION (BRIER SCORE)
    # ─────────────────────────────────────────

    def update_calibration(self, prediction_id: int, model_prob: float,
                            actual_outcome: int):
        """
        Called when a market resolves (1=YES, 0=NO).
        Brier Score = (probability - outcome)^2
        Lower is better. Perfect = 0, Random = 0.25
        """
        brier = (model_prob - actual_outcome) ** 2
        self.brier_history.append({
            "prediction_id": prediction_id,
            "brier_score":   brier,
            "prob":          model_prob,
            "outcome":       actual_outcome,
            "timestamp":     datetime.now().isoformat()
        })

        # Rolling window
        if len(self.brier_history) > BRIER_SCORE_WINDOW:
            self.brier_history = self.brier_history[-BRIER_SCORE_WINDOW:]

        rolling_brier = self.get_rolling_brier_score()
        print(f"[Calibration] Brier Score: {brier:.4f} | Rolling {BRIER_SCORE_WINDOW}: {rolling_brier:.4f}")

        return brier

    def get_rolling_brier_score(self) -> float:
        """Current rolling average Brier Score. Target: < 0.15"""
        if not self.brier_history:
            return 0.25  # Default = random
        return sum(h["brier_score"] for h in self.brier_history) / len(self.brier_history)

    def get_calibration_report(self) -> dict:
        """Full calibration report."""
        if not self.brier_history:
            return {"status": "insufficient_data", "samples": 0}

        scores   = [h["brier_score"] for h in self.brier_history]
        avg      = sum(scores) / len(scores)
        outcomes = [h["outcome"] for h in self.brier_history]
        probs    = [h["prob"] for h in self.brier_history]

        # Resolution accuracy
        correct = sum(
            1 for p, o in zip(probs, outcomes)
            if (p > 0.5 and o == 1) or (p <= 0.5 and o == 0)
        )
        accuracy = correct / len(outcomes)

        return {
            "samples":         len(self.brier_history),
            "brier_score":     round(avg, 4),
            "accuracy":        round(accuracy, 4),
            "model_status":    "🟢 GOOD" if avg < 0.15
                               else "🟡 DEGRADING" if avg < 0.22
                               else "🔴 POOR — RECALIBRATE",
            "target_brier":    0.15,
        }

    # ─────────────────────────────────────────
    # API CALL
    # ─────────────────────────────────────────

    def _call_api(self, prompt: str, model: str = None,
                   max_tokens: int = None) -> str | None:
        """Direct Anthropic API call."""
        if not ANTHROPIC_API_KEY:
            print("[Prediction] ERROR: ANTHROPIC_API_KEY not set")
            return None

        payload = {
            "model":      model or LLM_MODEL,
            "max_tokens": max_tokens or MAX_TOKENS,
            "messages":   [{"role": "user", "content": prompt}],
        }

        try:
            resp = requests.post(self.api_url, headers=self.headers,
                                  json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 401:
                print("[Prediction] Invalid API key")
            elif resp.status_code == 429:
                print("[Prediction] Rate limited — sleeping 60s")
                import time; import time; time.sleep(60)
            else:
                print(f"[Prediction] API error: {e}")
            return None
        except Exception as e:
            print(f"[Prediction] Unexpected error: {e}")
            return None
