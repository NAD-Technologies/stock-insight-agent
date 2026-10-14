"""Technical indicators and TradingView-style signal summary (pure pandas/numpy)."""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- indicators
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0)


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift()
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14):
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    a = atr(df, n)
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi


def stochastic(df: pd.DataFrame, k=14, d=3, smooth=3):
    ll, hh = df["low"].rolling(k).min(), df["high"].rolling(k).max()
    raw = 100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan)
    kk = raw.rolling(smooth).mean()
    return kk, kk.rolling(d).mean()


def roc(close: pd.Series, n: int = 12) -> pd.Series:
    return close.pct_change(n) * 100


def williams_r(df: pd.DataFrame, n: int = 14) -> pd.Series:
    hh, ll = df["high"].rolling(n).max(), df["low"].rolling(n).min()
    return -100 * (hh - df["close"]) / (hh - ll).replace(0, np.nan)


def cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma = tp.rolling(n).mean()
    md = tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - ma) / (0.015 * md.replace(0, np.nan))


def bollinger(close: pd.Series, n=20, k=2.0):
    mid = sma(close, n)
    sd = close.rolling(n).std(ddof=0)
    up, lo = mid + k * sd, mid - k * sd
    return up, mid, lo, (up - lo) / mid


def obv(df: pd.DataFrame) -> pd.Series:
    return (np.sign(df["close"].diff()).fillna(0) * df["volume"]).cumsum()


def cmf(df: pd.DataFrame, n: int = 20) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    mfv = ((2 * df["close"] - df["low"] - df["high"]) / rng).fillna(0) * df["volume"]
    return mfv.rolling(n).sum() / df["volume"].rolling(n).sum()


def accum_dist(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    return (((2 * df["close"] - df["low"] - df["high"]) / rng).fillna(0) * df["volume"]).cumsum()


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP; for daily bars this is a rolling 20-day VWAP."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).rolling(20).sum() / df["volume"].rolling(20).sum()


def ichimoku(df: pd.DataFrame):
    conv = (df["high"].rolling(9).max() + df["low"].rolling(9).min()) / 2
    base = (df["high"].rolling(26).max() + df["low"].rolling(26).min()) / 2
    a = ((conv + base) / 2).shift(26)
    b = ((df["high"].rolling(52).max() + df["low"].rolling(52).min()) / 2).shift(26)
    return conv, base, a, b


def hist_vol(close: pd.Series, n: int = 20) -> pd.Series:
    return np.log(close / close.shift()).rolling(n).std() * np.sqrt(252) * 100


# ------------------------------------------------------------------- levels
def swing_points(df: pd.DataFrame, w: int = 5):
    hi, lo = df["high"], df["low"]
    is_hi = hi == hi.rolling(2 * w + 1, center=True).max()
    is_lo = lo == lo.rolling(2 * w + 1, center=True).min()
    return hi[is_hi].dropna(), lo[is_lo].dropna()


def support_resistance(df: pd.DataFrame, tol: float = 0.015, max_levels: int = 3):
    """Cluster swing highs/lows + classic pivot into levels below / above last price."""
    price = float(df["close"].iloc[-1])
    highs, lows = swing_points(df.tail(250))
    pts = sorted(list(highs.values) + list(lows.values))
    clusters: list[list[float]] = []
    for p in pts:
        if clusters and abs(p - np.mean(clusters[-1])) / np.mean(clusters[-1]) < tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = [(float(np.mean(c)), len(c)) for c in clusters]
    prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
    pivot = (prev["high"] + prev["low"] + prev["close"]) / 3
    levels += [(float(pivot), 1), (float(2 * pivot - prev["low"]), 1), (float(2 * pivot - prev["high"]), 1)]
    sup = sorted({round(l, 2) for l, _ in levels if l < price}, reverse=True)[:max_levels]
    res = sorted({round(l, 2) for l, _ in levels if l > price})[:max_levels]
    return sup, res, float(pivot)


def fibonacci(df: pd.DataFrame, lookback: int = 120):
    seg = df.tail(lookback)
    hi, lo = float(seg["high"].max()), float(seg["low"].min())
    up_trend = seg["high"].idxmax() > seg["low"].idxmin()
    rng = hi - lo
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    levels = {str(r): round(hi - r * rng if up_trend else lo + r * rng, 2) for r in ratios}
    return {"high": hi, "low": lo, "direction": "up" if up_trend else "down", "levels": levels}


def trend_structure(df: pd.DataFrame) -> str:
    highs, lows = swing_points(df.tail(180), 5)
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs.iloc[-1] > highs.iloc[-2]
        hl = lows.iloc[-1] > lows.iloc[-2]
        if hh and hl:
            return "uptrend (HH/HL)"
        if not hh and not hl:
            return "downtrend (LH/LL)"
    return "mixed"


def rsi_divergence(df: pd.DataFrame, r: pd.Series) -> str | None:
    highs, lows = swing_points(df.tail(120), 4)
    if len(highs) >= 2:
        a, b = highs.index[-2], highs.index[-1]
        if highs[b] > highs[a] and r[b] < r[a] - 2:
            return "bearish"
    if len(lows) >= 2:
        a, b = lows.index[-2], lows.index[-1]
        if lows[b] < lows[a] and r[b] > r[a] + 2:
            return "bullish"
    return None


# ------------------------------------------------------------------- engine
BUY, NEUTRAL, SELL = "Buy", "Neutral", "Sell"


def _sig(name, value, signal, group, note=""):
    v = None if value is None or (isinstance(value, float) and np.isnan(value)) else round(float(value), 4)
    return {"name": name, "value": v, "signal": signal if v is not None else NEUTRAL, "group": group, "note": note}


def compute_indicator_series(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    c = df["close"]
    for n in (20, 50, 200):
        out[f"sma{n}"] = sma(c, n)
    for n in (9, 21):
        out[f"ema{n}"] = ema(c, n)
    out["rsi"] = rsi(c)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(c)
    out["bb_upper"], out["bb_mid"], out["bb_lower"], out["bb_width"] = bollinger(c)
    out["vwap"] = vwap(df)
    out["atr"] = atr(df)
    return out


def rating_from_counts(buy: int, sell: int, total: int) -> str:
    if total == 0:
        return "Neutral"
    net = (buy - sell) / total
    if net >= 0.5:
        return "Strong Buy"
    if net >= 0.1:
        return "Buy"
    if net <= -0.5:
        return "Strong Sell"
    if net <= -0.1:
        return "Sell"
    return "Neutral"


def compute_technicals(df: pd.DataFrame) -> dict:
    """df: columns open/high/low/close/volume, ascending DatetimeIndex."""
    if df is None or len(df) < 30:
        return {"available": False, "signals": [], "summary": {}, "score": None}
    c, price = df["close"], float(df["close"].iloc[-1])
    last = lambda s: float(s.iloc[-1]) if len(s) and pd.notna(s.iloc[-1]) else None  # noqa: E731
    sigs: list[dict] = []

    # --- moving averages
    for n in (20, 50, 200):
        v = last(sma(c, n))
        sigs.append(_sig(f"SMA {n}", v, BUY if v and price > v else SELL, "ma", f"price {price:.2f} vs {v and round(v, 2)}"))
    for n in (9, 21):
        v = last(ema(c, n))
        sigs.append(_sig(f"EMA {n}", v, BUY if v and price > v else SELL, "ma"))
    s50, s200 = sma(c, 50), sma(c, 200)
    cross = None
    if s200.notna().sum() > 5:
        diff = (s50 - s200).dropna()
        sigs.append(_sig("SMA 50 vs 200", last(diff), BUY if diff.iloc[-1] > 0 else SELL, "ma",
                         "Golden Cross regime" if diff.iloc[-1] > 0 else "Death Cross regime"))
        recent = np.sign(diff.tail(10))
        if recent.nunique() > 1:
            cross = "golden" if diff.iloc[-1] > 0 else "death"
    cl, ba, sa, sb = ichimoku(df)
    if pd.notna(sa.iloc[-1]) and pd.notna(sb.iloc[-1]):
        top, bot = max(sa.iloc[-1], sb.iloc[-1]), min(sa.iloc[-1], sb.iloc[-1])
        pos = "above cloud" if price > top else "below cloud" if price < bot else "inside cloud"
        sigs.append(_sig("Ichimoku", price - top, BUY if price > top else SELL if price < bot else NEUTRAL, "ma", pos))
    a, pdi, mdi = adx(df)
    adx_v = last(a)
    di_sig = BUY if last(pdi) > last(mdi) else SELL
    sigs.append(_sig("ADX(14)", adx_v, di_sig if adx_v and adx_v > 25 else NEUTRAL, "ma",
                     "strong trend" if adx_v and adx_v > 25 else "weak/no trend"))

    # --- oscillators
    r = rsi(c)
    rv = last(r)
    sigs.append(_sig("RSI(14)", rv, BUY if rv and rv < 30 else SELL if rv and rv > 70 else NEUTRAL, "osc",
                     "oversold" if rv and rv < 30 else "overbought" if rv and rv > 70 else ""))
    ml, ms, mh = macd(c)
    sigs.append(_sig("MACD(12,26,9)", last(mh), BUY if last(mh) and last(mh) > 0 else SELL, "osc",
                     "bullish" if last(mh) and last(mh) > 0 else "bearish"))
    k, d = stochastic(df)
    kv = last(k)
    sigs.append(_sig("Stochastic %K", kv, BUY if kv is not None and kv < 20 and last(k) > last(d) else
                     SELL if kv is not None and kv > 80 and last(k) < last(d) else NEUTRAL, "osc"))
    rc = last(roc(c))
    sigs.append(_sig("ROC(12)", rc, BUY if rc and rc > 0 else SELL if rc and rc < 0 else NEUTRAL, "osc"))
    w = last(williams_r(df))
    sigs.append(_sig("Williams %R", w, BUY if w is not None and w < -80 else SELL if w is not None and w > -20 else NEUTRAL, "osc"))
    cc = last(cci(df))
    sigs.append(_sig("CCI(20)", cc, BUY if cc is not None and cc < -100 else SELL if cc is not None and cc > 100 else NEUTRAL, "osc"))

    # --- volatility / volume (informational + oscillator-ish)
    up, mid, lo, width = bollinger(c)
    pb = (price - last(lo)) / (last(up) - last(lo)) if last(up) is not None and last(up) != last(lo) else None
    squeeze = bool(width.dropna().size > 60 and width.iloc[-1] <= width.dropna().tail(120).quantile(0.1))
    sigs.append(_sig("Bollinger %B", pb, BUY if pb is not None and pb < 0.05 else SELL if pb is not None and pb > 0.95 else NEUTRAL, "osc",
                     "squeeze" if squeeze else ""))
    ob = obv(df)
    obv_trend = float(np.polyfit(range(20), ob.tail(20).values, 1)[0]) if len(ob) >= 20 else None
    sigs.append(_sig("OBV trend", obv_trend, BUY if obv_trend and obv_trend > 0 else SELL if obv_trend and obv_trend < 0 else NEUTRAL, "vol"))
    cm = last(cmf(df))
    sigs.append(_sig("Chaikin MF", cm, BUY if cm and cm > 0.05 else SELL if cm and cm < -0.05 else NEUTRAL, "vol"))
    vw = last(vwap(df))
    sigs.append(_sig("VWAP(20)", vw, BUY if vw and price > vw else SELL, "vol"))
    vol_ratio = float(df["volume"].iloc[-1] / df["volume"].tail(20).mean()) if df["volume"].tail(20).mean() else None

    # --- tallies (TradingView style: oscillators and MAs counted separately)
    def tally(group):
        g = [s for s in sigs if s["group"] == group]
        b, s_, n_ = (sum(1 for x in g if x["signal"] == t) for t in (BUY, SELL, NEUTRAL))
        return {"buy": b, "sell": s_, "neutral": n_, "rating": rating_from_counts(b, s_, len(g))}

    osc, ma = tally("osc"), tally("ma")
    allg = {"buy": osc["buy"] + ma["buy"], "sell": osc["sell"] + ma["sell"], "neutral": osc["neutral"] + ma["neutral"]}
    allg["rating"] = rating_from_counts(allg["buy"], allg["sell"], sum(allg.values()))

    sup, res, pivot = support_resistance(df)
    a14 = last(atr(df))
    hi52, lo52 = float(df["high"].tail(252).max()), float(df["low"].tail(252).min())
    breakout = "breakout" if len(df) > 21 and price > float(df["high"].iloc[-21:-1].max()) else \
               "breakdown" if len(df) > 21 and price < float(df["low"].iloc[-21:-1].min()) else None
    return {
        "available": True,
        "signals": sigs,
        "summary": {"oscillators": osc, "movingAverages": ma, "overall": allg},
        "levels": {"support": sup, "resistance": res, "pivot": round(pivot, 2), "fibonacci": fibonacci(df),
                   "pctFrom52wHigh": round((price / hi52 - 1) * 100, 2), "pctFrom52wLow": round((price / lo52 - 1) * 100, 2)},
        "patterns": {"structure": trend_structure(df), "crossRecent": cross, "divergence": rsi_divergence(df, r),
                     "breakout": breakout, "bollingerSqueeze": squeeze},
        "values": {"price": price, "rsi": rv, "adx": adx_v, "atr": a14, "atrPct": a14 / price * 100 if a14 else None,
                   "histVol20": last(hist_vol(c)), "volumeVsAvg20": vol_ratio, "macdHist": last(mh)},
    }
