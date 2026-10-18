"""Sector overlay for a single stock (Module A item A9): which themes it belongs to and how they are doing."""
from __future__ import annotations

import functools
import logging
from typing import Optional

from . import scoring as S
from . import store

log = logging.getLogger("sector_pulse.overlay")


@functools.lru_cache(maxsize=1)
def _themes() -> dict:
    return S.load_yaml("themes.yaml")


def theme_ids_for(ticker: str, yahoo_sector: Optional[str]) -> list[str]:
    cfg = _themes()
    ticker = ticker.upper()
    ids = [t["id"] for t in cfg["themes"] if ticker in t["members"]]
    fallback = cfg["yahoo_sector_map"].get(yahoo_sector or "")
    if fallback and fallback not in ids:
        ids.append(fallback)
    by_id = {t["id"]: t for t in cfg["themes"]}
    ids.sort(key=lambda i: (by_id[i]["group"] != "gics", i))  # GICS sector first
    return ids[:3]


def _brief(snap: dict) -> dict:
    h = snap["horizons"]
    return {"theme": snap["theme"], "name": snap["name"], "group": snap["group"], "rank": snap.get("rank"),
            "asOf": snap.get("asOf"),
            "horizons": {k: {"score": v["score"], "direction": v["direction"], "confidence": v["confidence"]} for k, v in h.items()},
            "driver": (snap["drivers"]["positive"] or snap["drivers"]["negative"] or [None])[0]}


def overlay(ticker: str, yahoo_sector: Optional[str], rating: Optional[str]) -> Optional[dict]:
    """Never raises: the stock page must work even if the sector pipeline has not run or the database is down."""
    try:
        briefs = []
        for tid in theme_ids_for(ticker, yahoo_sector):
            snap = store.latest_snapshot(tid)
            if snap:
                briefs.append(_brief(snap))
        if not briefs:
            return None
        flag = None
        primary = briefs[0]
        d1m = primary["horizons"]["1M"]["direction"]
        score = primary["horizons"]["1M"]["score"]
        if rating in ("Buy", "Strong Buy") and d1m == "Down":
            flag = {"level": "warn", "text": f"Strong stock in a weak sector: {primary['name']} is rated Down over 1M (score {score}). "
                                             "Sector headwinds can outweigh stock-level strength."}
        elif rating in ("Sell", "Strong Sell") and d1m == "Up":
            flag = {"level": "info", "text": f"Weak stock in a strong sector: {primary['name']} is rated Up over 1M (score {score}), "
                                             "so the sector may be masking stock-level weakness."}
        return {"themes": briefs, "flag": flag}
    except Exception as e:  # noqa: BLE001
        log.warning("sector overlay unavailable: %s", e)
        return None
