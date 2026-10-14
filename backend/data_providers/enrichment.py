"""Optional enrichment providers. Each returns [] / None when its API key is absent or a call fails."""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Optional

import httpx

from .cache import ttl_cache

log = logging.getLogger("enrichment")


def _key(name: str) -> Optional[str]:
    v = os.getenv(name, "").strip()
    return v or None


async def _get(url: str, params: dict) -> Optional[dict | list]:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:  # noqa: BLE001
        log.info("enrichment call failed (%s): %s", url.split("/")[2], type(e).__name__)
        return None


@ttl_cache(900)
async def finnhub_news(ticker: str, days: int = 14) -> list[dict]:
    k = _key("FINNHUB_API_KEY")
    if not k:
        return []
    today = dt.date.today()
    data = await _get("https://finnhub.io/api/v1/company-news",
                      {"symbol": ticker, "from": (today - dt.timedelta(days=days)).isoformat(), "to": today.isoformat(), "token": k})
    return [{"title": d["headline"], "source": d.get("source"), "summary": d.get("summary"), "url": d.get("url"),
             "time": dt.datetime.fromtimestamp(d["datetime"], dt.timezone.utc).isoformat()}
            for d in (data or []) if d.get("headline")][:25]


@ttl_cache(900)
async def alphavantage_news(ticker: str) -> list[dict]:
    """Returns articles with the vendor's own sentiment label so the LLM can cross-check."""
    k = _key("ALPHAVANTAGE_API_KEY")
    if not k:
        return []
    data = await _get("https://www.alphavantage.co/query", {"function": "NEWS_SENTIMENT", "tickers": ticker, "limit": 30, "apikey": k})
    out = []
    for a in (data or {}).get("feed", []) if isinstance(data, dict) else []:
        try:
            t = dt.datetime.strptime(a["time_published"], "%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc).isoformat()
        except (KeyError, ValueError):
            t = None
        out.append({"title": a.get("title"), "source": a.get("source"), "summary": a.get("summary"), "url": a.get("url"),
                    "time": t, "vendorSentiment": a.get("overall_sentiment_label")})
    return out


@ttl_cache(86400)
async def fred_10y() -> Optional[dict]:
    k = _key("FRED_API_KEY")
    if not k:
        return None
    data = await _get("https://api.stlouisfed.org/fred/series/observations",
                      {"series_id": "DGS10", "api_key": k, "file_type": "json", "sort_order": "desc", "limit": 80})
    obs = [float(o["value"]) for o in (data or {}).get("observations", []) if o.get("value") not in (".", None)] if isinstance(data, dict) else []
    if len(obs) < 10:
        return None
    return {"level": obs[0], "change3mBps": round((obs[0] - obs[-1]) * 100, 1), "source": "FRED"}


@ttl_cache(86400)
async def finnhub_surprises(ticker: str) -> list[dict]:
    k = _key("FINNHUB_API_KEY")
    if not k:
        return []
    data = await _get("https://finnhub.io/api/v1/stock/earnings", {"symbol": ticker, "token": k})
    return [{"date": d.get("period"), "estimate": d.get("estimate"), "actual": d.get("actual"), "surprisePct": d.get("surprisePercent")}
            for d in (data or [])[:8]] if isinstance(data, list) else []
