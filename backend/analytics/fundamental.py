"""Fundamental metrics, Altman Z, Piotroski F, DCF and Graham fair value.

Input is a plain dict produced by data_providers.yahoo.fetch_fundamentals so that every
function here is pure and unit-testable. Missing inputs yield None, never guessed values.
"""
from __future__ import annotations

import math
from typing import Optional

# Approximate sector median multiples (static reference; documented in README).
SECTOR_MEDIANS = {
    "Technology": {"pe": 28, "forwardPe": 24, "pb": 7.0, "ps": 6.0, "evEbitda": 18, "evRevenue": 6.0, "peg": 1.9},
    "Healthcare": {"pe": 24, "forwardPe": 18, "pb": 4.0, "ps": 3.5, "evEbitda": 15, "evRevenue": 4.0, "peg": 2.0},
    "Financial Services": {"pe": 14, "forwardPe": 12, "pb": 1.5, "ps": 3.0, "evEbitda": 11, "evRevenue": 3.5, "peg": 1.4},
    "Consumer Cyclical": {"pe": 22, "forwardPe": 19, "pb": 4.0, "ps": 1.5, "evEbitda": 13, "evRevenue": 1.8, "peg": 1.8},
    "Consumer Defensive": {"pe": 21, "forwardPe": 19, "pb": 4.0, "ps": 1.3, "evEbitda": 13, "evRevenue": 1.6, "peg": 2.5},
    "Industrials": {"pe": 22, "forwardPe": 19, "pb": 4.0, "ps": 2.0, "evEbitda": 14, "evRevenue": 2.3, "peg": 2.0},
    "Energy": {"pe": 12, "forwardPe": 11, "pb": 1.8, "ps": 1.2, "evEbitda": 6, "evRevenue": 1.4, "peg": 1.2},
    "Utilities": {"pe": 18, "forwardPe": 16, "pb": 1.8, "ps": 2.2, "evEbitda": 11, "evRevenue": 3.0, "peg": 2.5},
    "Real Estate": {"pe": 35, "forwardPe": 30, "pb": 2.0, "ps": 6.0, "evEbitda": 17, "evRevenue": 8.0, "peg": 2.5},
    "Basic Materials": {"pe": 16, "forwardPe": 14, "pb": 2.2, "ps": 1.8, "evEbitda": 9, "evRevenue": 2.0, "peg": 1.6},
    "Communication Services": {"pe": 20, "forwardPe": 17, "pb": 3.0, "ps": 2.5, "evEbitda": 11, "evRevenue": 3.0, "peg": 1.6},
}
DEFAULT_MEDIAN = {"pe": 21, "forwardPe": 18, "pb": 3.5, "ps": 2.5, "evEbitda": 13, "evRevenue": 3.0, "peg": 1.8}


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def safe_div(a, b) -> Optional[float]:
    return a / b if _ok(a) and _ok(b) and b != 0 else None


def cagr(first, last, years) -> Optional[float]:
    if not (_ok(first) and _ok(last)) or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def yoy(cur, prev) -> Optional[float]:
    if not (_ok(cur) and _ok(prev)) or prev == 0:
        return None
    return (cur - prev) / abs(prev)


def altman_z(f: dict) -> Optional[float]:
    """Original Altman Z (manufacturing). Needs working capital, retained earnings, EBIT, mkt cap, sales, assets, liabilities."""
    ta = f.get("totalAssets")
    keys = ["workingCapital", "retainedEarnings", "ebit", "marketCap", "revenue", "totalLiabilities"]
    if not _ok(ta) or not ta or any(not _ok(f.get(k)) for k in keys) or not f["totalLiabilities"]:
        return None
    return round(1.2 * f["workingCapital"] / ta + 1.4 * f["retainedEarnings"] / ta + 3.3 * f["ebit"] / ta
                 + 0.6 * f["marketCap"] / f["totalLiabilities"] + 1.0 * f["revenue"] / ta, 2)


def piotroski(cur: dict, prev: dict) -> Optional[int]:
    """9-point F-score from two consecutive annual snapshots; None if too many inputs missing."""
    tests, missing = [], 0

    def add(cond):
        nonlocal missing
        if cond is None:
            missing += 1
        else:
            tests.append(1 if cond else 0)

    def gt(a, b):
        return (a > b) if _ok(a) and _ok(b) else None

    roa = lambda d: safe_div(d.get("netIncome"), d.get("totalAssets"))  # noqa: E731
    add(None if roa(cur) is None else roa(cur) > 0)
    add(None if not _ok(cur.get("operatingCashFlow")) else cur["operatingCashFlow"] > 0)
    add(gt(roa(cur), roa(prev)))
    add(None if not (_ok(cur.get("operatingCashFlow")) and _ok(cur.get("netIncome"))) else cur["operatingCashFlow"] > cur["netIncome"])
    lev = lambda d: safe_div(d.get("longTermDebt") or 0, d.get("totalAssets"))  # noqa: E731
    add(None if lev(cur) is None or lev(prev) is None else lev(cur) < lev(prev))
    cr = lambda d: safe_div(d.get("currentAssets"), d.get("currentLiabilities"))  # noqa: E731
    add(gt(cr(cur), cr(prev)))
    add(None if not (_ok(cur.get("shares")) and _ok(prev.get("shares"))) else cur["shares"] <= prev["shares"] * 1.005)
    gm = lambda d: safe_div(d.get("grossProfit"), d.get("revenue"))  # noqa: E731
    add(gt(gm(cur), gm(prev)))
    at = lambda d: safe_div(d.get("revenue"), d.get("totalAssets"))  # noqa: E731
    add(gt(at(cur), at(prev)))
    return sum(tests) if missing <= 2 else None


def dcf(fcf0: Optional[float], growth: float, wacc: float, terminal_g: float, shares: Optional[float],
        net_debt: float = 0.0, years: int = 5) -> Optional[float]:
    """Per-share DCF. growth fades linearly to terminal_g over `years`."""
    if not (_ok(fcf0) and _ok(shares)) or fcf0 <= 0 or not shares or wacc <= terminal_g:
        return None
    pv, cf = 0.0, fcf0
    for t in range(1, years + 1):
        g = growth + (terminal_g - growth) * (t - 1) / max(years - 1, 1)
        cf *= 1 + g
        pv += cf / (1 + wacc) ** t
    tv = cf * (1 + terminal_g) / (wacc - terminal_g)
    pv += tv / (1 + wacc) ** years
    return (pv - net_debt) / shares


def graham_number(eps: Optional[float], bvps: Optional[float]) -> Optional[float]:
    if _ok(eps) and _ok(bvps) and eps > 0 and bvps > 0:
        return math.sqrt(22.5 * eps * bvps)
    return None


def fair_value(f: dict, price: Optional[float], wacc=0.09, terminal_g=0.025) -> dict:
    g = f.get("fcfGrowthEstimate")
    g = min(max(g if _ok(g) else 0.05, -0.05), 0.20)
    net_debt = (f.get("totalDebt") or 0) - (f.get("cash") or 0)
    lo = dcf(f.get("fcf"), g * 0.6, wacc + 0.01, terminal_g, f.get("sharesOutstanding"), net_debt)
    base = dcf(f.get("fcf"), g, wacc, terminal_g, f.get("sharesOutstanding"), net_debt)
    hi = dcf(f.get("fcf"), min(g * 1.4, 0.25), wacc - 0.01, terminal_g, f.get("sharesOutstanding"), net_debt)
    gn = graham_number(f.get("eps"), f.get("bookValuePerShare"))
    vals = [v for v in (lo, base, hi) if v is not None]
    out = {"low": None, "base": None, "high": None, "dcf": base, "graham": gn, "marginOfSafety": None,
           "assumptions": {"wacc": wacc, "terminalGrowth": terminal_g, "fcfGrowth": g}}
    if vals:
        out.update(low=lo, base=base, high=hi)
    elif gn:
        out.update(low=gn * 0.85, base=gn, high=gn * 1.15)
    for k in ("low", "base", "high", "dcf", "graham"):
        if out[k] is not None:
            out[k] = round(out[k], 2)
    if out["base"] and price:
        out["marginOfSafety"] = round((out["base"] - price) / out["base"] * 100, 1)
    return out


def valuation_vs_sector(f: dict, sector: Optional[str]) -> dict:
    med = SECTOR_MEDIANS.get(sector or "", DEFAULT_MEDIAN)
    out = {}
    for k, m in med.items():
        v = f.get(k)
        out[k] = {"value": v if _ok(v) else None, "sectorMedian": m,
                  "premiumPct": round((v / m - 1) * 100, 1) if _ok(v) and v > 0 else None}
    return out


def build_metrics(f: dict, sector: Optional[str]) -> list[dict]:
    """Flat metric list with a good/bad/neutral signal vs fixed thresholds or sector medians."""
    med = SECTOR_MEDIANS.get(sector or "", DEFAULT_MEDIAN)
    rows: list[dict] = []

    def add(group, name, key, fmt="x", better="lower", median=None, good=None, bad=None):
        v = f.get(key)
        v = v if _ok(v) else None
        sig = "na"
        if v is not None:
            if median is not None and v > 0:
                r = v / median
                sig = ("good" if r < 0.85 else "bad" if r > 1.3 else "neutral") if better == "lower" else \
                      ("good" if r > 1.15 else "bad" if r < 0.75 else "neutral")
            elif median is not None and v <= 0:
                sig = "bad"
            elif good is not None and bad is not None:
                sig = ("good" if v >= good else "bad" if v <= bad else "neutral") if better == "higher" else \
                      ("good" if v <= good else "bad" if v >= bad else "neutral")
        rows.append({"group": group, "name": name, "key": key, "value": v, "format": fmt,
                     "sectorMedian": median, "signal": sig})

    add("Valuation", "P/E (TTM)", "pe", median=med["pe"])
    add("Valuation", "Forward P/E", "forwardPe", median=med["forwardPe"])
    add("Valuation", "PEG", "peg", median=med["peg"])
    add("Valuation", "P/B", "pb", median=med["pb"])
    add("Valuation", "P/S", "ps", median=med["ps"])
    add("Valuation", "EV/EBITDA", "evEbitda", median=med["evEbitda"])
    add("Valuation", "EV/Revenue", "evRevenue", median=med["evRevenue"])
    add("Valuation", "FCF yield", "fcfYield", "pct", "higher", good=0.04, bad=0.01)
    add("Growth", "Revenue growth YoY", "revenueGrowth", "pct", "higher", good=0.10, bad=0.0)
    add("Growth", "Revenue 3y CAGR", "revenueCagr3y", "pct", "higher", good=0.10, bad=0.0)
    add("Growth", "EPS growth YoY", "epsGrowth", "pct", "higher", good=0.10, bad=0.0)
    add("Growth", "EPS 3y CAGR", "epsCagr3y", "pct", "higher", good=0.10, bad=0.0)
    add("Growth", "Forward EPS growth", "forwardEpsGrowth", "pct", "higher", good=0.10, bad=0.0)
    add("Profitability", "Gross margin", "grossMargin", "pct", "higher", good=0.45, bad=0.2)
    add("Profitability", "Operating margin", "operatingMargin", "pct", "higher", good=0.20, bad=0.05)
    add("Profitability", "Net margin", "netMargin", "pct", "higher", good=0.15, bad=0.03)
    add("Profitability", "ROE", "roe", "pct", "higher", good=0.15, bad=0.05)
    add("Profitability", "ROA", "roa", "pct", "higher", good=0.07, bad=0.02)
    add("Profitability", "ROIC", "roic", "pct", "higher", good=0.12, bad=0.05)
    add("Health", "Debt/Equity", "debtToEquity", "x", "lower", good=0.8, bad=2.0)
    add("Health", "Net debt/EBITDA", "netDebtToEbitda", "x", "lower", good=1.5, bad=3.5)
    add("Health", "Current ratio", "currentRatio", "x", "higher", good=1.5, bad=1.0)
    add("Health", "Quick ratio", "quickRatio", "x", "higher", good=1.0, bad=0.7)
    add("Health", "Interest coverage", "interestCoverage", "x", "higher", good=6, bad=2)
    add("Health", "Altman Z", "altmanZ", "x", "higher", good=3.0, bad=1.8)
    add("Health", "Piotroski F", "piotroski", "int", "higher", good=7, bad=3)
    add("Shareholder", "Dividend yield", "dividendYield", "pct", "higher", good=0.025, bad=-1)
    add("Shareholder", "Payout ratio", "payoutRatio", "pct", "lower", good=0.6, bad=0.9)
    add("Shareholder", "Buyback yield", "buybackYield", "pct", "higher", good=0.01, bad=-1)
    return rows


def derive(raw: dict, price: Optional[float]) -> dict:
    """Compute derived ratios onto a copy of the raw dict."""
    f = dict(raw)
    a = f.get("annual") or []  # newest first: list of dicts
    if len(a) >= 2:
        f["revenueGrowth"] = f.get("revenueGrowth") if _ok(f.get("revenueGrowth")) else yoy(a[0].get("revenue"), a[1].get("revenue"))
        f["epsGrowth"] = yoy(a[0].get("eps"), a[1].get("eps"))
    if len(a) >= 4:
        f["revenueCagr3y"] = cagr(a[3].get("revenue"), a[0].get("revenue"), 3)
        f["epsCagr3y"] = cagr(a[3].get("eps"), a[0].get("eps"), 3)
    f["forwardEpsGrowth"] = yoy(f.get("forwardEps"), f.get("eps")) if _ok(f.get("forwardEps")) and _ok(f.get("eps")) and f["eps"] > 0 else None
    mc = f.get("marketCap")
    f["fcfYield"] = safe_div(f.get("fcf"), mc)
    f["netDebtToEbitda"] = safe_div((f.get("totalDebt") or 0) - (f.get("cash") or 0), f.get("ebitda")) if _ok(f.get("ebitda")) else None
    f["buybackYield"] = safe_div(f.get("buybacks"), mc)
    f["altmanZ"] = altman_z(f)
    if len(a) >= 2:
        f["piotroski"] = piotroski(a[0], a[1])
    # FCF growth proxy for the DCF: mean of available revenue CAGR / YoY growth / forward EPS growth (clamped in fair_value)
    gs = [f[k] for k in ("revenueCagr3y", "revenueGrowth", "forwardEpsGrowth") if _ok(f.get(k))]
    f["fcfGrowthEstimate"] = sum(gs) / len(gs) if gs else None
    if _ok(f.get("forwardEpsGrowth")) and f["forwardEpsGrowth"] > 0 and f.get("pe"):
        f["peg"] = f["peg"] if _ok(f.get("peg")) else f["pe"] / (f["forwardEpsGrowth"] * 100)
    return f
