"""Risk statistics and relative strength."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def risk_stats(close: pd.Series, rf: float = 0.04) -> dict:
    c = close.dropna().tail(TRADING_DAYS + 1)
    if len(c) < 60:
        return {}
    r = c.pct_change().dropna()
    vol = float(r.std() * np.sqrt(TRADING_DAYS))
    ann_ret = float((c.iloc[-1] / c.iloc[0]) ** (TRADING_DAYS / len(r)) - 1)
    downside = r[r < 0].std() * np.sqrt(TRADING_DAYS)
    dd = (c / c.cummax() - 1).min()
    return {
        "volatility": round(vol * 100, 2),
        "maxDrawdown": round(float(dd) * 100, 2),
        "sharpe": round((ann_ret - rf) / vol, 2) if vol else None,
        "sortino": round((ann_ret - rf) / float(downside), 2) if downside and not np.isnan(downside) else None,
        "return1y": round(ann_ret * 100, 2),
    }


def relative_strength(stock: pd.Series, bench: pd.Series | None) -> dict:
    """Excess return (pct points) vs benchmark over 1M/3M/6M/1Y."""
    out = {}
    if bench is None or len(bench) < 30:
        return out
    for label, n in (("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252)):
        if len(stock) > n and len(bench) > n:
            s = stock.iloc[-1] / stock.iloc[-n - 1] - 1
            b = bench.iloc[-1] / bench.iloc[-n - 1] - 1
            out[label] = {"stock": round(s * 100, 2), "benchmark": round(b * 100, 2), "excess": round((s - b) * 100, 2)}
    return out


def vix_regime(vix: float | None) -> str | None:
    if vix is None:
        return None
    return "calm" if vix < 15 else "normal" if vix < 22 else "elevated" if vix < 30 else "stressed"
