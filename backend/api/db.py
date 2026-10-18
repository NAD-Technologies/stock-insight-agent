"""Small data store for users, per-user ticker views and feedback.

Two backends, chosen by environment:
  * DATABASE_URL set (postgresql://...)  -> Postgres (e.g. free Neon / Supabase); data survives redeploys.
  * otherwise                           -> a local SQLite file (DATA_DIR/app.db, default backend/data/app.db).
    On hosts with an ephemeral disk (Render free tier) that file is wiped on every redeploy/restart.
"""
import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from decimal import Decimal
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):  # some providers still hand out the legacy scheme
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
PG = DATABASE_URL.startswith("postgresql://")

DB_PATH = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parent.parent / "data") / "app.db"
_init_lock = threading.Lock()
_ready = False
_pool = None

_TABLES = [
    "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT, name TEXT, picture TEXT, "
    "first_seen BIGINT, last_seen BIGINT, login_count INTEGER DEFAULT 0, prefs TEXT)",
    "CREATE TABLE IF NOT EXISTS ticker_views (user_id TEXT, ticker TEXT, count INTEGER DEFAULT 0, "
    "last_viewed BIGINT, PRIMARY KEY (user_id, ticker))",
    "CREATE TABLE IF NOT EXISTS activity (user_id TEXT, day TEXT, PRIMARY KEY (user_id, day))",
    "CREATE TABLE IF NOT EXISTS feedback (id {pk}, user_id TEXT, name TEXT, email TEXT, "
    "rating INTEGER, message TEXT, created_at BIGINT)",
    # ---- Sector Pulse (written by the scheduled pipeline, read by the API)
    "CREATE TABLE IF NOT EXISTS sp_runs (id {pk}, started BIGINT, finished BIGINT, status TEXT, stats TEXT)",
    "CREATE TABLE IF NOT EXISTS sp_snapshots (id {pk}, run_id BIGINT, theme TEXT, as_of BIGINT, payload TEXT)",
    "CREATE INDEX IF NOT EXISTS sp_snapshots_theme_asof ON sp_snapshots (theme, as_of)",
    "CREATE TABLE IF NOT EXISTS sp_events (id TEXT PRIMARY KEY, type TEXT, severity TEXT, first_seen BIGINT, "
    "last_seen BIGINT, n_headlines INTEGER, n_sources INTEGER, headlines TEXT)",
    "CREATE TABLE IF NOT EXISTS sp_news (hash TEXT PRIMARY KEY, title TEXT, url TEXT, source TEXT, published TEXT, "
    "sentiment TEXT, impact TEXT, catalyst TEXT, reason TEXT, method TEXT, ticker TEXT, fetched BIGINT)",
    "CREATE TABLE IF NOT EXISTS sp_stock_scores (ticker TEXT PRIMARY KEY, as_of BIGINT, composite DOUBLE PRECISION, "
    "rating TEXT, news_score DOUBLE PRECISION, name TEXT)",
    "CREATE TABLE IF NOT EXISTS sp_predictions (id {pk}, theme TEXT, horizon TEXT, made_at BIGINT, day TEXT, label TEXT, "
    "score DOUBLE PRECISION, prob_up DOUBLE PRECISION, confidence TEXT, baseline_label TEXT, bench TEXT, "
    "entry_px DOUBLE PRECISION, spy_entry DOUBLE PRECISION, evaluate_at BIGINT, exit_px DOUBLE PRECISION, "
    "spy_exit DOUBLE PRECISION, excess DOUBLE PRECISION, outcome TEXT, hit INTEGER, baseline_hit INTEGER, "
    "UNIQUE (theme, horizon, day))",
]


def _init() -> None:
    """Create tables once per process (and add columns introduced after the first release)."""
    global _ready, _pool
    with _init_lock:
        if _ready:
            return
        if PG:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            # prepare_threshold=None keeps this compatible with pgbouncer / Supabase pooler connections
            # Serverless Postgres (Neon) closes idle connections, so validate on checkout (`check`), recycle idle ones
            # before the server drops them (`max_idle`), and keep no permanent connections (`min_size=0`).
            _pool = ConnectionPool(DATABASE_URL, min_size=0, max_size=4, open=True, timeout=20,
                                   check=ConnectionPool.check_connection, max_idle=45, max_lifetime=600,
                                   kwargs={"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 15})
            with _pool.connection() as c:
                for t in _TABLES:
                    c.execute(t.format(pk="BIGSERIAL PRIMARY KEY"))
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS prefs TEXT")
        else:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(DB_PATH)) as c:
                for t in _TABLES:
                    c.execute(t.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT"))
                try:  # DBs created before prefs existed
                    c.execute("ALTER TABLE users ADD COLUMN prefs TEXT")
                except sqlite3.OperationalError:
                    pass
                c.commit()
        _ready = True


def _norm(row: dict) -> dict:
    """Postgres returns Decimal for SUM/AVG; make rows JSON-friendly."""
    return {k: (int(v) if v == v.to_integral_value() else float(v)) if isinstance(v, Decimal) else v for k, v in row.items()}


def _run(sql: str, args: tuple = (), many: bool = False):
    """Run one statement. SQL is written with ? placeholders (translated for Postgres)."""
    _init()
    if PG:
        import psycopg
        for attempt in (1, 2):
            try:
                with _pool.connection() as c:  # commits on clean exit
                    cur = c.execute(sql.replace("?", "%s"), args)
                    return [_norm(r) for r in cur.fetchall()] if many else None
            except psycopg.OperationalError:  # connection dropped under us (idle timeout, restart): retry on a fresh one
                if attempt == 2:
                    raise
                time.sleep(0.3)
    with closing(sqlite3.connect(DB_PATH, timeout=10)) as c:
        c.row_factory = sqlite3.Row
        cur = c.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()] if many else None
        c.commit()
        return rows


def upsert_user(u: dict) -> None:
    now = int(time.time())
    _run("""INSERT INTO users (id, email, name, picture, first_seen, last_seen, login_count) VALUES (?,?,?,?,?,?,1)
            ON CONFLICT(id) DO UPDATE SET email=excluded.email, name=excluded.name, picture=excluded.picture,
            last_seen=excluded.last_seen, login_count=users.login_count+1""",
         (u["id"], u.get("email"), u.get("name"), u.get("picture"), now, now))
    _mark_active(u["id"])


def _day(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts if ts is not None else time.time()))


def _mark_active(uid: str) -> None:
    _run("INSERT INTO activity (user_id, day) VALUES (?,?) ON CONFLICT DO NOTHING", (uid, _day()))


def touch_user(uid: str) -> None:
    _run("UPDATE users SET last_seen=? WHERE id=?", (int(time.time()), uid))
    _mark_active(uid)


def get_prefs(uid: str) -> dict | None:
    rows = _run("SELECT prefs FROM users WHERE id=?", (uid,), many=True)
    try:
        return json.loads(rows[0]["prefs"]) if rows and rows[0]["prefs"] else None
    except ValueError:
        return None


def set_prefs(uid: str, prefs: dict) -> None:
    _run("UPDATE users SET prefs=? WHERE id=?", (json.dumps(prefs, separators=(",", ":")), uid))


def record_view(uid: str, ticker: str) -> None:
    now = int(time.time())
    _run("""INSERT INTO ticker_views (user_id, ticker, count, last_viewed) VALUES (?,?,1,?)
            ON CONFLICT(user_id, ticker) DO UPDATE SET count=ticker_views.count+1, last_viewed=excluded.last_viewed""",
         (uid, ticker, now))
    _mark_active(uid)


def user_activity(uid: str) -> dict:
    rows = _run("SELECT ticker, count, last_viewed FROM ticker_views WHERE user_id=? ORDER BY count DESC, last_viewed DESC",
                (uid,), many=True)
    return {"distinctTickers": len(rows), "totalViews": sum(r["count"] for r in rows),
            "regionSplit": region_split(rows), "tickers": rows, "recent": sorted(rows, key=lambda r: -r["last_viewed"])[:8]}


def list_users() -> list[dict]:
    users = _run("SELECT * FROM users ORDER BY last_seen DESC", many=True)
    views = _run("SELECT user_id, ticker, count FROM ticker_views ORDER BY count DESC", many=True)
    by: dict[str, list[dict]] = {}
    for v in views:
        by.setdefault(v["user_id"], []).append(v)
    for u in users:
        vs = by.get(u["id"], [])
        u["distinctTickers"] = len(vs)
        u["totalViews"] = sum(v["count"] for v in vs)
        u["topTickers"] = [v["ticker"] for v in vs[:5]]
    return users


def add_feedback(user: dict | None, name: str, email: str, rating: int | None, message: str) -> None:
    _run("INSERT INTO feedback (user_id, name, email, rating, message, created_at) VALUES (?,?,?,?,?,?)",
         (user["id"] if user else None, name, email, rating, message, int(time.time())))


def list_feedback() -> list[dict]:
    return _run("SELECT * FROM feedback ORDER BY created_at DESC LIMIT 500", many=True)


def region(ticker: str) -> str:
    return "India" if ticker.upper().endswith((".NS", ".BO")) else "Global"


def region_split(rows: list[dict]) -> dict:
    out = {"India": 0, "Global": 0}
    for r in rows:
        out[region(r["ticker"])] += r["count"]
    return out


def metrics(days: int = 14) -> dict:
    """Admin-facing growth/engagement numbers."""
    now = time.time()
    labels = [_day(now - 86400 * i) for i in range(days - 1, -1, -1)]
    first = _run("SELECT first_seen FROM users", many=True)
    signups = {d: 0 for d in labels}
    for r in first:
        d = _day(r["first_seen"])
        if d in signups:
            signups[d] += 1
    act = {d: 0 for d in labels}
    for r in _run("SELECT day, COUNT(*) AS n FROM activity GROUP BY day", many=True):
        if r["day"] in act:
            act[r["day"]] = r["n"]
    users = _run("SELECT id, name, email, login_count FROM users", many=True)
    views = _run("SELECT user_id, ticker, count FROM ticker_views", many=True)
    per_user: dict[str, int] = {}
    for v in views:
        per_user[v["user_id"]] = per_user.get(v["user_id"], 0) + v["count"]
    n = len(users)
    week = now - 7 * 86400
    ratings = {str(i): 0 for i in range(1, 6)}
    for r in _run("SELECT rating, COUNT(*) AS n FROM feedback WHERE rating IS NOT NULL GROUP BY rating", many=True):
        ratings[str(r["rating"])] = r["n"]
    return {
        "days": labels,
        "signupsByDay": [signups[d] for d in labels],
        "activeByDay": [act[d] for d in labels],
        "newUsers7d": sum(1 for r in first if r["first_seen"] >= week),
        "returningUsers": sum(1 for u in users if (u["login_count"] or 0) > 1),
        "returningRate": round(100 * sum(1 for u in users if (u["login_count"] or 0) > 1) / n, 1) if n else None,
        "avgTickersPerUser": round(len({(v["user_id"], v["ticker"]) for v in views}) / n, 1) if n else None,
        "avgLookupsPerUser": round(sum(per_user.values()) / n, 1) if n else None,
        "regionSplit": region_split(views),
        "topUsers": sorted(({"name": u["name"], "email": u["email"], "lookups": per_user.get(u["id"], 0)} for u in users),
                           key=lambda x: -x["lookups"])[:5],
        "ratingDist": ratings,
    }


def stats() -> dict:
    day = int(time.time()) - 86400
    one = lambda q, a=(): _run(q, a, many=True)[0]["n"]  # noqa: E731
    avg = _run("SELECT AVG(rating) AS a FROM feedback WHERE rating IS NOT NULL", many=True)[0]["a"]
    top = _run("SELECT ticker, SUM(count) AS views FROM ticker_views GROUP BY ticker ORDER BY views DESC LIMIT 8", many=True)
    return {"users": one("SELECT COUNT(*) AS n FROM users"),
            "activeToday": one("SELECT COUNT(*) AS n FROM users WHERE last_seen>=?", (day,)),
            "totalViews": one("SELECT COALESCE(SUM(count),0) AS n FROM ticker_views"),
            "feedback": one("SELECT COUNT(*) AS n FROM feedback"),
            "avgRating": round(avg, 2) if avg is not None else None, "topTickers": top}
