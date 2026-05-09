"""
POLYBOT — Intelligence Gatherer
Pulls free data from RSS feeds, Reddit, Metaculus, Manifold.
No paid APIs required for the core intelligence layer.
"""

import time
import json
import hashlib
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional
from core.database import save_prediction
from config.settings import (
    RSS_FEEDS, REDDIT_SUBREDDITS, METACULUS_API, MANIFOLD_API
)


class IntelligenceGatherer:
    """
    Aggregates real-world signals from free sources.
    Each source adds weight to the prediction model.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PolyBot-Research/1.0 (prediction market research)"
        })
        self._news_cache    = {}  # url -> item
        self._last_metaculus = {}  # question -> cached result

    # ─────────────────────────────────────────
    # 1. RSS NEWS
    # ─────────────────────────────────────────

    def fetch_rss_news(self, max_age_hours: int = 6) -> list[dict]:
        """Pull headlines from all RSS feeds. No API key needed."""
        all_items = []
        cutoff    = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    pub_date = self._parse_feed_date(entry)
                    if pub_date and pub_date < cutoff:
                        continue

                    url = entry.get("link", "")
                    if url in self._news_cache:
                        continue

                    item = {
                        "headline":   entry.get("title", ""),
                        "summary":    entry.get("summary", "")[:500],
                        "url":        url,
                        "source":     feed.feed.get("title", feed_url),
                        "published":  pub_date.isoformat() if pub_date else "",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                    self._news_cache[url] = item
                    all_items.append(item)

                time.sleep(0.2)  # Polite rate limiting
            except Exception as e:
                print(f"[Intel] RSS error ({feed_url}): {e}")

        print(f"[Intel] Fetched {len(all_items)} fresh news items")
        return all_items

    # ─────────────────────────────────────────
    # 2. REDDIT SIGNALS
    # ─────────────────────────────────────────

    def fetch_reddit_signals(self, keywords: list[str] = None) -> list[dict]:
        """
        Pull Reddit posts via old.reddit.com JSON (no API key needed).
        Look for volume spikes and sentiment.
        """
        all_posts = []

        subreddits = REDDIT_SUBREDDITS[:6]  # Limit to avoid rate limit
        for sub in subreddits:
            try:
                url  = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
                resp = self.session.get(url, timeout=8)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                for post in data.get("data", {}).get("children", []):
                    p = post.get("data", {})

                    # Filter by keywords if provided
                    title = p.get("title", "").lower()
                    if keywords:
                        if not any(kw.lower() in title for kw in keywords):
                            continue

                    all_posts.append({
                        "title":      p.get("title", ""),
                        "subreddit":  sub,
                        "score":      p.get("score", 0),
                        "comments":   p.get("num_comments", 0),
                        "url":        p.get("url", ""),
                        "created_at": datetime.fromtimestamp(
                            p.get("created_utc", 0), tz=timezone.utc
                        ).isoformat(),
                        "upvote_ratio": p.get("upvote_ratio", 0.5),
                        "sentiment_proxy": self._reddit_sentiment_proxy(p),
                    })

                time.sleep(1.0)  # Reddit rate limit
            except Exception as e:
                print(f"[Intel] Reddit error (r/{sub}): {e}")

        print(f"[Intel] Reddit: {len(all_posts)} posts collected")
        return all_posts

    def _reddit_sentiment_proxy(self, post: dict) -> float:
        """
        Simple sentiment proxy from Reddit metadata.
        +1.0 = very positive, -1.0 = very negative
        """
        ratio    = post.get("upvote_ratio", 0.5)
        score    = post.get("score", 0)
        comments = post.get("num_comments", 0)

        # High engagement + high ratio = positive signal
        engagement_boost = min(0.2, comments / 1000)
        return round((ratio * 2 - 1) + engagement_boost, 3)

    # ─────────────────────────────────────────
    # 3. METACULUS (EXPERT FORECASTER CALIBRATION)
    # ─────────────────────────────────────────

    def get_metaculus_probability(self, keywords: list[str]) -> list[dict]:
        """
        Search Metaculus for questions similar to a Polymarket market.
        Metaculus forecasters are well-calibrated — gold standard for comparison.
        """
        results = []
        search_term = " ".join(keywords[:3])

        try:
            params = {
                "search":   search_term,
                "status":   "open",
                "order_by": "-activity",
                "limit":    5
            }
            resp = self.session.get(METACULUS_API, params=params, timeout=10)
            if resp.status_code != 200:
                return []

            data = resp.json()
            for q in data.get("results", []):
                community = q.get("community_prediction", {})
                full_q    = community.get("full", {})
                prob      = full_q.get("q2")  # median forecast

                if prob is not None:
                    results.append({
                        "source":       "metaculus",
                        "question":     q.get("title", ""),
                        "url":          f"https://www.metaculus.com/questions/{q.get('id')}/",
                        "probability":  prob,
                        "forecasters":  q.get("number_of_forecasters", 0),
                        "resolve_time": q.get("resolve_time", ""),
                    })
        except Exception as e:
            print(f"[Intel] Metaculus error: {e}")

        return results

    # ─────────────────────────────────────────
    # 4. MANIFOLD MARKETS (FREE PREDICTION MARKET CROSS-REF)
    # ─────────────────────────────────────────

    def get_manifold_probability(self, keywords: list[str]) -> list[dict]:
        """
        Search Manifold for similar questions.
        Great for cross-market arbitrage signal.
        """
        results = []
        search_term = " ".join(keywords[:3])

        try:
            params = {"term": search_term, "limit": 5}
            resp   = self.session.get(
                f"{MANIFOLD_API}/search-markets", params=params, timeout=10
            )
            if resp.status_code != 200:
                return []

            for market in resp.json():
                if market.get("outcomeType") != "BINARY":
                    continue
                prob = market.get("probability")
                if prob is not None:
                    results.append({
                        "source":      "manifold",
                        "question":    market.get("question", ""),
                        "url":         market.get("url", ""),
                        "probability": round(prob, 4),
                        "traders":     market.get("uniqueBettorCount", 0),
                        "volume":      market.get("volume", 0),
                    })
        except Exception as e:
            print(f"[Intel] Manifold error: {e}")

        return results

    # ─────────────────────────────────────────
    # 5. CROSS-MARKET DIVERGENCE DETECTOR
    # ─────────────────────────────────────────

    def detect_cross_market_divergence(
        self, polymarket_prob: float, keywords: list[str]
    ) -> dict:
        """
        THE MAIN EDGE: Find where Polymarket disagrees with expert forecasters.
        Returns divergence signal and confidence weight.
        """
        signals = []

        # Metaculus signal
        metaculus = self.get_metaculus_probability(keywords)
        for m in metaculus:
            signals.append({
                "source":      "metaculus",
                "probability": m["probability"],
                "weight":      0.4,  # High weight — trained forecasters
                "url":         m["url"],
            })

        # Manifold signal
        manifold = self.get_manifold_probability(keywords)
        for m in manifold:
            signals.append({
                "source":      "manifold",
                "probability": m["probability"],
                "weight":      0.25,
                "url":         m["url"],
            })

        if not signals:
            return {"divergence": 0, "consensus_prob": None, "signals": []}

        # Weighted consensus probability
        total_weight  = sum(s["weight"] for s in signals)
        consensus     = sum(s["probability"] * s["weight"] for s in signals) / total_weight
        divergence    = polymarket_prob - consensus

        return {
            "polymarket_prob": polymarket_prob,
            "consensus_prob":  round(consensus, 4),
            "divergence":      round(divergence, 4),
            "abs_divergence":  round(abs(divergence), 4),
            "signals":         signals,
            "signal_count":    len(signals),
            # If divergence > 0.08: Polymarket is OVERPRICED
            # If divergence < -0.08: Polymarket is UNDERPRICED = BUY YES
            "recommendation":  "BUY_YES" if divergence < -0.08
                               else "BUY_NO" if divergence > 0.08
                               else "NEUTRAL"
        }

    # ─────────────────────────────────────────
    # 6. NEWS RELEVANCE SCORING
    # ─────────────────────────────────────────

    def score_news_relevance(self, news_items: list[dict],
                              market_question: str) -> list[dict]:
        """
        Score each news item's relevance to a specific market question.
        Uses keyword overlap — fast and free (no LLM needed here).
        """
        q_words = set(market_question.lower().split())
        stop    = {"the","a","an","is","are","was","were","will","be","to","of",
                   "and","or","in","on","at","for","with","by","from","that","this"}
        q_words -= stop

        scored = []
        for item in news_items:
            text     = (item["headline"] + " " + item.get("summary","")).lower()
            t_words  = set(text.split()) - stop
            overlap  = len(q_words & t_words)
            relevance = min(1.0, overlap / max(len(q_words), 1))

            if relevance > 0.1:  # Only keep relevant items
                scored.append({**item, "relevance_score": round(relevance, 3)})

        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored[:10]  # Top 10 most relevant

    # ─────────────────────────────────────────
    # 7. FAKE / NOISE DETECTION
    # ─────────────────────────────────────────

    def flag_suspicious_signals(self, signals: list[dict]) -> list[dict]:
        """
        Basic manipulation / noise detection.
        Flags signals that look like coordinated pumps or bot activity.
        """
        for s in signals:
            flags = []

            # Reddit: suspiciously high ratio on low-karma post
            if s.get("source") == "reddit":
                if s.get("upvote_ratio", 1) > 0.98 and s.get("score", 0) < 50:
                    flags.append("SUSPICIOUS_RATIO")
                if s.get("comments", 0) == 0 and s.get("score", 0) > 500:
                    flags.append("ZERO_COMMENTS_HIGH_SCORE")

            # News: duplicate headlines from different sources = coordinated PR
            if s.get("source") == "rss":
                headline_hash = hashlib.md5(
                    s.get("headline","").lower().encode()
                ).hexdigest()[:8]
                s["headline_hash"] = headline_hash

            s["manipulation_flags"] = flags
            s["is_suspicious"]      = len(flags) > 0

        return signals

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

    def _parse_feed_date(self, entry) -> Optional[datetime]:
        try:
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if hasattr(entry, "updated_parsed") and entry.updated_parsed:
                return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
        return None

    def build_market_context(self, market: dict, news_items: list[dict]) -> dict:
        """
        Aggregate all intelligence for a single market.
        This is what gets passed to the LLM prediction engine.
        """
        question    = market.get("question", "")
        keywords    = [w for w in question.split() if len(w) > 4][:6]
        yes_price   = market.get("yes_price")

        # Skip markets with no valid price
        if yes_price is None or not (0.01 <= float(yes_price) <= 0.99):
            return {}

        yes_price = float(yes_price)

        relevant_news     = self.score_news_relevance(news_items, question)
        cross_market      = self.detect_cross_market_divergence(yes_price, keywords)
        reddit_signals    = self.fetch_reddit_signals(keywords=keywords[:3])
        flagged_reddit    = self.flag_suspicious_signals(reddit_signals[:5])
        clean_reddit      = [r for r in flagged_reddit if not r["is_suspicious"]]

        return {
            "market_question":  question,
            "market_prob_yes":  yes_price,
            "category":         market.get("category", ""),
            "liquidity_usd":    market.get("liquidity_usd", 0),
            "relevant_news":    relevant_news[:5],
            "reddit_signals":   clean_reddit[:3],
            "cross_market":     cross_market,
            "data_quality":     "high" if len(relevant_news) > 2 else "low",
        }
