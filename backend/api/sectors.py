"""Read-only Sector Pulse endpoints. All data comes from the snapshots the scheduled pipeline stored; nothing heavy runs here."""
import datetime as dt
import time

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_admin
from sector_pulse import overlay as OV
from sector_pulse import scoring as S
from sector_pulse import store

router = APIRouter(prefix="/api")
STALE_AFTER = 12 * 3600


def _summary(s: dict) -> dict:
    h = s["horizons"]
    return {"theme": s["theme"], "name": s["name"], "group": s["group"], "rank": s.get("rank"),
            "benchmark": s["benchmark"]["symbol"],
            "horizons": {k: {x: v[x] for x in ("score", "direction", "probUp", "confidence")} for k, v in h.items()},
            "ret1M": s["metrics"]["returns"].get("1M"), "excess1M": h["1M"].get("excess"),
            "driver": (s["drivers"]["positive"] or s["drivers"]["negative"] or [None])[0],
            "leaders": [p["ticker"] for p in s["picks"]["leaders"][:3]], "laggards": [p["ticker"] for p in s["picks"]["laggards"][:3]]}


def _active_events() -> list[dict]:
    rules = S.load_yaml("rules.yaml")
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for e in store.recent_events(30):
        active = S.active_event_weights([e], rules, now).get(e["type"])
        if not active or active < 0.05:
            continue
        matrix = rules["impact_matrix"].get(e["type"], {})
        ranked = sorted(matrix.items(), key=lambda kv: -abs(kv[1]))
        out.append({"type": e["type"], "label": e["type"].replace("_", " ").capitalize(), "severity": e["severity"],
                    "nSources": e["n_sources"], "lastSeen": e["last_seen"], "strength": round(active, 2),
                    "headline": (e["headlines"] or [None])[0],
                    "helps": [t for t, v in ranked if v > 0][:4], "hurts": [t for t, v in ranked if v < 0][:4]})
    out.sort(key=lambda x: -x["strength"])
    return out


@router.get("/sectors")
async def sectors():
    snaps = store.latest_snapshots()
    runs = store.last_runs(1)
    if not snaps:
        return {"ready": False, "themes": [], "events": [], "message": "Sector Pulse has not run yet. The scheduled pipeline populates it."}
    as_of = max(s["asOf"] for s in snaps)
    names = {s["theme"]: s["name"] for s in snaps}
    events = _active_events()
    for e in events:
        e["helps"] = [{"theme": t, "name": names.get(t, t)} for t in e["helps"]]
        e["hurts"] = [{"theme": t, "name": names.get(t, t)} for t in e["hurts"]]
    return {"ready": True, "asOf": as_of, "stale": time.time() - as_of > STALE_AFTER,
            "run": {k: runs[0][k] for k in ("status", "finished")} if runs else None,
            "themes": sorted((_summary(s) for s in snaps), key=lambda x: x["rank"] or 999), "events": events}


@router.get("/sectors/accuracy")
async def sectors_accuracy():
    return store.accuracy()


@router.get("/sectors/for/{ticker}")
async def sector_for_ticker(ticker: str, sector: str = "", rating: str = ""):
    return {"overlay": OV.overlay(ticker, sector or None, rating or None)}


@router.get("/sectors/{theme}")
async def sector_detail(theme: str):
    snap = store.latest_snapshot(theme)
    if not snap:
        raise HTTPException(404, f"No Sector Pulse data for '{theme}' yet")
    snap["history"] = store.score_history(theme, 90)
    snap["stale"] = time.time() - snap["asOf"] > STALE_AFTER
    return snap


@router.get("/admin/pipeline")
async def admin_pipeline(_: dict = Depends(require_admin)):
    return {"runs": store.last_runs(10), "accuracy": store.accuracy()}
