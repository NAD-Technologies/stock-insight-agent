"""yfinance-backed fetchers. Every fetcher returns plain dicts/DataFrames and never raises for a
*missing optional* dataset - it returns empty values so downstream scoring can mark N/A.
Only an unknown ticker (no price data at all) raises TickerNotFound."""
from __future__ import annotations

import datetime as dt
import logging
import math
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from .cache import ttl_cache, with_backoff

log = logging.getLogger("yahoo")

SECTOR_ETF = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV", "Energy": "XLE",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP", "Industrials": "XLI", "Utilities": "XLU",
    "Real Estate": "XLRE", "Basic Materials": "XLB", "Communication Services": "XLC",
}


class TickerNotFound(Exception):
    pass


def _num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _tk(ticker: str) -> yf.Ticker:
    return yf.Ticker(ticker)


def _safe(fn, default=None):
    try:
        v = fn()
        return default if v is None else v
    except Exception as e:  # noqa: BLE001
        log.debug("optional dataset failed: %s", e)
        return default


# ------------------------------------------------------------------ quote
@ttl_cache(60)
async def get_quote(ticker: str) -> dict:
    def work():
        t = _tk(ticker)
        info = _safe(lambda: t.info, {}) or {}
        fi = _safe(lambda: dict(t.fast_info), {}) or {}
        price = _num(info.get("currentPrice") or info.get("regularMarketPrice") or fi.get("lastPrice"))
        if price is None:
            h = t.history(period="5d")
            if h.empty:
                raise TickerNotFound(ticker)
            price = float(h["Close"].iloc[-1])
        prev = _num(info.get("regularMarketPreviousClose") or info.get("previousClose") or fi.get("previousClose"))
        change = price - prev if prev else None
        vol, avg = _num(info.get("regularMarketVolume") or info.get("volume")), _num(info.get("averageVolume") or info.get("averageDailyVolume3Month"))
        return {
            "ticker": ticker.upper(),
            "name": info.get("longName") or info.get("shortName") or ticker.upper(),
            "currency": info.get("currency"), "exchange": info.get("fullExchangeName") or info.get("exchange"),
            "price": price, "previousClose": prev, "change": change,
            "changePct": (change / prev * 100) if change is not None and prev else None,
            "volume": vol, "avgVolume": avg, "volumeVsAvg": (vol / avg) if vol and avg else None,
            "marketCap": _num(info.get("marketCap")),
            "fiftyTwoWeekHigh": _num(info.get("fiftyTwoWeekHigh")), "fiftyTwoWeekLow": _num(info.get("fiftyTwoWeekLow")),
            "dayHigh": _num(info.get("dayHigh")), "dayLow": _num(info.get("dayLow")), "open": _num(info.get("open")),
            "preMarketPrice": _num(info.get("preMarketPrice")), "postMarketPrice": _num(info.get("postMarketPrice")),
            "marketState": info.get("marketState"),
            "beta": _num(info.get("beta")), "pe": _num(info.get("trailingPE")), "forwardPe": _num(info.get("forwardPE")),
            "dividendYield": (_num(info.get("dividendRate")) / price) if _num(info.get("dividendRate")) and price else None,
            "sector": info.get("sector"), "industry": info.get("industry"),
            "summary": info.get("longBusinessSummary"), "website": info.get("website"),
            "country": info.get("country"),
        }
    return await with_backoff(work)


# ---------------------------------------------------------------- history
def _clean(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


@ttl_cache(300)
async def get_price_history(ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    return _clean(await with_backoff(lambda: _tk(ticker).history(period=period, interval=interval, auto_adjust=False)))


# ----------------------------------------------------------- fundamentals
def _row(df: pd.DataFrame, names: list[str], col) -> Optional[float]:
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return _num(df.loc[n, col])
    return None


def _periods(income, balance, cash, n) -> list[dict]:
    out = []
    if income is None or income.empty:
        return out
    for col in list(income.columns)[:n]:
        bcol = col if balance is not None and col in balance.columns else None
        ccol = col if cash is not None and col in cash.columns else None
        rev = _row(income, ["Total Revenue", "Operating Revenue"], col)
        gp = _row(income, ["Gross Profit"], col)
        out.append({
            "period": str(col)[:10], "revenue": rev, "grossProfit": gp,
            "operatingIncome": _row(income, ["Operating Income"], col), "netIncome": _row(income, ["Net Income", "Net Income Common Stockholders"], col),
            "eps": _row(income, ["Diluted EPS", "Basic EPS"], col), "ebit": _row(income, ["EBIT", "Operating Income"], col),
            "interestExpense": _row(income, ["Interest Expense"], col),
            "grossMargin": (gp / rev) if gp is not None and rev else None,
            "operatingMargin": (_row(income, ["Operating Income"], col) / rev) if rev and _row(income, ["Operating Income"], col) is not None else None,
            "netMargin": (_row(income, ["Net Income"], col) / rev) if rev and _row(income, ["Net Income"], col) is not None else None,
            "totalAssets": _row(balance, ["Total Assets"], bcol) if bcol is not None else None,
            "currentAssets": _row(balance, ["Current Assets"], bcol) if bcol is not None else None,
            "currentLiabilities": _row(balance, ["Current Liabilities"], bcol) if bcol is not None else None,
            "longTermDebt": _row(balance, ["Long Term Debt"], bcol) if bcol is not None else None,
            "shares": _row(balance, ["Ordinary Shares Number", "Share Issued"], bcol) if bcol is not None else None,
            "operatingCashFlow": _row(cash, ["Operating Cash Flow"], ccol) if ccol is not None else None,
            "fcf": _row(cash, ["Free Cash Flow"], ccol) if ccol is not None else None,
        })
    return out


@ttl_cache(86400)
async def get_fundamentals(ticker: str) -> dict:
    def work():
        t = _tk(ticker)
        info = _safe(lambda: t.info, {}) or {}
        inc_a, bal_a, cf_a = (_safe(lambda: getattr(t, a)) for a in ("income_stmt", "balance_sheet", "cashflow"))
        inc_q, bal_q, cf_q = (_safe(lambda: getattr(t, a)) for a in ("quarterly_income_stmt", "quarterly_balance_sheet", "quarterly_cashflow"))
        annual, quarterly = _periods(inc_a, bal_a, cf_a, 5), _periods(inc_q, bal_q, cf_q, 5)
        latest = annual[0] if annual else {}
        c0 = inc_a.columns[0] if inc_a is not None and not inc_a.empty else None
        b0 = bal_a.columns[0] if bal_a is not None and not bal_a.empty else None
        ebit, intexp = latest.get("ebit"), latest.get("interestExpense")
        debt = _num(info.get("totalDebt")) or (_row(bal_a, ["Total Debt"], b0) if b0 is not None else None)
        equity = _row(bal_a, ["Stockholders Equity", "Total Equity Gross Minority Interest"], b0) if b0 is not None else None
        de = _num(info.get("debtToEquity"))
        rep = _row(cf_a, ["Repurchase Of Capital Stock"], cf_a.columns[0]) if cf_a is not None and not cf_a.empty else None
        price = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
        return {
            "pe": _num(info.get("trailingPE")), "forwardPe": _num(info.get("forwardPE")), "peg": _num(info.get("trailingPegRatio") or info.get("pegRatio")),
            "pb": _num(info.get("priceToBook")), "ps": _num(info.get("priceToSalesTrailing12Months")),
            "evEbitda": _num(info.get("enterpriseToEbitda")), "evRevenue": _num(info.get("enterpriseToRevenue")),
            "grossMargin": _num(info.get("grossMargins")), "operatingMargin": _num(info.get("operatingMargins")), "netMargin": _num(info.get("profitMargins")),
            "roe": _num(info.get("returnOnEquity")), "roa": _num(info.get("returnOnAssets")),
            "roic": (ebit * 0.79 / (debt + equity)) if ebit and debt is not None and equity and (debt + equity) else None,
            "revenueGrowth": _num(info.get("revenueGrowth")),
            "debtToEquity": de / 100 if de is not None else None,
            "currentRatio": _num(info.get("currentRatio")), "quickRatio": _num(info.get("quickRatio")),
            "interestCoverage": (ebit / abs(intexp)) if ebit and intexp else None,
            "fcf": _num(info.get("freeCashflow")) or latest.get("fcf"),
            "eps": _num(info.get("trailingEps")), "forwardEps": _num(info.get("forwardEps")),
            "bookValuePerShare": _num(info.get("bookValue")), "sharesOutstanding": _num(info.get("sharesOutstanding")),
            "totalDebt": debt, "cash": _num(info.get("totalCash")), "ebitda": _num(info.get("ebitda")), "marketCap": _num(info.get("marketCap")),
            "revenue": _num(info.get("totalRevenue")) or latest.get("revenue"), "ebit": ebit, "netIncome": latest.get("netIncome"),
            "totalAssets": latest.get("totalAssets"),
            "totalLiabilities": _row(bal_a, ["Total Liabilities Net Minority Interest"], b0) if b0 is not None else None,
            "workingCapital": _row(bal_a, ["Working Capital"], b0) if b0 is not None else None,
            "retainedEarnings": _row(bal_a, ["Retained Earnings"], b0) if b0 is not None else None,
            "dividendYield": (_num(info.get("dividendRate")) / price) if _num(info.get("dividendRate")) and price else None,
            "payoutRatio": _num(info.get("payoutRatio")), "buybacks": abs(rep) if rep else None,
            "annual": annual, "quarterly": quarterly,
        }
    return await with_backoff(work)


# --------------------------------------------------------------- analysts
def post_earnings_moves(hist: pd.DataFrame, dates: list[pd.Timestamp]) -> list[float]:
    moves = []
    for d in dates:
        d = pd.Timestamp(d).tz_localize(None).normalize() if pd.Timestamp(d).tzinfo else pd.Timestamp(d).normalize()
        after = hist[hist.index > d - pd.Timedelta(days=0)]
        before = hist[hist.index <= d]
        if len(before) and len(after) >= 2:
            # reaction = close of first session after (or on) report vs prior close, approximated on daily bars
            base = float(before["close"].iloc[-1])
            nxt = float(after["close"].iloc[1 if after.index[0] <= d else 0])
            moves.append((nxt / base - 1) * 100)
    return moves


@ttl_cache(900)
async def get_analyst_view(ticker: str, price: Optional[float] = None, hist: Optional[pd.DataFrame] = None) -> dict:
    def work():
        t = _tk(ticker)
        rec = _safe(lambda: t.recommendations)
        dist = {}
        mean = None
        if rec is not None and not rec.empty:
            r = rec.iloc[0]
            dist = {k: int(r.get(k, 0) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
            n = sum(dist.values())
            if n:
                mean = (dist["strongBuy"] * 1 + dist["buy"] * 2 + dist["hold"] * 3 + dist["sell"] * 4 + dist["strongSell"] * 5) / n
        pt = _safe(lambda: t.analyst_price_targets, {}) or {}
        info = _safe(lambda: t.info, {}) or {}
        targets = {k: _num(pt.get(k)) for k in ("current", "low", "high", "mean", "median")}
        if targets["mean"] is None:
            targets.update(mean=_num(info.get("targetMeanPrice")), high=_num(info.get("targetHighPrice")),
                           low=_num(info.get("targetLowPrice")), median=_num(info.get("targetMedianPrice")))
        px = price or targets.get("current") or _num(info.get("currentPrice"))
        upside = (targets["mean"] / px - 1) * 100 if targets["mean"] and px else None
        if mean is None:
            mean = _num(info.get("recommendationMean"))

        ud, net = [], None
        df = _safe(lambda: t.upgrades_downgrades)
        if df is not None and not df.empty:
            df = df.copy()
            df.index = pd.to_datetime(df.index).tz_localize(None) if df.index.tz is not None else pd.to_datetime(df.index)
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
            rcent = df[df.index >= cutoff]
            for idx, row in rcent.head(30).iterrows():
                ud.append({"date": idx.strftime("%Y-%m-%d"), "firm": row.get("Firm"), "from": row.get("FromGrade"),
                           "to": row.get("ToGrade"), "action": row.get("Action")})
            act = rcent["Action"].astype(str).str.lower()
            net = int((act == "up").sum() - (act == "down").sum())

        rev_net = None
        er = _safe(lambda: t.eps_revisions)
        if er is not None and not er.empty:
            rows = er.iloc[:2]
            up = rows.get("upLast30days", pd.Series(dtype=float)).fillna(0).sum()
            dn = rows.get("downLast30days", pd.Series(dtype=float)).fillna(0).sum()
            rev_net = int(up - dn)

        surprises, dates = [], []
        ed = _safe(lambda: t.get_earnings_dates(limit=12))
        if ed is not None and not ed.empty:
            done = ed[ed["Reported EPS"].notna()].head(8)
            for idx, row in done.iterrows():
                surprises.append({"date": idx.strftime("%Y-%m-%d"), "estimate": _num(row.get("EPS Estimate")),
                                  "actual": _num(row.get("Reported EPS")), "surprisePct": _num(row.get("Surprise(%)"))})
                dates.append(idx)
        valid = [s for s in surprises if s["surprisePct"] is not None]
        beat = (sum(1 for s in valid if s["surprisePct"] > 0) / len(valid)) if valid else None
        avg_s = (sum(s["surprisePct"] for s in valid) / len(valid)) if valid else None
        moves = post_earnings_moves(hist, dates) if hist is not None and len(hist) and dates else []
        return {
            "consensusMean": mean, "distribution": dist, "numAnalysts": sum(dist.values()) or _num(info.get("numberOfAnalystOpinions")),
            "targets": targets, "upsidePct": upside, "upgradesDowngrades": ud, "netUpgrades90d": net,
            "revisionNet": rev_net, "surprises": surprises, "beatRate": beat, "avgSurprisePct": avg_s,
            "avgPostEarningsMove": (sum(moves) / len(moves)) if moves else None, "postEarningsMoves": [round(m, 2) for m in moves],
        }
    return await with_backoff(work)


# -------------------------------------------------------------- ownership
@ttl_cache(900)
async def get_ownership_and_flow(ticker: str, hv_series: Optional[pd.Series] = None) -> dict:
    def work():
        t = _tk(ticker)
        info = _safe(lambda: t.info, {}) or {}
        ins = {"buys": 0, "sells": 0, "netShares": None, "netValue": None, "transactions": [], "institutionPct": _num(info.get("heldPercentInstitutions"))}
        if ins["institutionPct"] is not None:
            ins["institutionPct"] *= 100
        df = _safe(lambda: t.insider_transactions)
        if df is not None and not df.empty and "Start Date" in df.columns:
            d = df.copy()
            d["Start Date"] = pd.to_datetime(d["Start Date"], errors="coerce")
            d = d[d["Start Date"] >= pd.Timestamp.now() - pd.Timedelta(days=183)]
            text = d.get("Text", pd.Series("", index=d.index)).astype(str).str.lower()
            buy = d[text.str.contains("purchase")]
            sell = d[text.str.contains("sale")]
            bs, ss = buy["Shares"].fillna(0).sum(), sell["Shares"].fillna(0).sum()
            bv = buy["Value"].fillna(0).sum() if "Value" in d else 0
            sv = sell["Value"].fillna(0).sum() if "Value" in d else 0
            ins.update(buys=len(buy), sells=len(sell), netShares=float(bs - ss), netValue=float(bv - sv))
            for _, r in pd.concat([buy, sell]).sort_values("Start Date", ascending=False).head(12).iterrows():
                ins["transactions"].append({"date": r["Start Date"].strftime("%Y-%m-%d"), "insider": r.get("Insider"),
                                            "position": r.get("Position"), "type": "Buy" if "purchase" in str(r.get("Text", "")).lower() else "Sell",
                                            "shares": _num(r.get("Shares")), "value": _num(r.get("Value"))})
        inst = _safe(lambda: t.institutional_holders)
        ins["topHolders"] = [] if inst is None or inst.empty else [
            {"holder": r.get("Holder"), "pct": (_num(r.get("pctHeld")) or 0) * 100, "pctChange": (_num(r.get("pctChange")) or 0) * 100} for _, r in inst.head(8).iterrows()]
        ch = [h["pctChange"] for h in ins["topHolders"] if h["pctChange"] is not None]
        ins["institutionalChangePct"] = (sum(ch) / len(ch)) if ch else None  # mean % change in position among top holders

        spf = _num(info.get("shortPercentOfFloat"))
        short = {"pctFloat": spf * 100 if spf is not None else None, "daysToCover": _num(info.get("shortRatio")),
                 "sharesShort": _num(info.get("sharesShort"))}

        opt = {"putCall": None, "putCallVolume": None, "iv": None, "ivPercentile": None, "expiry": None}
        exps = _safe(lambda: t.options, ()) or ()
        today = dt.date.today()
        pick = next((e for e in exps if (dt.date.fromisoformat(e) - today).days >= 14), exps[0] if exps else None)
        if pick:
            ch_ = _safe(lambda: t.option_chain(pick))
            if ch_ is not None:
                c, p = ch_.calls, ch_.puts
                coi, poi = c["openInterest"].fillna(0).sum(), p["openInterest"].fillna(0).sum()
                cv, pv = c["volume"].fillna(0).sum(), p["volume"].fillna(0).sum()
                px = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
                iv = None
                if px:
                    atm = pd.concat([c.iloc[(c["strike"] - px).abs().argsort()[:2]], p.iloc[(p["strike"] - px).abs().argsort()[:2]]])
                    iv = _num(atm["impliedVolatility"].mean())
                opt.update(putCall=float(poi / coi) if coi else None, putCallVolume=float(pv / cv) if cv else None,
                           iv=iv * 100 if iv else None, expiry=pick)
                if iv and hv_series is not None and hv_series.dropna().size > 60:
                    # PROXY: percentile of current IV within the trailing-1y distribution of realised vol.
                    opt["ivPercentile"] = float((hv_series.dropna() <= iv * 100).mean() * 100)
        return {"insider": ins, "short": short, "options": opt}
    return await with_backoff(work)


# ------------------------------------------------------------------- news
@ttl_cache(900)
async def get_news(ticker: str, days: int = 14, limit: int = 20) -> list[dict]:
    def work():
        raw = _safe(lambda: _tk(ticker).news, []) or []
        if not raw:  # Ticker.news is intermittently empty; fall back to search news, keeping only items tagged with this ticker
            sn = _safe(lambda: yf.Search(ticker, news_count=25, max_results=1).news, []) or []
            raw = [n for n in sn if ticker.upper() in [str(x).upper() for x in n.get("relatedTickers", [])]]
        out, cutoff = [], dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        for n in raw:
            c = n.get("content", n)
            title = c.get("title")
            if not title:
                continue
            ts = c.get("pubDate") or c.get("displayTime")
            if ts is None and n.get("providerPublishTime"):
                ts = dt.datetime.fromtimestamp(n["providerPublishTime"], dt.timezone.utc).isoformat()
            try:
                when = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except ValueError:
                when = None
            if when and when < cutoff:
                continue
            url = (c.get("canonicalUrl") or c.get("clickThroughUrl") or {}).get("url") or n.get("link")
            out.append({"title": title, "source": (c.get("provider") or {}).get("displayName") or n.get("publisher"),
                        "time": when.isoformat() if when else None, "url": url, "summary": c.get("summary")})
        return out[:limit]
    return await with_backoff(work)


# ---------------------------------------------------------------- context
async def get_market_context(ticker: str, sector: Optional[str], stock_close: pd.Series) -> dict:
    spy = (await get_price_history("SPY", "2y"))["close"]
    etf_sym = SECTOR_ETF.get(sector or "")
    etf = (await get_price_history(etf_sym, "2y"))["close"] if etf_sym else None
    vix = tnx = None
    try:
        v = await get_price_history("^VIX", "3mo")
        vix = float(v["close"].iloc[-1]) if len(v) else None
        y = await get_price_history("^TNX", "6mo")
        if len(y) > 60:
            tnx = {"level": float(y["close"].iloc[-1]), "change3mBps": round((float(y["close"].iloc[-1]) - float(y["close"].iloc[-63])) * 100, 1)}
    except Exception as e:  # noqa: BLE001
        log.info("macro fetch failed: %s", e)
    return {"spy": spy, "sectorEtf": etf_sym, "sectorSeries": etf, "vix": vix, "tenYear": tnx}


# ----------------------------------------------------------------- events
@ttl_cache(3600)
async def get_events(ticker: str) -> list[dict]:
    def work():
        cal = _safe(lambda: _tk(ticker).calendar, {}) or {}
        today = dt.date.today()
        events = []

        def add(typ, d, risk):
            if isinstance(d, (list, tuple)):
                d = d[0] if d else None
            if d is None:
                return
            if isinstance(d, dt.datetime):
                d = d.date()
            if isinstance(d, str):
                d = dt.date.fromisoformat(d[:10])
            events.append({"type": typ, "date": d.isoformat(), "daysAway": (d - today).days, "risk": risk and 0 <= (d - today).days <= 14})

        add("Earnings", cal.get("Earnings Date"), True)
        add("Ex-dividend", cal.get("Ex-Dividend Date"), False)
        return [e for e in events if e["daysAway"] >= 0]
    return await with_backoff(work)


# ----------------------------------------------------------------- search
@ttl_cache(300)
async def search(q: str, limit: int = 8) -> list[dict]:
    def work():
        res = yf.Search(q, max_results=limit, news_count=0).quotes
        return [{"symbol": r.get("symbol"), "name": r.get("longname") or r.get("shortname"), "exchange": r.get("exchDisp"),
                 "type": r.get("quoteType")} for r in res if r.get("symbol") and r.get("quoteType") in ("EQUITY", "ETF")]
    return await with_backoff(work, attempts=2)
