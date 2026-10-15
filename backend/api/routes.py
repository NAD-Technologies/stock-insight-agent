import asyncio
import re

from fastapi import APIRouter, Header, HTTPException, Query

from agent import orchestrator as O
from api import db
from api.auth import get_user
from data_providers import yahoo as Y

router = APIRouter(prefix="/api")
TICKER_RE = re.compile(r"^[A-Za-z0-9^][A-Za-z0-9.\-=^]{0,14}$")  # AAPL, BRK-B, RELIANCE.NS, 7203.T


def _check(t: str) -> str:
    if not TICKER_RE.match(t.strip()):
        raise HTTPException(400, f"Invalid ticker symbol: {t!r}")
    return t.strip().upper()


@router.get("/health")
async def health():
    from agent import llm
    return {"ok": True, "llm": llm.available()}


@router.get("/analyze/{ticker}")
async def analyze(ticker: str, profile: str = Query("balanced", pattern="^(balanced|trader|investor)$"), authorization: str = Header("")):
    t = _check(ticker)
    try:
        result = await O.analyze(t, profile)
        user = get_user(authorization)
        if user:  # personalised activity: count successful lookups for signed-in users
            try:
                db.record_view(user["id"], t)
            except Exception:  # noqa: BLE001  (never fail an analysis because of tracking)
                pass
        return result
    except Y.TickerNotFound:
        raise HTTPException(404, f"No market data found for {t}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Upstream data provider error ({type(e).__name__}); try again shortly")


@router.get("/search")
async def search(q: str = Query(..., min_length=1, max_length=40)):
    try:
        return {"results": await Y.search(q)}
    except Exception:  # noqa: BLE001
        return {"results": []}


@router.get("/compare")
async def compare(tickers: str, profile: str = Query("balanced", pattern="^(balanced|trader|investor)$")):
    syms = list(dict.fromkeys(_check(t) for t in tickers.split(",") if t.strip()))[:4]
    if len(syms) < 2:
        raise HTTPException(400, "Provide 2-4 comma-separated tickers")
    res = await asyncio.gather(*(O.analyze(s, profile, use_llm=False) for s in syms), return_exceptions=True)
    return {"results": [O.condensed(r) if not isinstance(r, Exception) else {"ticker": s, "error": "unavailable"} for s, r in zip(syms, res)]}
