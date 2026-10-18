"""Sector Pulse pipeline: collect -> understand -> score -> pick -> publish. Meant to run on a schedule (GitHub Actions cron),
never inside a web request. Every stage degrades on its own: a failed source lowers confidence, it does not stop the run.

    python -m sector_pulse run        # score all themes and store a snapshot
    python -m sector_pulse evaluate   # grade predictions whose horizon has elapsed
    python -m sector_pulse all
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import logging
import math
import os
import time
from contextlib import contextmanager
from typing import Optional

import numpy as np
import pandas as pd

from agent import news as N
from agent import orchestrator as O
from analytics import scoring as AS
from data_providers import yahoo as Y

from . import events as EV
from . import scoring as S
from . import store

log = logging.getLogger("sector_pulse")
VERSION = "sector-pulse-1.0"
HORIZONS = ("1W", "1M", "3M")


# ------------------------------------------------------------------ small helpers
def _row_hash(ticker: str, title: str) -> str:
    return hashlib.sha1(f"{ticker}|{title.lower().strip()[:120]}".encode()).hexdigest()


def _f(x, nd: int = 4) -> Optional[float]:
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), nd)


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


async def _map_limited(fn, items, limit: int):
    sem = asyncio.Semaphore(limit)

    async def one(x):
        async with sem:
            return await fn(x)
    return await asyncio.gather(*(one(x) for x in items))


async def load_histories(symbols: set[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    async def one(sym):
        try:
            df = await Y.get_price_history(sym, period)
            return sym, df if df is not None and len(df) else None
        except Exception as e:  # noqa: BLE001
            log.warning("history failed for %s: %s", sym, e)
            return sym, None
    res = await _map_limited(one, sorted(symbols), 6)
    return {s: df for s, df in res if df is not None}


def basket_close(closes: list[pd.Series]) -> Optional[pd.Series]:
    """Equal-weight index (start = 100) of several price series; used for themes with no clean benchmark ETF."""
    closes = [c for c in closes if c is not None and len(c) > 20]
    if len(closes) < 2:
        return None
    rets = pd.concat([c.pct_change() for c in closes], axis=1).mean(axis=1, skipna=True)
    return (1 + rets.fillna(0)).cumprod() * 100


def bench_series(theme: dict, hist: dict[str, pd.DataFrame]) -> tuple[Optional[pd.Series], str]:
    etf = theme.get("etf")
    if etf and etf in hist and len(hist[etf]) > 60:
        return hist[etf]["close"], "etf"
    return basket_close([hist[m]["close"] for m in theme["members"] if m in hist]), "basket"


def beta_vs(member: pd.Series, bench: pd.Series, days: int = 90) -> Optional[float]:
    df = pd.concat([member.pct_change(), bench.pct_change()], axis=1).dropna().tail(days)
    if len(df) < 40 or df.iloc[:, 1].var() == 0:
        return None
    return float(df.iloc[:, 0].cov(df.iloc[:, 1]) / df.iloc[:, 1].var())


def avg_dollar_volume(df: pd.DataFrame, days: int) -> Optional[float]:
    if df is None or len(df) < days:
        return None
    return float((df["close"] * df["volume"]).tail(days).mean())


# ------------------------------------------------------------------ news
async def collect_news(themes: list[dict], rules: dict) -> dict:
    """Fetch headlines for each theme's ETF + leading constituents, classify only the ones not seen before, store them."""
    cfg = rules["news"]
    tickers: list[str] = []
    for t in themes:
        for sym in ([t["etf"]] if t.get("etf") else []) + t["members"][: cfg["per_theme_tickers"]]:
            if sym not in tickers:
                tickers.append(sym)

    async def fetch(sym):
        try:
            return sym, await Y.get_news(sym, cfg["lookback_days"], cfg["per_ticker_items"])
        except Exception as e:  # noqa: BLE001
            log.warning("news failed for %s: %s", sym, e)
            return sym, []
    fetched = await _map_limited(fetch, tickers, 5)

    rows = []
    for sym, items in fetched:
        for n in items:
            if n.get("title"):
                rows.append({**n, "ticker": sym, "hash": _row_hash(sym, n["title"])})
    known = store.known_news_hashes([r["hash"] for r in rows])
    new = [r for r in rows if r["hash"] not in known]
    model = AS.load_config()["llm"]["model"]
    methods: dict[str, int] = {}
    for i in range(0, len(new), 25):
        chunk = new[i:i + 25]
        classified, method = await N.classify(chunk, model)
        methods[method] = methods.get(method, 0) + len(chunk)
        store.save_news([{**c, "hash": r["hash"], "ticker": r["ticker"], "method": method, "title": r["title"],
                          "url": r.get("url"), "source": r.get("source"), "time": r.get("time")} for c, r in zip(classified, chunk)])
    return {"tickers": len(tickers), "headlines": len(rows), "newClassified": len(new), "methods": methods}


# ------------------------------------------------------------------ events
async def collect_events(rules: dict) -> dict:
    src = rules["event_sources"]

    async def fetch(sym):
        try:
            return await Y.get_news(sym, 2, 15)
        except Exception:  # noqa: BLE001
            return []
    yahoo = await _map_limited(fetch, src["macro_tickers"], 4)
    headlines = [h for lst in yahoo for h in lst]
    gdelt = await EV.fetch_gdelt(rules)
    detected = EV.detect(headlines + gdelt, rules)
    for e in detected:
        store.upsert_event(e)
    return {"headlines": len(headlines) + len(gdelt), "gdelt": len(gdelt), "detected": [(e["type"], e["severity"]) for e in detected]}


# ------------------------------------------------------------------ Module A scores used for ranking
def _lexicon_only_classify():
    async def classify(items, model):
        out = []
        for n in items:
            c = N.lexicon_classify(n["title"])
            out.append({**{k: n.get(k) for k in ("title", "source", "time", "url")}, "sentiment": c["sentiment"],
                        "impact": c["impact"], "reason": c["reason"], "catalyst": c.get("catalyst", "none")})
        return out, "lexicon"
    return classify


@contextmanager
def _no_llm_news():
    """Module A classifies news with the LLM even for use_llm=False. For bulk ranking use the free lexicon instead."""
    original = N.classify
    N.classify = _lexicon_only_classify()
    try:
        yield
    finally:
        N.classify = original


async def refresh_stock_scores(tickers: list[str], budget: int, stale_hours: float) -> dict:
    existing = store.stock_scores(tickers)
    now = time.time()
    missing = [t for t in tickers if t not in existing]
    stale = sorted((t for t in tickers if t in existing and now - existing[t]["as_of"] > stale_hours * 3600),
                   key=lambda t: existing[t]["as_of"])
    todo = (missing + stale)[:budget]
    ok = failed = 0

    async def one(t):
        nonlocal ok, failed
        try:
            p = await O.analyze(t, "balanced", use_llm=False)
            rec = p["recommendation"]
            store.save_stock_score(t, rec.get("compositeScore"), rec.get("rating"), (p.get("sentiment") or {}).get("newsScore"), p.get("company"))
            ok += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            log.warning("stock analysis failed for %s: %s", t, e)
    with _no_llm_news():
        await _map_limited(one, todo, 3)
    return {"missing": len(missing), "stale": len(stale), "refreshed": ok, "failed": failed, "budget": budget}


# ------------------------------------------------------------------ scoring one theme
def _drivers(theme: dict, bench_sym: str, m: dict, news_items: list[dict], active: dict, rules: dict, now: dt.datetime) -> dict:
    """Plain-English reasons, each with a strength used only for ordering. Positive and negative are returned separately."""
    ds: list[dict] = []
    h = "1M"
    ex, rt, rs = m["excess"].get(h), m["ret"].get(h), m["spy_ret"].get(h)
    if ex is not None and rt is not None:
        ds.append({"factor": "momentum", "strength": abs(math.tanh(ex / rules["horizons"][h]["scale"])) * 0.5,
                   "sign": 1 if ex >= 0 else -1,
                   "text": f"{bench_sym} {_pct(rt)} over 1M vs SPY {_pct(rs)} ({_pct(ex)} relative)"})
    if m["breadth"] is not None:
        ds.append({"factor": "momentum", "strength": abs(m["breadth"] - 0.5) * 0.6, "sign": 1 if m["breadth"] >= 0.5 else -1,
                   "text": f"{round(m['breadth'] * 100)}% of constituents trade above their 50-day average"})
    if m["trend"] is not None and abs(m["trend"]) >= 0.99:
        ds.append({"factor": "momentum", "strength": 0.2, "sign": 1 if m["trend"] > 0 else -1,
                   "text": f"{bench_sym} is {'above' if m['trend'] > 0 else 'below'} both its 50- and 200-day averages"})
    if m["flows"] is not None and abs(m["flows"]) >= 0.25:
        ds.append({"factor": "flows", "strength": abs(m["flows"]) * 0.3, "sign": 1 if m["flows"] > 0 else -1,
                   "text": f"Trading volume {'surging into' if m['flows'] > 0 else 'surging out of'} the sector (flow proxy)"})
    sev_w = rules["event_severity_weight"]
    for ev in m["events"]:
        imp = rules["impact_matrix"].get(ev["type"], {}).get(theme["id"], 0)
        if imp:
            hl = ev["headlines"][0] if ev["headlines"] else {}
            ds.append({"factor": "events", "strength": abs(imp) * active.get(ev["type"], 0), "sign": 1 if imp > 0 else -1,
                       "text": f"{ev['type'].replace('_', ' ').capitalize()} ({ev['severity']} severity, {ev['n_sources']} outlets): "
                               f"{'tailwind' if imp > 0 else 'headwind'} for this sector", "url": hl.get("url"), "source": hl.get("source")})
    for it in news_items:
        s = S.SENTIMENT_SIGN.get(it["sentiment"], 0)
        if not s:
            continue
        try:
            age = (now - dt.datetime.fromisoformat(str(it["time"]).replace("Z", "+00:00"))).total_seconds() / 86400
        except (TypeError, ValueError):
            age = rules["news"]["half_life_days"]
        ds.append({"factor": "news", "strength": S.IMPACT_W.get(it["impact"], 1) * S.decay(age, rules["news"]["half_life_days"]) / 10,
                   "sign": s, "text": it["title"], "url": it.get("url"), "source": it.get("source")})
    pos = sorted((d for d in ds if d["sign"] > 0), key=lambda d: -d["strength"])[:3]
    neg = sorted((d for d in ds if d["sign"] < 0), key=lambda d: -d["strength"])[:3]
    strip = lambda d: {k: d[k] for k in ("factor", "text", "url", "source") if d.get(k)}  # noqa: E731
    return {"positive": [strip(d) for d in pos], "negative": [strip(d) for d in neg]}


def score_theme(theme: dict, hist: dict[str, pd.DataFrame], rules: dict, news_items: list[dict], events: list[dict], now: dt.datetime) -> dict:
    spy_sym = rules["benchmark"]
    spy = hist[spy_sym]["close"] if spy_sym in hist else None
    bench, bench_kind = bench_series(theme, hist)
    bench_sym = theme["etf"] if bench_kind == "etf" else "equal-weight basket"
    member_closes = {m: hist[m]["close"] for m in theme["members"] if m in hist}

    m: dict = {"ret": {}, "spy_ret": {}, "excess": {}, "events": [], "bench_kind": bench_kind}
    for h in HORIZONS:
        d = rules["horizons"][h]["days"]
        m["ret"][h] = S.period_return(bench, d) if bench is not None else None
        m["spy_ret"][h] = S.period_return(spy, d) if spy is not None else None
        m["excess"][h] = m["ret"][h] - m["spy_ret"][h] if m["ret"][h] is not None and m["spy_ret"][h] is not None else None
    m["breadth"] = S.pct_above_sma(list(member_closes.values()), 50)
    m["trend"] = S.trend_signal(bench) if bench is not None else None
    etf_df = hist.get(theme.get("etf") or "")
    fd, sd = rules["flows"]["fast_days"], rules["flows"]["slow_days"]
    m["flows"] = S.flows_signal(avg_dollar_volume(etf_df, fd), avg_dollar_volume(etf_df, sd), m["ret"]["1M"]) if bench_kind == "etf" else None

    news_sig, n_news = S.news_signal(news_items, now, rules)
    active = S.active_event_weights(events, rules, now)
    ev_sig = S.event_signal(active, theme["id"], rules)
    m["events"] = [e for e in events if e["type"] in active and rules["impact_matrix"].get(e["type"], {}).get(theme["id"])]

    horizons: dict[str, dict] = {}
    for h in HORIZONS:
        mom = S.momentum_signal(m["excess"][h], m["breadth"], m["trend"], rules, h)
        sigs = {"momentum": mom, "earnings": None, "news": news_sig, "events": ev_sig, "social": None, "flows": m["flows"]}
        scores = {k: (S.to_score(v) if v is not None else None) for k, v in sigs.items()}
        w = rules["weights"][h]
        comp, used, missing = S.composite(scores, w)
        conf, why = S.confidence(scores, w, n_news, rules)
        horizons[h] = {"score": comp, "direction": S.direction(comp, rules), "probUp": S.prob_up(comp, rules),
                       "confidence": conf, "confidenceReasons": why, "missingFactors": missing,
                       "excess": _f(m["excess"][h]),
                       "factors": {k: {"signal": _f(sigs[k]), "score": scores[k], "weight": _f(used.get(k, 0.0))} for k in sigs}}

    return {"theme": theme["id"], "name": theme["name"], "group": theme["group"],
            "benchmark": {"symbol": bench_sym, "kind": bench_kind, "last": _f(bench.iloc[-1]) if bench is not None else None},
            "horizons": horizons,
            "metrics": {"returns": {h: _f(m["ret"][h]) for h in HORIZONS}, "spyReturns": {h: _f(m["spy_ret"][h]) for h in HORIZONS},
                        "breadth": _f(m["breadth"]), "trend": _f(m["trend"]), "flowsProxy": _f(m["flows"]),
                        "newsSignal": _f(news_sig), "newsItems": n_news, "eventSignal": _f(ev_sig)},
            "drivers": _drivers(theme, bench_sym, m, news_items, active, rules, now),
            "events": [{"type": e["type"], "severity": e["severity"], "nSources": e["n_sources"],
                        "impact": rules["impact_matrix"][e["type"]][theme["id"]], "headline": (e["headlines"] or [{}])[0]} for e in m["events"]],
            "news": [{k: it.get(k) for k in ("title", "url", "source", "time", "sentiment", "impact")} for it in news_items[:8]],
            "version": VERSION}


def build_picks(theme: dict, snap: dict, hist: dict[str, pd.DataFrame], bench: Optional[pd.Series], scores: dict, rules: dict) -> dict:
    cfg = rules["picks"]
    theme_score = snap["horizons"]["1M"]["score"] or 50.0
    rows, excluded = [], []
    for sym in theme["members"]:
        df = hist.get(sym)
        if df is None or len(df) < 30:
            excluded.append({"ticker": sym, "reason": "no price data"})
            continue
        dv = avg_dollar_volume(df, 20)
        if dv is not None and dv < cfg["min_dollar_volume"]:
            excluded.append({"ticker": sym, "reason": "below liquidity minimum"})
            continue
        close = df["close"]
        r1m = S.period_return(close, rules["horizons"]["1M"]["days"])
        tr = S.period_return(bench, rules["horizons"]["1M"]["days"]) if bench is not None else None
        rs = r1m - tr if r1m is not None and tr is not None else None
        beta = beta_vs(close, bench) if bench is not None else None
        sc = scores.get(sym) or {}
        rank = S.rank_score(sc.get("composite"), sc.get("news_score"), rs, S.sensitivity_score(beta, theme_score), rules)
        rows.append({"ticker": sym, "name": sc.get("name"), "rank": rank, "composite": _f(sc.get("composite"), 1), "rating": sc.get("rating"),
                     "newsScore": _f(sc.get("news_score"), 2), "ret1M": _f(r1m), "relativeStrength": _f(rs), "beta": _f(beta, 2),
                     "price": _f(close.iloc[-1], 2), "pending": sc.get("composite") is None})
    rows.sort(key=lambda r: -r["rank"])
    k = min(cfg["leaders"], len(rows) // 2)  # leaders and laggards never overlap
    return {"leaders": rows[:k], "laggards": list(reversed(rows[len(rows) - k:])) if k else [], "all": len(rows), "excluded": excluded}


# ------------------------------------------------------------------ run
async def run(budget: Optional[int] = None) -> dict:
    themes_cfg, rules = S.load_yaml("themes.yaml"), S.load_yaml("rules.yaml")
    themes = themes_cfg["themes"]
    budget = budget if budget is not None else int(os.getenv("SECTOR_ANALYZE_BUDGET", "40"))
    run_id = store.start_run()
    started = time.time()
    stats: dict = {"errors": []}
    now = dt.datetime.now(dt.timezone.utc)
    try:
        symbols = {rules["benchmark"]} | {t["etf"] for t in themes if t.get("etf")} | {m for t in themes for m in t["members"]}
        hist = await load_histories(symbols)
        stats["prices"] = {"requested": len(symbols), "loaded": len(hist)}
        if rules["benchmark"] not in hist:
            stats["errors"].append("benchmark SPY history unavailable: relative-strength signals are skipped")

        try:
            stats["news"] = await collect_news(themes, rules)
        except Exception as e:  # noqa: BLE001
            log.exception("news stage failed")
            stats["errors"].append(f"news: {e}")
        try:
            stats["events"] = await collect_events(rules)
        except Exception as e:  # noqa: BLE001
            log.exception("event stage failed")
            stats["errors"].append(f"events: {e}")

        all_members = list(dict.fromkeys(m for t in themes for m in t["members"] if m in hist))
        try:
            stats["stockScores"] = await refresh_stock_scores(all_members, budget, rules["picks"]["stale_hours"])
        except Exception as e:  # noqa: BLE001
            log.exception("stock score stage failed")
            stats["errors"].append(f"stock scores: {e}")

        events = store.recent_events()
        scores = store.stock_scores(all_members)
        since = (now - dt.timedelta(days=rules["news"]["lookback_days"])).isoformat()
        as_of = int(time.time())
        snaps = []
        for th in themes:
            try:
                tickers = ([th["etf"]] if th.get("etf") else []) + th["members"][: rules["news"]["per_theme_tickers"]]
                items = store.news_for(tickers, since)
                snap = score_theme(th, hist, rules, items, events, now)
                bench, _ = bench_series(th, hist)
                snap["picks"] = build_picks(th, snap, hist, bench, scores, rules)
                snaps.append(snap)
            except Exception as e:  # noqa: BLE001
                log.exception("scoring failed for %s", th["id"])
                stats["errors"].append(f"{th['id']}: {e}")

        ranked = sorted(snaps, key=lambda s: -(s["horizons"]["1M"]["score"] or 0))
        for i, s in enumerate(ranked, 1):
            s["rank"] = i
            s["asOf"] = as_of
        for s in snaps:
            store.save_snapshot(run_id, s["theme"], as_of, s)
        stats["themes"] = len(snaps)
        stats["predictionsLogged"] = log_predictions(snaps, themes, hist, rules, as_of)
        status = "ok" if snaps and not stats["errors"] else "degraded" if snaps else "failed"
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline failed")
        stats["errors"].append(str(e))
        status = "failed"
    stats["seconds"] = round(time.time() - started, 1)
    store.finish_run(run_id, status, stats)
    log.info("run %s %s: %s", run_id, status, stats)
    return {"runId": run_id, "status": status, **stats}


def log_predictions(snaps: list[dict], themes: list[dict], hist: dict, rules: dict, as_of: int) -> int:
    """One prediction per theme/horizon per UTC day (the first run of the day), so accuracy is not inflated by duplicates."""
    day = dt.datetime.fromtimestamp(as_of, dt.timezone.utc).date().isoformat()
    spy = hist.get(rules["benchmark"])
    by_id = {t["id"]: t for t in themes}
    n = 0
    for s in snaps:
        th = by_id[s["theme"]]
        base = S.baseline_label(s["horizons"]["1M"]["excess"], rules)
        for h in HORIZONS:
            hz = s["horizons"][h]
            if hz["score"] is None:
                continue
            store.log_prediction({"theme": s["theme"], "horizon": h, "made_at": as_of, "day": day, "label": hz["direction"],
                                  "score": hz["score"], "prob_up": hz["probUp"], "confidence": hz["confidence"], "baseline_label": base,
                                  "bench": s["benchmark"]["symbol"],
                                  "entry_px": s["benchmark"]["last"] if s["benchmark"]["kind"] == "etf" else None,
                                  "spy_entry": _f(spy["close"].iloc[-1]) if spy is not None else None,
                                  "evaluate_at": as_of + rules["horizons"][h]["eval_days"] * 86400})
            n += 1
    return n


# ------------------------------------------------------------------ evaluation
def _px_on(series: pd.Series, when: dt.datetime) -> Optional[float]:
    s = series[series.index <= pd.Timestamp(when.date())]
    return float(s.iloc[-1]) if len(s) else None


async def evaluate(now: Optional[int] = None) -> dict:
    """Grade predictions whose horizon has elapsed: excess return of the theme benchmark over SPY between the two dates."""
    themes_cfg, rules = S.load_yaml("themes.yaml"), S.load_yaml("rules.yaml")
    by_id = {t["id"]: t for t in themes_cfg["themes"]}
    now = now or int(time.time())
    due = store.due_predictions(now)
    if not due:
        return {"due": 0, "graded": 0}
    needed = {rules["benchmark"]} | {s for p in due if p["theme"] in by_id
                                     for s in ([by_id[p["theme"]].get("etf")] if by_id[p["theme"]].get("etf") else by_id[p["theme"]]["members"]) if s}
    hist = await load_histories(needed, "2y")
    spy = hist.get(rules["benchmark"])
    graded = skipped = 0
    for p in due:
        th = by_id.get(p["theme"])
        if th is None:
            store.save_outcome(p["id"], None, None, None, "n/a", 0, 0)
            continue
        bench, _ = bench_series(th, hist)
        t0, t1 = (dt.datetime.fromtimestamp(p[k], dt.timezone.utc) for k in ("made_at", "evaluate_at"))
        if bench is None or spy is None or bench.index[-1] < pd.Timestamp(t1.date()) - pd.Timedelta(days=4):
            skipped += 1  # price data does not reach the evaluation date yet: try again next run
            continue
        b0, b1, s0, s1 = _px_on(bench, t0), _px_on(bench, t1), _px_on(spy, t0), _px_on(spy, t1)
        if None in (b0, b1, s0, s1):
            skipped += 1
            continue
        excess = (b1 / b0 - 1) - (s1 / s0 - 1)
        outcome = S.outcome_label(excess, rules["horizons"][p["horizon"]]["flat_band"])
        store.save_outcome(p["id"], b1, s1, excess, outcome, int(outcome == p["label"]), int(outcome == p["baseline_label"]))
        graded += 1
    return {"due": len(due), "graded": graded, "skipped": skipped}
