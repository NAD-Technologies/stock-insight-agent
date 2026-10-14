"""Deterministic scoring engine. No LLM involvement; every number traces to an input."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def scale(v, lo, hi, invert=False) -> Optional[float]:
    """Linear map of v from [lo, hi] to [0, 100], clamped. invert flips direction."""
    if not _ok(v):
        return None
    t = (v - lo) / (hi - lo) if hi != lo else 0.5
    t = min(max(t, 0.0), 1.0)
    return round(100 * (1 - t if invert else t), 1)


def comp(name, value, score, weight=1.0, display=None, detail=""):
    return {"name": name, "value": value, "score": score, "weight": weight,
            "display": display if display is not None else (None if value is None else (round(value, 2) if isinstance(value, float) else value)),
            "detail": detail}


def aggregate(components: list[dict]) -> dict:
    valid = [c for c in components if c["score"] is not None]
    tw = sum(c["weight"] for c in valid)
    score = round(sum(c["score"] * c["weight"] for c in valid) / tw, 1) if tw else None
    total_w = sum(c["weight"] for c in components) or 1
    return {"score": score, "components": components, "coverage": round(tw / total_w, 2)}


def verdict(score: Optional[float]) -> str:
    if score is None:
        return "N/A"
    return "Bullish" if score >= 62 else "Bearish" if score < 40 else "Neutral"


# ----------------------------------------------------------------- pillars
def score_technical(t: dict) -> dict:
    if not t.get("available"):
        return {"score": None, "components": [], "coverage": 0}
    v, s = t["values"], t["summary"]
    ov, ma, osc = s["overall"], s["movingAverages"], s["oscillators"]
    n = max(sum((ov["buy"], ov["sell"], ov["neutral"])), 1)
    cs = [
        comp("Signal consensus (buy-sell)", (ov["buy"] - ov["sell"]) / n, scale((ov["buy"] - ov["sell"]) / n, -0.8, 0.8), 3,
             f'{ov["buy"]} buy / {ov["sell"]} sell / {ov["neutral"]} neutral'),
        comp("Moving-average rating", ma["rating"], scale((ma["buy"] - ma["sell"]) / max(ma["buy"] + ma["sell"] + ma["neutral"], 1), -0.8, 0.8), 2),
        comp("Oscillator rating", osc["rating"], scale((osc["buy"] - osc["sell"]) / max(osc["buy"] + osc["sell"] + osc["neutral"], 1), -0.6, 0.6), 1),
        comp("RSI(14)", v["rsi"], None if v["rsi"] is None else (100 - abs(v["rsi"] - 55) * 2.2) if v["rsi"] < 70 else scale(v["rsi"], 85, 70), 1),
        comp("Volume vs 20d avg", v["volumeVsAvg20"], scale(v["volumeVsAvg20"], 0.5, 1.8), 0.5),
        comp("Distance from 52w high %", t["levels"]["pctFrom52wHigh"], scale(t["levels"]["pctFrom52wHigh"], -35, 0), 1),
    ]
    p = t["patterns"]
    bonus = (6 if p.get("breakout") == "breakout" else -8 if p.get("breakout") == "breakdown" else 0) + \
            (4 if p.get("divergence") == "bullish" else -4 if p.get("divergence") == "bearish" else 0)
    out = aggregate(cs)
    if out["score"] is not None:
        out["score"] = round(min(max(out["score"] + bonus, 0), 100), 1)
    return out


def score_fundamental(metrics: list[dict], fair: dict, price: Optional[float]) -> dict:
    by = {m["key"]: m for m in metrics}
    sig = lambda k: {"good": 80, "neutral": 50, "bad": 20}.get(by.get(k, {}).get("signal"))  # noqa: E731
    keys = [("pe", 1), ("forwardPe", 1.5), ("peg", 1), ("evEbitda", 1), ("fcfYield", 1),
            ("revenueGrowth", 1.5), ("revenueCagr3y", 1), ("epsGrowth", 1.5), ("forwardEpsGrowth", 1),
            ("operatingMargin", 1.5), ("netMargin", 1), ("roe", 1), ("roic", 1),
            ("debtToEquity", 1), ("currentRatio", 0.7), ("interestCoverage", 0.7), ("altmanZ", 0.7), ("piotroski", 1)]
    cs = [comp(by[k]["name"], by[k]["value"], sig(k), w) for k, w in keys if k in by]
    mos = fair.get("marginOfSafety")
    cs.append(comp("Margin of safety %", mos, scale(mos, -40, 40), 2, detail="DCF/Graham fair value vs price"))
    return aggregate(cs)


def score_analyst(a: dict) -> dict:
    cs = [
        comp("Consensus (1=Strong Buy..5=Strong Sell)", a.get("consensusMean"), scale(a.get("consensusMean"), 4, 1.5), 3),
        comp("Price-target upside %", a.get("upsidePct"), scale(a.get("upsidePct"), -10, 30), 3),
        comp("Net upgrades (90d)", a.get("netUpgrades90d"), scale(a.get("netUpgrades90d"), -4, 4), 1.5),
        comp("EPS estimate revisions (net up)", a.get("revisionNet"), scale(a.get("revisionNet"), -4, 4), 1.5),
        comp("Earnings beat rate", a.get("beatRate"), scale(a.get("beatRate"), 0.25, 1.0), 1.5),
        comp("Avg earnings surprise %", a.get("avgSurprisePct"), scale(a.get("avgSurprisePct"), -5, 10), 1),
        comp("Avg post-earnings 1d move %", a.get("avgPostEarningsMove"), scale(a.get("avgPostEarningsMove"), -4, 4), 0.5),
    ]
    return aggregate(cs)


def score_sentiment(s: dict) -> dict:
    ins, sh, op = s.get("insider") or {}, s.get("short") or {}, s.get("options") or {}
    cs = [
        comp("News sentiment (-1..1)", s.get("newsScore"), scale(s.get("newsScore"), -0.6, 0.6), 3),
        # Count-based: routine selling at large caps is a weak signal, so the effect is capped to 30..70.
        comp("Insider buys vs sells (6m)", ins.get("netShares"),
             None if ins.get("buys") is None or (ins.get("buys", 0) + ins.get("sells", 0)) == 0
             else 50 + 20 * (ins["buys"] - ins["sells"]) / (ins["buys"] + ins["sells"]), 1,
             display=None if ins.get("buys") is None else f'{ins["buys"]} buys / {ins["sells"]} sells', detail="open-market transactions"),
        comp("Institutional ownership %", ins.get("institutionPct"), scale(ins.get("institutionPct"), 20, 80), 0.7),
        comp("Short interest % float", sh.get("pctFloat"), scale(sh.get("pctFloat"), 2, 20, invert=True), 1),
        comp("Put/Call ratio (OI)", op.get("putCall"), scale(op.get("putCall"), 1.3, 0.5), 1),
    ]
    return aggregate(cs)


def score_risk(r: dict) -> dict:
    rs = r.get("relativeStrength") or {}
    st = r.get("stats") or {}
    cs = [
        comp("Beta", r.get("beta"), scale(r.get("beta"), 1.8, 0.7), 1),
        comp("Max drawdown 1Y %", st.get("maxDrawdown"), scale(st.get("maxDrawdown"), -50, -8), 1.5),
        comp("Sharpe 1Y", st.get("sharpe"), scale(st.get("sharpe"), -0.5, 2), 1.5),
        comp("Sortino 1Y", st.get("sortino"), scale(st.get("sortino"), -0.5, 3), 0.5),
        comp("Annualized volatility %", st.get("volatility"), scale(st.get("volatility"), 60, 15), 1),
        comp("Rel. strength vs SPY 3M (pp)", (rs.get("3M") or {}).get("excess"), scale((rs.get("3M") or {}).get("excess"), -15, 15), 1.5),
        comp("Rel. strength vs SPY 1Y (pp)", (rs.get("1Y") or {}).get("excess"), scale((rs.get("1Y") or {}).get("excess"), -30, 30), 1),
        comp("VIX", r.get("vix"), scale(r.get("vix"), 32, 12), 0.7),
    ]
    sec = (r.get("sectorRelativeStrength") or {}).get("3M")
    if sec:
        cs.append(comp("Rel. strength vs sector 3M (pp)", sec["excess"], scale(sec["excess"], -12, 12), 1))
    return aggregate(cs)


# --------------------------------------------------------------- composite
def rating_for(score: Optional[float], bands: dict) -> str:
    if score is None:
        return "N/A"
    for name, lo in sorted(bands.items(), key=lambda kv: -kv[1]):
        if score >= lo:
            return name
    return "Strong Sell"


def confidence(pillars: dict, scores: dict, events: list[dict], coverage: float) -> dict:
    reasons, pts = [], 3
    if coverage < 0.7:
        pts -= 2 if coverage < 0.5 else 1
        reasons.append(f"data completeness {coverage:.0%}")
    vals = [s for s in scores.values() if s is not None]
    if len(vals) >= 2:
        spread = max(vals) - min(vals)
        if spread > 40:
            pts -= 1
            reasons.append(f"pillars disagree (spread {spread:.0f} pts)")
    near = [e for e in events if e.get("daysAway") is not None and 0 <= e["daysAway"] <= 14 and e.get("risk")]
    if near:
        pts -= 1
        reasons.append("event within 14 days: " + ", ".join(e["type"] for e in near))
    level = "High" if pts >= 3 else "Medium" if pts == 2 else "Low"
    return {"level": level, "reasons": reasons or ["data complete and pillars agree"]}


def horizon_views(scores: dict, bands: dict, hw: dict) -> dict:
    out = {}
    for h, weights in hw.items():
        num = den = 0.0
        for k, w in weights.items():
            if scores.get(k) is not None:
                num += scores[k] * w
                den += w
        sc = round(num / den, 1) if den else None
        out[h] = {"score": sc, "rating": rating_for(sc, bands)}
    return out


def trade_plan(price: Optional[float], tech: dict, analyst: dict) -> Optional[dict]:
    if not price or not tech.get("available"):
        return None
    lv, v = tech["levels"], tech["values"]
    atr_ = v.get("atr")
    sup, res = lv["support"], lv["resistance"]
    sma20 = next((s["value"] for s in tech["signals"] if s["name"] == "SMA 20"), None)
    sma50 = next((s["value"] for s in tech["signals"] if s["name"] == "SMA 50"), None)
    near_sup = sup[0] if sup else price * 0.95
    pullbacks = [x for x in (sma20, sma50, near_sup) if x and x <= price * 1.002]
    entry_lo = max(pullbacks) if pullbacks else price * 0.98
    entry_hi = price
    entry = round((entry_lo + entry_hi) / 2, 2)
    stops = [near_sup - 0.5 * atr_ if atr_ else near_sup * 0.98]
    if atr_:
        stops.append(entry - 2 * atr_)
    stop = round(min(max(stops), entry * 0.99), 2)  # tighter of support-based / 2xATR, but always below entry
    step = atr_ or entry * 0.03
    # ignore resistance within 1 ATR of entry: too close to be a meaningful target
    far = [r_ for r_ in res if r_ >= entry + step]
    t1 = far[0] if far else round(entry + 2 * step, 2)
    res = far
    t2 = analyst.get("targetMean") if analyst.get("targetMean") and analyst["targetMean"] > t1 else (res[1] if len(res) > 1 else round(t1 + 2 * (atr_ or entry * 0.03), 2))
    risk = entry - stop
    rr = round((t1 - entry) / risk, 2) if risk > 0 else None
    return {"entryZone": [round(entry_lo, 2), round(entry_hi, 2)], "entry": entry, "stopLoss": stop,
            "t1": round(t1, 2), "t2": round(t2, 2), "riskReward": rr,
            "rewardRiskT2": round((t2 - entry) / risk, 2) if risk > 0 else None}


def drivers(pillar_results: dict, n: int = 3) -> dict:
    items = []
    for pname, pr in pillar_results.items():
        for c in pr["components"]:
            if c["score"] is None:
                continue
            items.append({"pillar": pname, "metric": c["name"], "value": c["display"], "score": c["score"],
                          "impact": round((c["score"] - 50) * c["weight"], 1), "detail": c["detail"]})
    pos = sorted([i for i in items if i["score"] >= 60], key=lambda i: -i["impact"])[:n]
    neg = sorted([i for i in items if i["score"] <= 40], key=lambda i: i["impact"])[:n]
    return {"positive": pos, "negative": neg}


def recommend(pillar_results: dict, events: list[dict], price: Optional[float], tech: dict,
              analyst_data: dict, profile: str = "balanced", cfg: Optional[dict] = None) -> dict:
    cfg = cfg or load_config()
    weights = cfg["profiles"].get(profile) or cfg["profiles"]["balanced"]
    scores = {k: v["score"] for k, v in pillar_results.items()}
    num = den = cov_num = 0.0
    for k, w in weights.items():
        cov_num += w * (pillar_results[k]["coverage"] if scores.get(k) is not None else 0)
        if scores.get(k) is not None:
            num += scores[k] * w
            den += w
    composite = round(num / den, 1) if den else None
    coverage = cov_num / sum(weights.values())
    # Data-sparse guard: refuse a strong call when under-informed.
    rating = rating_for(composite, cfg["rating_bands"])
    if rating in ("Strong Buy", "Strong Sell") and coverage < 0.6:
        rating = "Buy" if rating == "Strong Buy" else "Sell"
    return {
        "rating": rating,
        "compositeScore": composite,
        "profile": profile,
        "weights": weights,
        "pillarScores": scores,
        "dataCoverage": round(coverage, 2),
        "confidence": confidence(pillar_results, scores, events, coverage),
        "horizons": horizon_views(scores, cfg["rating_bands"], cfg["horizons"]),
        "tradePlan": trade_plan(price, tech, analyst_data),
        "drivers": drivers(pillar_results),
    }
