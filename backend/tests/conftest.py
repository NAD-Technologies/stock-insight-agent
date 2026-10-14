import numpy as np
import pandas as pd
import pytest


def make_ohlcv(n=300, drift=0.001, vol=0.01, seed=7, start=100.0):
    rng = np.random.default_rng(seed)
    ret = rng.normal(drift, vol, n)
    close = start * np.exp(np.cumsum(ret))
    open_ = np.r_[start, close[:-1]]
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": rng.integers(1_000_000, 2_000_000, n)}, index=idx)


@pytest.fixture
def uptrend():
    return make_ohlcv(drift=0.003, vol=0.008)


@pytest.fixture
def downtrend():
    return make_ohlcv(drift=-0.003, vol=0.008, seed=3)
