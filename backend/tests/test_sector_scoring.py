import datetime as dt
import math

import pandas as pd
import pytest

from sector_pulse import scoring as S

R = S.load_yaml("rules.yaml")
T = S.load_yaml("themes.yaml")
NOW = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)


def test_config_is_consistent():
    for h, w in R["weights"].items():
        assert abs(sum(w.values()) - 1) < 1e-9, h
    assert set(R["weights"]) == set(R["horizons"])
    ids = [t["id"] for t in T["themes"]]
    assert len(ids) == len(set(ids)) and len(ids) >= 25
    for ev, m in R["impact_matrix"].items():
        assert ev in R["event_types"], ev
        assert set(m) <= set(ids), (ev, set(m) - set(ids))
        assert all(-1 <= v <= 1 for v in m.values())
    assert set(T["yahoo_sector_map"].values()) <= set(ids)


def test_decay_halves_every_half_life():
    assert S.decay(0, 14) == 1
    assert S.decay(14, 14) == pytest.approx(0.5)
    assert S.decay(28, 14) == pytest.approx(0.25)
    assert S.decay(-5, 14) == 1  # clock skew never boosts a weight


def test_to_score_is_bounded_and_centred():
    assert S.to_score(0) == 50
    assert S.to_score(1) == 100 and S.to_score(-1) == 0
    assert S.to_score(5) == 100


def test_period_return_and_breadth():
    c = pd.Series(range(100, 160), dtype=float)
    assert S.period_return(c, 10) == pytest.approx(159 / 149 - 1)
    assert S.period_return(c, 100) is None
    down = pd.Series(range(160, 100, -1), dtype=float)
    assert S.pct_above_sma([c, down, c], 50) == pytest.approx(2 / 3)
    assert S.pct_above_sma([pd.Series([1.0, 2.0])], 50) is None


def test_trend_signal():
    up = pd.Series([float(x) for x in range(1, 261)])
    assert S.trend_signal(up) == 1.0
    assert S.trend_signal(up[::-1].reset_index(drop=True)) == -1.0
    assert S.trend_signal(pd.Series([1.0] * 10)) is None


def test_momentum_signal_direction_and_missing_parts():
    pos = S.momentum_signal(0.08, 0.8, 1.0, R, "1M")
    neg = S.momentum_signal(-0.08, 0.2, -1.0, R, "1M")
    assert pos > 0.5 > -0.5 > neg
    assert S.momentum_signal(None, None, None, R, "1M") is None
    only_breadth = S.momentum_signal(None, 1.0, None, R, "1M")
    assert only_breadth == pytest.approx(1.0)  # renormalised over the single available part
    assert S.momentum_signal(0.0, 0.5, 0.0, R, "1M") == pytest.approx(0.0)


def _item(sent, impact, days_old):
    return {"sentiment": sent, "impact": impact, "time": (NOW - dt.timedelta(days=days_old)).isoformat()}


def test_news_signal_weights_recency_impact_and_shrinks():
    sig, n = S.news_signal([_item("Bullish", "High", 0)], NOW, R)
    assert n == 1 and 0 < sig < 0.5  # one headline cannot dominate (shrinkage)
    many, n2 = S.news_signal([_item("Bullish", "High", 0)] * 20, NOW, R)
    assert many > sig and n2 == 20
    bear, _ = S.news_signal([_item("Bearish", "Med", 1)] * 5, NOW, R)
    assert bear < 0
    assert S.news_signal([_item("Bullish", "High", 30)], NOW, R) == (None, 0)  # outside the lookback window
    fresh, _ = S.news_signal([_item("Bullish", "Low", 0), _item("Bearish", "Low", 6)], NOW, R)
    assert fresh > 0  # the newer item outweighs the stale one


def test_events_use_max_per_type_and_matrix_direction():
    ev = [{"type": "conflict_escalation", "severity": "High", "last_seen": int((NOW - dt.timedelta(days=1)).timestamp())},
          {"type": "conflict_escalation", "severity": "High", "last_seen": int((NOW - dt.timedelta(days=2)).timestamp())},
          {"type": "mystery", "severity": "High", "last_seen": int(NOW.timestamp())}]
    active = S.active_event_weights(ev, R, NOW)
    assert set(active) == {"conflict_escalation"}
    assert active["conflict_escalation"] == pytest.approx(S.decay(1, 30))  # max, not the sum of two duplicates
    assert S.event_signal(active, "defense_aerospace", R) > 0
    assert S.event_signal(active, "airlines_travel", R) < 0
    assert S.event_signal(active, "homebuilders", R) == 0
    assert S.event_signal({}, "defense_aerospace", R) is None


def test_flows_proxy():
    assert S.flows_signal(150, 100, 0.05) > 0
    assert S.flows_signal(150, 100, -0.05) < 0
    assert S.flows_signal(None, 100, 0.05) is None


def test_composite_renormalises_over_available_factors():
    w = R["weights"]["1M"]
    score, used, missing = S.composite({"momentum": 80.0, "news": 60.0, "events": None, "flows": 50.0,
                                        "earnings": None, "social": None}, w)
    assert sum(used.values()) == pytest.approx(1)
    assert set(missing) == {"events", "earnings", "social"}
    expected = (0.25 * 80 + 0.20 * 60 + 0.10 * 50) / 0.55
    assert score == pytest.approx(round(expected, 1))
    assert S.composite({k: None for k in w}, w)[0] is None


def test_direction_probability_and_bands():
    assert S.direction(75, R) == "Up" and S.direction(60, R) == "Up"
    assert S.direction(50, R) == "Flat" and S.direction(40, R) == "Down" and S.direction(10, R) == "Down"
    assert S.direction(None, R) == "Flat"
    assert S.prob_up(50, R) == 0.5
    assert S.prob_up(80, R) > 0.9 > 0.1 > S.prob_up(20, R)
    assert S.prob_up(None, R) is None


def test_confidence_reflects_coverage_agreement_and_news():
    w = R["weights"]["1M"]
    full = {"momentum": 70.0, "earnings": 68.0, "news": 66.0, "events": 65.0, "social": 64.0, "flows": 67.0}
    assert S.confidence(full, w, 20, R)[0] == "High"
    partial = {**full, "earnings": None, "social": None}
    lvl, why = S.confidence(partial, w, 20, R)
    assert lvl == "Medium" and any("factor weight" in x for x in why)
    split = {**full, "momentum": 95.0, "news": 10.0}
    assert S.confidence(split, w, 20, R)[0] != "High"
    assert S.confidence({k: None for k in w}, w, 0, R)[0] == "Low"
    assert S.confidence(full, w, 1, R)[0] != "High"  # thin news


def test_sensitivity_flips_with_theme_direction():
    assert S.sensitivity_score(1.5, 70) > 50 > S.sensitivity_score(1.5, 30)
    assert S.sensitivity_score(0.6, 30) > 50 > S.sensitivity_score(0.6, 70)
    assert S.sensitivity_score(None, 70) is None


def test_rank_score_weights_and_neutral_defaults():
    assert S.rank_score(None, None, None, None, R) == 50.0
    hi = S.rank_score(90, 0.8, 0.05, 80, R)
    lo = S.rank_score(20, -0.8, -0.05, 20, R)
    assert hi > 70 > 30 > lo
    only_comp = S.rank_score(100, None, None, None, R)
    assert only_comp == pytest.approx(0.5 * 100 + 0.2 * 50 + 0.15 * 50 + 0.15 * 50)


def test_outcome_and_baseline():
    assert S.outcome_label(0.03, 0.02) == "Up"
    assert S.outcome_label(-0.03, 0.02) == "Down"
    assert S.outcome_label(0.01, 0.02) == "Flat"
    assert S.baseline_label(0.05, R) == "Up" and S.baseline_label(None, R) == "Flat"
    assert math.isfinite(S.to_score(0.3))
