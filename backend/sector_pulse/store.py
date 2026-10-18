"""Database access for Sector Pulse (works on SQLite and Postgres through api.db._run)."""
from __future__ import annotations

import json
import time
from typing import Optional

from api.db import _run


def _loads(s: Optional[str], default=None):
    try:
        return json.loads(s) if s else default
    except ValueError:
        return default


# ------------------------------------------------------------------ runs
def start_run() -> int:
    now = int(time.time())
    _run("INSERT INTO sp_runs (started, status) VALUES (?, 'running')", (now,))
    return _run("SELECT id FROM sp_runs WHERE started=? ORDER BY id DESC LIMIT 1", (now,), many=True)[0]["id"]


def finish_run(run_id: int, status: str, stats: dict) -> None:
    _run("UPDATE sp_runs SET finished=?, status=?, stats=? WHERE id=?", (int(time.time()), status, json.dumps(stats), run_id))


def last_runs(limit: int = 10) -> list[dict]:
    rows = _run("SELECT * FROM sp_runs ORDER BY id DESC LIMIT ?", (limit,), many=True)
    for r in rows:
        r["stats"] = _loads(r.get("stats"), {})
    return rows


# ------------------------------------------------------------------ snapshots
def save_snapshot(run_id: int, theme: str, as_of: int, payload: dict) -> None:
    _run("INSERT INTO sp_snapshots (run_id, theme, as_of, payload) VALUES (?,?,?,?)", (run_id, theme, as_of, json.dumps(payload)))


def latest_snapshots() -> list[dict]:
    rows = _run("""SELECT s.theme, s.as_of, s.payload FROM sp_snapshots s
                   JOIN (SELECT theme, MAX(as_of) AS m FROM sp_snapshots GROUP BY theme) x
                     ON s.theme = x.theme AND s.as_of = x.m""", many=True)
    return [{**_loads(r["payload"], {}), "asOf": r["as_of"]} for r in rows]


def latest_snapshot(theme: str) -> Optional[dict]:
    rows = _run("SELECT as_of, payload FROM sp_snapshots WHERE theme=? ORDER BY as_of DESC LIMIT 1", (theme,), many=True)
    return {**_loads(rows[0]["payload"], {}), "asOf": rows[0]["as_of"]} if rows else None


def score_history(theme: str, limit: int = 90) -> list[dict]:
    rows = _run("SELECT as_of, payload FROM sp_snapshots WHERE theme=? ORDER BY as_of DESC LIMIT ?", (theme, limit), many=True)
    out = []
    for r in reversed(rows):
        h = (_loads(r["payload"], {}) or {}).get("horizons", {})
        out.append({"asOf": r["as_of"], **{k: (v or {}).get("score") for k, v in h.items()}})
    return out


# ------------------------------------------------------------------ events
def upsert_event(ev: dict) -> None:
    _run("""INSERT INTO sp_events (id, type, severity, first_seen, last_seen, n_headlines, n_sources, headlines)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET severity=excluded.severity, last_seen=excluded.last_seen,
              n_headlines=excluded.n_headlines, n_sources=excluded.n_sources, headlines=excluded.headlines""",
         (ev["id"], ev["type"], ev["severity"], ev["first_seen"], ev["last_seen"], ev["n_headlines"], ev["n_sources"],
          json.dumps(ev["headlines"])))


def recent_events(max_age_days: int = 120) -> list[dict]:
    rows = _run("SELECT * FROM sp_events WHERE last_seen >= ? ORDER BY last_seen DESC", (int(time.time()) - max_age_days * 86400,), many=True)
    for r in rows:
        r["headlines"] = _loads(r.get("headlines"), [])
    return rows


# ------------------------------------------------------------------ news cache
def known_news_hashes(hashes: list[str]) -> set[str]:
    if not hashes:
        return set()
    out: set[str] = set()
    for i in range(0, len(hashes), 200):
        chunk = hashes[i:i + 200]
        rows = _run(f"SELECT hash FROM sp_news WHERE hash IN ({','.join('?' * len(chunk))})", tuple(chunk), many=True)
        out |= {r["hash"] for r in rows}
    return out


def save_news(items: list[dict]) -> None:
    for n in items:
        _run("""INSERT INTO sp_news (hash, title, url, source, published, sentiment, impact, catalyst, reason, method, ticker, fetched)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(hash) DO NOTHING""",
             (n["hash"], n["title"], n.get("url"), n.get("source"), n.get("time"), n["sentiment"], n["impact"],
              n.get("catalyst"), n.get("reason"), n.get("method"), n.get("ticker"), int(time.time())))


def news_for(tickers: list[str], since_iso: str) -> list[dict]:
    if not tickers:
        return []
    rows = _run(f"""SELECT hash, title, url, source, published AS time, sentiment, impact, catalyst, reason, method, ticker
                    FROM sp_news WHERE ticker IN ({','.join('?' * len(tickers))}) AND published >= ?
                    ORDER BY published DESC""", tuple(tickers) + (since_iso,), many=True)
    seen, out = set(), []
    for r in rows:  # one headline can be tagged to several tickers (hash is per ticker+title); count it once per theme
        key = (r["title"] or "").lower().strip()[:120]
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ------------------------------------------------------------------ Module A scores for ranking
def stock_scores(tickers: list[str]) -> dict[str, dict]:
    if not tickers:
        return {}
    rows = _run(f"SELECT * FROM sp_stock_scores WHERE ticker IN ({','.join('?' * len(tickers))})", tuple(tickers), many=True)
    return {r["ticker"]: r for r in rows}


def save_stock_score(ticker: str, composite: Optional[float], rating: Optional[str], news_score: Optional[float], name: Optional[str]) -> None:
    _run("""INSERT INTO sp_stock_scores (ticker, as_of, composite, rating, news_score, name) VALUES (?,?,?,?,?,?)
            ON CONFLICT(ticker) DO UPDATE SET as_of=excluded.as_of, composite=excluded.composite, rating=excluded.rating,
              news_score=excluded.news_score, name=excluded.name""",
         (ticker, int(time.time()), composite, rating, news_score, name))


# ------------------------------------------------------------------ predictions
def log_prediction(p: dict) -> None:
    _run("""INSERT INTO sp_predictions (theme, horizon, made_at, day, label, score, prob_up, confidence, baseline_label, bench,
                                         entry_px, spy_entry, evaluate_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (theme, horizon, day) DO NOTHING""",
         (p["theme"], p["horizon"], p["made_at"], p["day"], p["label"], p["score"], p["prob_up"], p["confidence"],
          p["baseline_label"], p["bench"], p.get("entry_px"), p.get("spy_entry"), p["evaluate_at"]))


def due_predictions(now: int) -> list[dict]:
    return _run("SELECT * FROM sp_predictions WHERE outcome IS NULL AND evaluate_at <= ? ORDER BY id", (now,), many=True)


def save_outcome(pred_id: int, exit_px: Optional[float], spy_exit: Optional[float], excess: Optional[float], outcome: str,
                 hit: int, baseline_hit: int) -> None:
    _run("UPDATE sp_predictions SET exit_px=?, spy_exit=?, excess=?, outcome=?, hit=?, baseline_hit=? WHERE id=?",
         (exit_px, spy_exit, excess, outcome, hit, baseline_hit, pred_id))


def accuracy() -> dict:
    rows = _run("SELECT theme, horizon, label, outcome, hit, baseline_hit FROM sp_predictions WHERE outcome IS NOT NULL AND outcome <> 'n/a'", many=True)
    pending = _run("SELECT COUNT(*) AS n FROM sp_predictions WHERE outcome IS NULL", many=True)[0]["n"]

    def summarise(rs: list[dict]) -> dict:
        n = len(rs)
        directional = [r for r in rs if r["label"] in ("Up", "Down")]
        return {"n": n,
                "hitRate": round(100 * sum(r["hit"] for r in rs) / n, 1) if n else None,
                "baselineHitRate": round(100 * sum(r["baseline_hit"] for r in rs) / n, 1) if n else None,
                "directionalCalls": len(directional),
                "directionalHitRate": round(100 * sum(r["hit"] for r in directional) / len(directional), 1) if directional else None}

    by_h = {h: summarise([r for r in rows if r["horizon"] == h]) for h in ("1W", "1M", "3M")}
    by_t: dict[str, dict] = {}
    for t in sorted({r["theme"] for r in rows}):
        by_t[t] = summarise([r for r in rows if r["theme"] == t])
    return {"overall": summarise(rows), "byHorizon": by_h, "byTheme": by_t, "pending": pending}
