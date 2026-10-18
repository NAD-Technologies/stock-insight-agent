"""Event detection: turn headlines into market events (war, sanctions, rate decisions...).

Detection is keyword-based and deterministic (the LLM is optional and not needed here). What an event *means* for each
sector comes from the impact matrix in rules.yaml, which a human edits.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from urllib.parse import urlparse

import httpx

log = logging.getLogger("sector_pulse.events")
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _outlet(h: dict) -> str:
    return (h.get("source") or urlparse(h.get("url") or "").netloc or "unknown").lower()


def match_type(title: str, rules: dict) -> str | None:
    """Event type with the most keyword hits in the headline (first listed wins ties); None if nothing matches."""
    t = title.lower()
    best, best_hits = None, 0
    for name, cfg in rules["event_types"].items():
        hits = sum(1 for kw in cfg["keywords"] if kw in t)
        if hits > best_hits:
            best, best_hits = name, hits
    return best


def detect(headlines: list[dict], rules: dict, now: dt.datetime | None = None) -> list[dict]:
    """Group headlines by event type and rate severity by how many headlines/outlets report it."""
    now = now or dt.datetime.now(dt.timezone.utc)
    det = rules["event_detection"]
    groups: dict[str, list[dict]] = {}
    for h in headlines:
        if not h.get("title"):
            continue
        typ = match_type(h["title"], rules)
        if typ:
            groups.setdefault(typ, []).append(h)
    out = []
    ts = int(now.timestamp())
    for typ, hs in groups.items():
        uniq = list({h["title"].lower()[:90]: h for h in hs}.values())
        sources = {_outlet(h) for h in uniq}
        sev = ("High" if len(sources) >= det["high_sources"] and len(uniq) >= det["high_headlines"]
               else "Med" if len(uniq) >= det["med_headlines"] else "Low")
        out.append({"id": f"{typ}:{now.date().isoformat()}", "type": typ, "severity": sev, "first_seen": ts, "last_seen": ts,
                    "n_headlines": len(uniq), "n_sources": len(sources),
                    "headlines": [{"title": h["title"], "url": h.get("url"), "source": h.get("source")}
                                  for h in uniq[: det["max_headlines_kept"]]]})
    return out


def _gdelt_query(keywords: list[str]) -> str:
    terms = [f'"{k.strip()}"' if " " in k.strip() else k.strip() for k in keywords[:6]]
    return "(" + " OR ".join(terms) + ") sourcelang:english"


async def fetch_gdelt(rules: dict) -> list[dict]:
    """Free, keyless global news index. One query per event type, throttled as GDELT requests. Never raises."""
    cfg = rules["event_sources"]["gdelt"]
    if not cfg.get("enabled"):
        return []
    out: list[dict] = []
    deadline = time.monotonic() + cfg.get("max_seconds", 150)
    failures = 0  # consecutive event types that returned nothing usable
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "stock-insight-sector-pulse/1.0"}) as c:
        for typ, tcfg in rules["event_types"].items():
            if time.monotonic() > deadline or failures >= cfg.get("stop_after_failures", 3):
                log.warning("GDELT stage stopped early (%s)", "time cap" if time.monotonic() > deadline else "repeated failures")
                break
            got = False
            params = {"query": _gdelt_query(tcfg["keywords"]), "mode": "artlist", "format": "json",
                      "maxrecords": cfg["max_records"], "timespan": cfg["timespan"], "sort": "datedesc"}
            for attempt in (1, 2, 3):
                try:
                    r = await c.get(GDELT_URL, params=params)
                except Exception as e:  # noqa: BLE001
                    log.warning("GDELT %s failed: %s", typ, e)
                    break
                if r.status_code == 429 and attempt < 3:  # rate limited: back off, then retry
                    await asyncio.sleep(cfg["sleep_seconds"] * 2 * attempt)
                    continue
                if r.status_code == 200 and r.text.strip().startswith("{"):
                    got = True
                    for a in r.json().get("articles", []):
                        out.append({"title": a.get("title"), "url": a.get("url"), "source": a.get("domain"), "time": a.get("seendate")})
                else:
                    log.warning("GDELT %s -> HTTP %s", typ, r.status_code)
                break
            failures = 0 if got else failures + 1
            await asyncio.sleep(cfg["sleep_seconds"])
    return out
