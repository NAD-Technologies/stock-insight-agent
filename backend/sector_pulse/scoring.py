"""Sector Pulse scoring. Pure, deterministic functions: no I/O, no LLM, no globals beyond config passed in.

Conventions
  * a *signal* is a number in [-1, 1] (0 = neutral); a *score* is 0-100 (50 = neutral vs the market).
  * all constants (weights, scales, bands) come from rules.yaml.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

HERE = Path(__file__).parent
IMPACT_W = {"High": 3.0, "Med": 2.0, "Low": 1.0}
SENTIMENT_SIGN = {"Bullish": 1, "Bearish": -1}


def load_yaml(name: str) -> dict:
    with open(HERE / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def to_score(signal: float) -> float:
    """Signal in [-1, 1] -> score 0..100."""
    return round(50 + 50 * clip(signal), 1)


def decay(age_days: float, half_life_days: float) -> float:
    """w(t) = 0.5 ** (t / h): an item's weight halves every `half_life_days`."""
    return 0.5 ** (max(age_days, 0.0) / half_life_days)


# ------------------------------------------------------------------ price helpers
def period_return(close: pd.Series, days: int) -> Optional[float]:
    if close is None or len(close) <= days:
        return None
    start = float(close.iloc[-1 - days])
    return float(close.iloc[-1]) / start - 1 if start else None


def pct_above_sma(closes: list[pd.Series], window: int = 50) -> Optional[float]:
    """Breadth: share of series whose last close is above its own `window`-day SMA."""
    flags = []
    for c in closes:
        if c is not None and len(c) >= window:
            flags.append(float(c.iloc[-1]) > float(c.tail(window).mean()))
    return sum(flags) / len(flags) if flags else None


def trend_signal(close: pd.Series) -> Optional[float]:
    """+0.5 for each of (price > SMA50, price > SMA200), -0.5 for each below. Range [-1, 1]."""
    if close is None or len(close) < 50:
        return None
    px = float(close.iloc[-1])
    s = 0.5 if px > float(close.tail(50).mean()) else -0.5
    if len(close) >= 200:
        s += 0.5 if px > float(close.tail(200).mean()) else -0.5
    else:
        s *= 2  # only SMA50 available: scale to the same range
    return s


# ------------------------------------------------------------------ factor signals
def momentum_signal(excess: Optional[float], breadth: Optional[float], trend: Optional[float], rules: dict, horizon: str) -> Optional[float]:
    """Blend of excess return vs SPY (tanh-scaled), breadth and trend. Missing parts are dropped and weights renormalised."""
    parts = rules["momentum"]["parts"]
    scale = rules["horizons"][horizon]["scale"]
    vals = {
        "excess_return": math.tanh(excess / scale) if excess is not None else None,
        "breadth": (breadth - 0.5) * 2 if breadth is not None else None,
        "trend": trend,
    }
    avail = {k: v for k, v in vals.items() if v is not None}
    if not avail:
        return None
    tot = sum(parts[k] for k in avail)
    return clip(sum(parts[k] * v for k, v in avail.items()) / tot)


def news_signal(items: list[dict], now: dt.datetime, rules: dict) -> tuple[Optional[float], int]:
    """Recency- and impact-weighted sentiment with shrinkage. Returns (signal, n_items); None when there is no news."""
    cfg = rules["news"]
    num = den = 0.0
    n = 0
    for it in items:
        try:
            age = (now - dt.datetime.fromisoformat(str(it["time"]).replace("Z", "+00:00"))).total_seconds() / 86400
        except (KeyError, TypeError, ValueError):
            age = cfg["half_life_days"]
        if age > cfg["lookback_days"]:
            continue
        w = IMPACT_W.get(it.get("impact"), 1.0) * decay(age, cfg["half_life_days"])
        num += SENTIMENT_SIGN.get(it.get("sentiment"), 0) * w
        den += w
        n += 1
    if not n:
        return None, 0
    return clip(num / (den + cfg["shrink"])), n


def active_event_weights(events: list[dict], rules: dict, now: dt.datetime) -> dict[str, float]:
    """Strongest decayed weight per event type among events still in the news. Using max (not sum) stops a story that
    repeats daily from stacking up."""
    sev = rules["event_severity_weight"]
    out: dict[str, float] = {}
    for e in events:
        hl = rules["event_types"].get(e["type"], {}).get("half_life_days")
        if not hl:
            continue
        age = (now - dt.datetime.fromtimestamp(e["last_seen"], dt.timezone.utc)).total_seconds() / 86400
        w = sev.get(e["severity"], 0.3) * decay(age, hl)
        out[e["type"]] = max(out.get(e["type"], 0.0), w)
    return out


def event_signal(active: dict[str, float], theme_id: str, rules: dict) -> Optional[float]:
    if not active:
        return None
    total = sum(rules["impact_matrix"].get(t, {}).get(theme_id, 0.0) * w for t, w in active.items())
    return clip(total)


def flows_signal(fast_dollar_vol: Optional[float], slow_dollar_vol: Optional[float], ret_1m: Optional[float]) -> Optional[float]:
    """PROXY for fund flows (true flow data needs a paid feed): ETF dollar-volume surge, signed by the 1M price trend.
    Rising volume in an uptrend is read as inflow, rising volume in a downtrend as outflow."""
    if not fast_dollar_vol or not slow_dollar_vol or ret_1m is None:
        return None
    surge = fast_dollar_vol / slow_dollar_vol - 1
    return clip(math.tanh(surge / 0.5) * (1 if ret_1m >= 0 else -1))


# ------------------------------------------------------------------ composite, direction, confidence
def composite(factor_scores: dict[str, Optional[float]], weights: dict[str, float]) -> tuple[Optional[float], dict[str, float], list[str]]:
    """Weighted mean of the available factor scores. Returns (score, normalised weights used, missing factors)."""
    avail = {k: s for k, s in factor_scores.items() if s is not None and weights.get(k, 0) > 0}
    missing = [k for k, w in weights.items() if w > 0 and factor_scores.get(k) is None]
    if not avail:
        return None, {}, missing
    tot = sum(weights[k] for k in avail)
    used = {k: weights[k] / tot for k in avail}
    return round(sum(used[k] * avail[k] for k in avail), 1), used, missing


def direction(score: Optional[float], rules: dict) -> str:
    if score is None:
        return "Flat"
    d = rules["direction"]
    return "Up" if score >= d["up_at"] else "Down" if score <= d["down_at"] else "Flat"


def prob_up(score: Optional[float], rules: dict) -> Optional[float]:
    """Logistic map from score to P(beat SPY). Uncalibrated until enough outcomes exist to fit it."""
    if score is None:
        return None
    return round(1 / (1 + math.exp(-(score - 50) / rules["probability_slope"])), 3)


def confidence(factor_scores: dict[str, Optional[float]], weights: dict[str, float], n_news: int, rules: dict) -> tuple[str, list[str]]:
    cfg = rules["confidence"]
    avail = {k: s for k, s in factor_scores.items() if s is not None and weights.get(k, 0) > 0}
    total_w = sum(w for w in weights.values() if w > 0) or 1
    coverage = sum(weights[k] for k in avail) / total_w
    spread = statistics.pstdev(avail.values()) if len(avail) >= 2 else 0.0
    reasons = []
    if coverage < cfg["high_coverage"]:
        reasons.append(f"only {round(coverage * 100)}% of factor weight has data")
    if spread > cfg["high_spread"]:
        reasons.append("factors disagree")
    if n_news < rules["news"]["min_items_for_confidence"]:
        reasons.append(f"thin news coverage ({n_news} items)")
    if not avail:
        return "Low", ["no usable data"]
    if coverage >= cfg["high_coverage"] and spread <= cfg["high_spread"] and n_news >= rules["news"]["min_items_for_confidence"]:
        return "High", []
    if coverage >= 0.5 and spread <= cfg["med_spread"]:
        return "Medium", reasons
    return "Low", reasons


# ------------------------------------------------------------------ ticker ranking inside a theme
def sensitivity_score(beta: Optional[float], theme_score: float) -> Optional[float]:
    """Higher-beta names gain more in an Up theme and lose more in a Down one, so reward beta when the theme score is
    above neutral and penalise it when below. Returns 0..100."""
    if beta is None:
        return None
    s = 1 if theme_score >= 50 else -1
    return to_score(math.tanh(beta - 1) * s)


def rank_score(composite_score: Optional[float], news_signal_pm1: Optional[float], excess_vs_theme: Optional[float],
               sens: Optional[float], rules: dict) -> float:
    """50% Module A composite, 20% ticker news momentum, 15% relative strength vs theme, 15% sector sensitivity.
    Unknown components default to neutral (50) so a name is neither rewarded nor punished for missing data."""
    w = rules["picks"]["weights"]
    comp = composite_score if composite_score is not None else 50.0
    news = to_score(news_signal_pm1) if news_signal_pm1 is not None else 50.0
    rs = to_score(math.tanh(excess_vs_theme / rules["picks"]["rs_scale"])) if excess_vs_theme is not None else 50.0
    se = sens if sens is not None else 50.0
    return round(w["composite"] * comp + w["news"] * news + w["relative_strength"] * rs + w["sensitivity"] * se, 1)


# ------------------------------------------------------------------ outcome evaluation
def outcome_label(excess_return: float, flat_band: float) -> str:
    return "Up" if excess_return > flat_band else "Down" if excess_return < -flat_band else "Flat"


def baseline_label(excess_1m: Optional[float], rules: dict) -> str:
    """Naive benchmark to beat: 'last month's relative move continues'."""
    if excess_1m is None:
        return "Flat"
    return outcome_label(excess_1m, rules["horizons"]["1M"]["flat_band"])
