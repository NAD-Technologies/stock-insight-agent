import numpy as np
import pandas as pd
import pytest

from analytics import technical as T


def test_sma_known_values():
    s = pd.Series([1, 2, 3, 4, 5.0])
    assert T.sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0]


def test_ema_converges_to_constant():
    assert T.ema(pd.Series([10.0] * 50), 9).iloc[-1] == pytest.approx(10.0)


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    down = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert T.rsi(up).iloc[-1] == pytest.approx(100.0)
    assert T.rsi(down).iloc[-1] < 1.0
    r = T.rsi(pd.Series(np.random.default_rng(1).normal(100, 2, 200)))
    assert r.dropna().between(0, 100).all()


def test_macd_histogram_identity(uptrend):
    line, sig, hist = T.macd(uptrend["close"])
    assert (hist - (line - sig)).abs().max() < 1e-12
    assert line.iloc[-1] > 0  # steady uptrend => fast EMA above slow


def test_bollinger_contains_stationary_price():
    # a trending series rides the band, so use a stationary one: ~95% of points fall inside 2 sigma
    c = pd.Series(np.random.default_rng(5).normal(100, 2, 500))
    up, mid, lo, _ = T.bollinger(c)
    inside = ((c <= up) & (c >= lo))[20:].mean()
    assert inside > 0.9
    assert (up[20:] >= mid[20:]).all() and (mid[20:] >= lo[20:]).all()


def test_atr_positive(uptrend):
    assert (T.atr(uptrend).dropna() > 0).all()


def test_stochastic_range(uptrend):
    k, d = T.stochastic(uptrend)
    assert k.dropna().between(0, 100).all()


def test_williams_r_range(uptrend):
    assert T.williams_r(uptrend).dropna().between(-100, 0).all()


def test_obv_direction():
    df = pd.DataFrame({"close": [1, 2, 3, 2.0], "volume": [10, 10, 10, 10]})
    assert T.obv(df).tolist() == [0, 10, 20, 10]


def test_adx_high_in_strong_trend(uptrend):
    assert T.adx(uptrend)[0].iloc[-1] > 25


def test_summary_uptrend_vs_downtrend(uptrend, downtrend):
    up = T.compute_technicals(uptrend)
    dn = T.compute_technicals(downtrend)
    assert up["summary"]["movingAverages"]["buy"] > up["summary"]["movingAverages"]["sell"]
    assert dn["summary"]["movingAverages"]["sell"] > dn["summary"]["movingAverages"]["buy"]
    assert up["summary"]["overall"]["rating"] in ("Buy", "Strong Buy")
    assert dn["summary"]["overall"]["rating"] in ("Sell", "Strong Sell")


def test_levels_ordered_around_price(uptrend):
    out = T.compute_technicals(uptrend)
    p = out["values"]["price"]
    assert all(s < p for s in out["levels"]["support"])
    assert all(r > p for r in out["levels"]["resistance"])


def test_insufficient_data_is_unavailable():
    one = pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]})
    assert T.compute_technicals(one)["available"] is False


def test_rating_from_counts():
    assert T.rating_from_counts(10, 0, 12) == "Strong Buy"
    assert T.rating_from_counts(0, 10, 12) == "Strong Sell"
    assert T.rating_from_counts(4, 4, 12) == "Neutral"
