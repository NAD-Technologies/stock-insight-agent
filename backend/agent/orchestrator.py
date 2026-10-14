"""Agent workflow: runs the data tools in the specified order (independent ones concurrently), then the
deterministic scorer, then the LLM narrative. Every step is traced and failures degrade per-section."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from typing import Any, Awaitable, Callable, Optional

import numpy as np
import pandas as pd

from analytics import fundamental as F
from analytics import risk as R
from analytics import scoring as S
from analytics import technical as T
from data_providers import enrichment as E
from data_providers import yahoo as Y
from data_providers.cache import ttl_cache

from . import news as N
from . import narrative as NR

log = logging.getLogger("agent")
DISCLAIMER = "Educational analysis only — not financial advice. Data may be delayed."


class Trace:
    def __init__(self):
        self.steps: list[dict] = []

    async def run(self, name: str, coro: Awaitable[Any], default: Any = None):
        t0 = time.perf_counter()
        try:
            res = await coro
            self.steps.append({"tool": name, "ok": True, "ms": int((time.perf_counter() - t0) * 1000)})
            return res
        except Y.TickerNotFound:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("tool %s failed: %s", name, e)
            self.steps.append({"tool": name, "ok": False, "ms": int((time.perf_counter() - t0) * 1000), "error": type(e).__name__})
            return default


def _series(idx, vals) -> list[dict]:
    return [{"time": ts.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for ts, v in zip(idx, vals) if pd.notna(v)]


def _markers(ind: pd.DataFrame, df: pd.DataFrame, since) -> list[dict]:
    m = []
    d = np.sign(ind["macd"] - ind["macd_signal"])
    cross = d.ne(d.shift()) & d.shift().notna() & (d != 0)
    for ts in ind.index[cross & (ind.index >= since)]:
        up = d[ts] > 0
        m.append({"time": ts.strftime("%Y-%m-%d"), "type": "buy" if up else "sell", "label": "MACD " + ("↑" if up else "↓")})
    gd = np.sign(ind["sma50"] - ind["sma200"])
    gc = gd.ne(gd.shift()) & gd.shift().notna() & (gd != 0) & ind["sma200"].notna()
    for ts in ind.index[gc & (ind.index >= since)]:
        up = gd[ts] > 0
        m.append({"time": ts.strftime("%Y-%m-%d"), "type": "buy" if up else "sell", "label": "Golden X" if up else "Death X"})
    return sorted(m, key=lambda x: x["time"])


def build_chart(df: pd.DataFrame, intraday: pd.DataFrame, tech: dict) -> dict:
    if df.empty:
        return {"ohlcv": [], "indicators": {}, "markers": [], "intraday": []}
    ind = T.compute_indicator_series(df)
    since = df.index[-1] - pd.Timedelta(days=730)
    ohlcv = [{"time": ts.strftime("%Y-%m-%d"), "open": round(r.open, 4), "high": round(r.high, 4), "low": round(r.low, 4),
              "close": round(r.close, 4), "volume": int(r.volume)} for ts, r in df.iterrows()]
    indicators = {c: _series(ind.index, ind[c].values) for c in
                  ("sma20", "sma50", "sma200", "ema9", "ema21", "bb_upper", "bb_mid", "bb_lower", "vwap", "rsi", "macd", "macd_signal", "macd_hist")}
    intr = []
    if intraday is not None and not intraday.empty:
        tp = (intraday["high"] + intraday["low"] + intraday["close"]) / 3
        day = intraday.index.normalize()
        cv = (tp * intraday["volume"]).groupby(day).cumsum() / intraday["volume"].groupby(day).cumsum().replace(0, np.nan)  # session VWAP
        for (ts, r), vw in zip(intraday.iterrows(), cv.values):
            intr.append({"time": int(ts.replace(tzinfo=dt.timezone.utc).timestamp()), "open": round(r.open, 4), "high": round(r.high, 4),
                         "low": round(r.low, 4), "close": round(r.close, 4), "volume": int(r.volume),
                         "vwap": None if pd.isna(vw) else round(float(vw), 4)})
    return {"ohlcv": ohlcv, "indicators": indicators, "markers": _markers(ind, df, since), "intraday": intr,
            "levels": {"support": tech.get("levels", {}).get("support", []), "resistance": tech.get("levels", {}).get("resistance", [])}}


def _statement_series(f: dict) -> dict:
    pick = lambda rows, k: [{"period": r["period"], "value": r.get(k)} for r in reversed(rows)]  # noqa: E731
    return {
        "annual": {"revenue": pick(f.get("annual", []), "revenue"), "eps": pick(f.get("annual", []), "eps"),
                   "grossMargin": pick(f.get("annual", []), "grossMargin"), "operatingMargin": pick(f.get("annual", []), "operatingMargin"),
                   "netMargin": pick(f.get("annual", []), "netMargin")},
        "quarterly": {"revenue": pick(f.get("quarterly", []), "revenue"), "eps": pick(f.get("quarterly", []), "eps"),
                      "grossMargin": pick(f.get("quarterly", []), "grossMargin"), "operatingMargin": pick(f.get("quarterly", []), "operatingMargin"),
                      "netMargin": pick(f.get("quarterly", []), "netMargin")},
    }


@ttl_cache(120)
async def analyze(ticker: str, profile: str = "balanced", use_llm: bool = True) -> dict:
    cfg = S.load_config()
    tr = Trace()
    ticker = ticker.strip().upper()

    # 1. quote (raises TickerNotFound for unknown symbols)
    quote = await tr.run("get_quote", Y.get_quote(ticker))
    # 2. history (5y daily for chart/indicators) + 5m intraday for the 1D view
    hist, intraday = await asyncio.gather(
        tr.run("get_price_history", Y.get_price_history(ticker, "5y", "1d"), pd.DataFrame()),
        tr.run("get_price_history_intraday", Y.get_price_history(ticker, "5d", "5m"), pd.DataFrame()))
    price = quote["price"]
    sector = quote.get("sector")
    # 3. technicals (sync CPU work, small)
    tech = await tr.run("compute_technicals", asyncio.to_thread(T.compute_technicals, hist), {"available": False, "signals": [], "summary": {}})
    hv = T.hist_vol(hist["close"]) if len(hist) > 60 else None
    # 4-9 independent fetchers, concurrently
    fund_raw, analyst, flow, raw_news, ctx, events = await asyncio.gather(
        tr.run("get_fundamentals", Y.get_fundamentals(ticker), {}),
        tr.run("get_analyst_view", Y.get_analyst_view(ticker, price, hist), {}),
        tr.run("get_ownership_and_flow", Y.get_ownership_and_flow(ticker, hv.tail(252) if hv is not None else None), {}),
        tr.run("get_news", _gather_news(ticker), []),
        tr.run("get_market_context", Y.get_market_context(ticker, sector, hist["close"] if len(hist) else pd.Series(dtype=float)), {}),
        tr.run("get_events", Y.get_events(ticker), []),
    )
    # fundamentals
    f = F.derive(fund_raw, price) if fund_raw else {}
    metrics = F.build_metrics(f, sector) if f else []
    fair = F.fair_value(f, price, cfg["dcf"]["wacc"], cfg["dcf"]["terminal_growth"]) if f else {"low": None, "base": None, "high": None, "marginOfSafety": None}
    # news
    model = cfg["llm"]["model"]
    news_items, news_method = await N.classify(raw_news[: cfg["llm"]["max_news_items"]], model) if use_llm or raw_news else ([], "none")
    news_score = N.news_score(news_items)
    # risk
    stats = R.risk_stats(hist["close"]) if len(hist) else {}
    spy = ctx.get("spy") if ctx else None
    rel = R.relative_strength(hist["close"], spy) if len(hist) and spy is not None else {}
    sec_rel = R.relative_strength(hist["close"], ctx.get("sectorSeries")) if ctx and ctx.get("sectorSeries") is not None and len(hist) else {}
    ten = (ctx or {}).get("tenYear")
    fred = await E.fred_10y()
    ten = fred or ten
    risk = {"beta": quote.get("beta"), "stats": stats, "relativeStrength": rel, "sectorRelativeStrength": sec_rel,
            "sectorEtf": (ctx or {}).get("sectorEtf"), "vix": (ctx or {}).get("vix"), "vixRegime": R.vix_regime((ctx or {}).get("vix")),
            "tenYear": ten, "events": events or []}
    sentiment = {"news": news_items, "newsScore": news_score, "newsMethod": news_method,
                 "catalysts": sorted({n["catalyst"] for n in news_items if n.get("catalyst") not in (None, "none")}),
                 "insider": (flow or {}).get("insider"), "short": (flow or {}).get("short"), "options": (flow or {}).get("options")}

    # 10. deterministic scoring
    pillars = {
        "technical": S.score_technical(tech),
        "fundamental": S.score_fundamental(metrics, fair, price),
        "analyst": S.score_analyst(analyst or {}),
        "sentiment": S.score_sentiment(sentiment),
        "risk": S.score_risk(risk),
    }
    rec = S.recommend(pillars, events or [], price, tech, analyst or {}, profile, cfg)
    for k, v in pillars.items():
        v["verdict"] = S.verdict(v["score"])
    risk["score"] = pillars["risk"]["score"]

    payload = {
        "ticker": ticker, "company": quote["name"], "asOf": dt.datetime.now(dt.timezone.utc).isoformat(),
        "quote": quote,
        "chart": build_chart(hist, intraday, tech),
        "technical": {**tech, "score": pillars["technical"]["score"], "pillar": pillars["technical"], "verdict": pillars["technical"]["verdict"]},
        "fundamental": {"metrics": metrics, "vsSector": F.valuation_vs_sector(f, sector) if f else {}, "fairValue": fair,
                        "series": _statement_series(f) if f else {}, "score": pillars["fundamental"]["score"],
                        "pillar": pillars["fundamental"], "verdict": pillars["fundamental"]["verdict"]},
        "analyst": {**(analyst or {}), "score": pillars["analyst"]["score"], "pillar": pillars["analyst"], "verdict": pillars["analyst"]["verdict"]},
        "sentiment": {**sentiment, "score": pillars["sentiment"]["score"], "pillar": pillars["sentiment"], "verdict": pillars["sentiment"]["verdict"]},
        "risk": {**risk, "pillar": pillars["risk"], "verdict": pillars["risk"]["verdict"]},
        "recommendation": rec,
        "agentTrace": tr.steps,
        "dataSources": ["Yahoo Finance (yfinance)"] + [n for n, k in (("Finnhub", "FINNHUB_API_KEY"), ("Alpha Vantage", "ALPHAVANTAGE_API_KEY"), ("FRED", "FRED_API_KEY"))
                                                       if __import__("os").getenv(k)],
        "disclaimer": DISCLAIMER,
    }
    payload["narrative"] = await NR.synthesize(payload, model) if use_llm else NR.template_narrative(payload)
    return payload


async def _gather_news(ticker: str) -> list[dict]:
    y, fh, av = await asyncio.gather(Y.get_news(ticker), E.finnhub_news(ticker), E.alphavantage_news(ticker), return_exceptions=True)
    merged, seen = [], set()
    for lst in (y, fh, av):
        if isinstance(lst, Exception):
            continue
        for n in lst:
            key = (n.get("title") or "").lower()[:80]
            if key and key not in seen:
                seen.add(key)
                merged.append(n)
    merged.sort(key=lambda n: n.get("time") or "", reverse=True)
    return merged


def condensed(p: dict) -> dict:
    """Compact per-ticker summary for the compare view."""
    q, r = p["quote"], p["recommendation"]
    m = {x["key"]: x["value"] for x in p["fundamental"]["metrics"]}
    return {"ticker": p["ticker"], "company": p["company"], "price": q["price"], "changePct": q["changePct"], "marketCap": q["marketCap"],
            "rating": r["rating"], "compositeScore": r["compositeScore"], "confidence": r["confidence"]["level"],
            "pillarScores": r["pillarScores"], "horizons": r["horizons"],
            "metrics": {k: m.get(k) for k in ("pe", "forwardPe", "revenueGrowth", "operatingMargin", "roe", "debtToEquity", "fcfYield")},
            "upsidePct": p["analyst"].get("upsidePct"), "rsi": (p["technical"].get("values") or {}).get("rsi"),
            "sharpe": (p["risk"].get("stats") or {}).get("sharpe"), "maxDrawdown": (p["risk"].get("stats") or {}).get("maxDrawdown")}
