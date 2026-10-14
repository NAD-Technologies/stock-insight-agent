import datetime as dt

import pytest

from agent.news import news_score
from analytics import scoring as S
from analytics import technical as T
from tests.conftest import make_ohlcv

NO_TECH = {"available": False}


def test_scale_clamps_and_inverts():
    assert S.scale(5, 0, 10) == 50
    assert S.scale(-5, 0, 10) == 0 and S.scale(50, 0, 10) == 100
    assert S.scale(2, 0, 10, invert=True) == 80
    assert S.scale(None, 0, 10) is None


def test_rating_bands_boundaries():
    b = S.load_config()["rating_bands"]
    got = [S.rating_for(x, b) for x in (100, 80, 79.9, 65, 64.9, 45, 44.9, 30, 29.9, 0)]
    assert got == ["Strong Buy", "Strong Buy", "Buy", "Buy", "Hold", "Hold", "Sell", "Sell", "Strong Sell", "Strong Sell"]
    assert S.rating_for(None, b) == "N/A"


def test_profile_weights_sum_to_one():
    for name, w in S.load_config()["profiles"].items():
        assert sum(w.values()) == pytest.approx(1.0), name


def _pillar(score, cov=1.0):
    return {"score": score, "components": [S.comp("x", score, score, 1)], "coverage": cov}


def test_composite_weighted_average():
    p = {"technical": _pillar(100), "fundamental": _pillar(0), "analyst": _pillar(50), "sentiment": _pillar(50), "risk": _pillar(50)}
    r = S.recommend(p, [], None, NO_TECH, {}, "balanced")
    assert r["compositeScore"] == pytest.approx(100 * .3 + 0 * .3 + 50 * .4)
    assert S.recommend(p, [], None, NO_TECH, {}, "trader")["compositeScore"] > r["compositeScore"]
    assert S.recommend(p, [], None, NO_TECH, {}, "investor")["compositeScore"] < r["compositeScore"]


def test_missing_pillars_renormalise_and_lower_confidence():
    p = {"technical": _pillar(90), "fundamental": _pillar(None, 0), "analyst": _pillar(None, 0),
         "sentiment": _pillar(None, 0), "risk": _pillar(None, 0)}
    r = S.recommend(p, [], None, NO_TECH, {}, "balanced")
    assert r["compositeScore"] == 90
    assert r["rating"] == "Buy"  # Strong Buy capped: only 30% of weight has data
    assert r["confidence"]["level"] == "Low"


def test_event_risk_and_disagreement_lower_confidence():
    p = {k: _pillar(70) for k in ("technical", "fundamental", "analyst", "sentiment", "risk")}
    assert S.recommend(p, [], None, NO_TECH, {})["confidence"]["level"] == "High"
    ev = [{"type": "Earnings", "daysAway": 5, "risk": True}]
    assert S.recommend(p, ev, None, NO_TECH, {})["confidence"]["level"] == "Medium"
    p["technical"], p["fundamental"] = _pillar(95), _pillar(20)
    assert S.recommend(p, ev, None, NO_TECH, {})["confidence"]["level"] == "Low"


def test_drivers_top3_with_values():
    comps = [S.comp(f"m{i}", i, s, 1) for i, s in enumerate([95, 90, 85, 80, 10, 15, 20, 25, 50])]
    d = S.drivers({"technical": S.aggregate(comps)})
    assert [x["metric"] for x in d["positive"]] == ["m0", "m1", "m2"]
    assert [x["metric"] for x in d["negative"]] == ["m4", "m5", "m6"]
    assert d["positive"][0]["value"] == 0


def test_trade_plan_sanity():
    tech = T.compute_technicals(make_ohlcv(drift=0.002))
    price = tech["values"]["price"]
    plan = S.trade_plan(price, tech, {"targetMean": price * 1.2})
    assert plan["stopLoss"] < plan["entry"] < plan["t1"] <= plan["t2"]
    assert plan["riskReward"] > 0


def test_news_score_recency_and_impact():
    now = dt.datetime.now(dt.timezone.utc)
    fresh_bull = {"sentiment": "Bullish", "impact": "High", "time": now.isoformat()}
    old_bear = {"sentiment": "Bearish", "impact": "High", "time": (now - dt.timedelta(days=14)).isoformat()}
    assert news_score([fresh_bull, old_bear], now) > 0.7
    assert news_score([], now) is None


def test_technical_pillar_ranks_trends(uptrend, downtrend):
    up = S.score_technical(T.compute_technicals(uptrend))["score"]
    dn = S.score_technical(T.compute_technicals(downtrend))["score"]
    assert up > 60 > 40 > dn
