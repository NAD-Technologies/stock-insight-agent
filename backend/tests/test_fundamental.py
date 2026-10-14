import pytest

from analytics import fundamental as F


def test_cagr_and_yoy():
    assert F.cagr(100, 133.1, 3) == pytest.approx(0.10, abs=1e-4)
    assert F.cagr(-1, 5, 3) is None
    assert F.yoy(110, 100) == pytest.approx(0.10)
    assert F.yoy(1, 0) is None


def test_dcf_monotonic_in_wacc_and_growth():
    base = F.dcf(100, 0.08, 0.09, 0.025, 10)
    assert F.dcf(100, 0.08, 0.11, 0.025, 10) < base
    assert F.dcf(100, 0.12, 0.09, 0.025, 10) > base
    assert F.dcf(-5, 0.08, 0.09, 0.025, 10) is None
    assert F.dcf(100, 0.08, 0.02, 0.025, 10) is None  # wacc <= terminal growth is invalid


def test_dcf_known_value():
    # zero growth perpetuity: EV = FCF / wacc = 1000, over 10 shares -> 100
    assert F.dcf(100, 0.0, 0.10, 0.0, 10) == pytest.approx(100.0, rel=1e-6)


def test_graham():
    assert F.graham_number(5, 20) == pytest.approx((22.5 * 100) ** 0.5)
    assert F.graham_number(-1, 20) is None


def test_altman_z_safe_company():
    f = dict(totalAssets=1000, workingCapital=300, retainedEarnings=400, ebit=200, marketCap=2000, revenue=1200, totalLiabilities=400)
    assert F.altman_z(f) > 3
    assert F.altman_z({**f, "ebit": None}) is None


def test_piotroski_perfect_and_missing():
    prev = dict(netIncome=50, totalAssets=1000, operatingCashFlow=60, longTermDebt=300, currentAssets=400, currentLiabilities=300,
                shares=100, grossProfit=300, revenue=1000)
    cur = dict(netIncome=90, totalAssets=1000, operatingCashFlow=120, longTermDebt=200, currentAssets=500, currentLiabilities=300,
               shares=100, grossProfit=400, revenue=1100)
    assert F.piotroski(cur, prev) == 9
    assert F.piotroski({}, {}) is None


def test_fair_value_margin_of_safety():
    f = dict(fcf=1000, fcfGrowthEstimate=0.05, sharesOutstanding=100, totalDebt=0, cash=0, eps=5, bookValuePerShare=20)
    fv = F.fair_value(f, 50)
    assert fv["low"] < fv["base"] < fv["high"]
    assert fv["marginOfSafety"] == pytest.approx((fv["base"] - 50) / fv["base"] * 100, abs=0.1)


def test_metrics_signal_vs_sector_median():
    rows = F.build_metrics({"pe": 10, "roe": 0.30, "debtToEquity": 3.0}, "Technology")
    by = {r["key"]: r["signal"] for r in rows}
    assert by["pe"] == "good" and by["roe"] == "good" and by["debtToEquity"] == "bad"
    assert by["pb"] == "na"  # missing => N/A, never guessed
