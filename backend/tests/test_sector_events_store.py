import datetime as dt
import time

import pandas as pd
import pytest

from api import db
from sector_pulse import events as EV
from sector_pulse import pipeline as PL
from sector_pulse import scoring as S
from sector_pulse import store

R = S.load_yaml("rules.yaml")


# ------------------------------------------------------------------ events
def test_match_type_picks_best_keyword_match():
    assert EV.match_type("Missile strike escalates conflict in the region", R) == "conflict_escalation"
    assert EV.match_type("OPEC cuts output as oil supply tightens", R) == "oil_supply_shock"
    assert EV.match_type("Fed signals another rate hike", R) == "rate_hike"
    assert EV.match_type("Apple unveils new iPhone", R) is None


def _h(title, source):
    return {"title": title, "url": f"https://{source}/x", "source": source}


def test_detect_rates_severity_by_headlines_and_outlets():
    many = [_h(f"War escalates: troops move, story {i}", f"outlet{i % 4}.com") for i in range(6)]
    ev = {e["type"]: e for e in EV.detect(many, R)}
    assert ev["conflict_escalation"]["severity"] == "High"
    assert ev["conflict_escalation"]["n_sources"] >= 3
    few = EV.detect([_h("New tariffs announced", "a.com"), _h("Tariff threat grows", "b.com")], R)
    assert few[0]["type"] == "tariffs" and few[0]["severity"] == "Med"
    one = EV.detect([_h("Sanctions imposed on exporter", "a.com")], R)
    assert one[0]["severity"] == "Low"
    assert EV.detect([_h("Apple unveils new iPhone", "a.com"), {"title": None}], R) == []


def test_detect_dedupes_repeated_headlines_and_caps_kept_headlines():
    hs = [_h("War escalates again", "a.com")] * 5
    e = EV.detect(hs, R)[0]
    assert e["n_headlines"] == 1  # identical headlines count once
    many = [_h(f"Troops deployed, war grows {i}", f"o{i}.com") for i in range(10)]
    assert len(EV.detect(many, R)[0]["headlines"]) == R["event_detection"]["max_headlines_kept"]


# ------------------------------------------------------------------ pipeline helpers
def test_basket_close_and_beta():
    idx = pd.date_range("2026-01-01", periods=120)
    up = pd.Series(range(100, 220), index=idx, dtype=float)
    flat = pd.Series([100.0] * 120, index=idx)
    basket = PL.basket_close([up, flat])
    assert basket.iloc[0] == pytest.approx(100) and basket.iloc[-1] > 100
    assert PL.basket_close([up]) is None  # one series is not a basket
    wobble = pd.Series([100 + (i % 7) * 1.5 for i in range(120)], index=idx)
    assert PL.beta_vs(wobble * 2, wobble) == pytest.approx(1.0)  # scaling a price series does not change its returns
    amplified = 100 * (1 + 2 * wobble.pct_change().fillna(0)).cumprod()  # moves exactly twice as much each day
    assert PL.beta_vs(amplified, wobble) == pytest.approx(2.0, rel=0.02)
    assert PL.beta_vs(wobble, wobble) == pytest.approx(1.0)
    assert PL.beta_vs(wobble.head(10), wobble.head(10)) is None


def test_build_picks_ranks_filters_and_never_overlaps():
    idx = pd.date_range("2026-01-01", periods=120)
    mk = lambda drift, vol=2_000_000: pd.DataFrame({"close": [100 + i * drift for i in range(120)], "volume": [vol] * 120}, index=idx)  # noqa: E731
    names = ["A", "B", "C", "D", "E", "F", "G", "H", "THIN", "NODATA"]
    hist = {n: mk(0.1 * (i + 1)) for i, n in enumerate(names[:8])}
    hist["THIN"] = mk(0.5, vol=10)
    theme = {"id": "t", "members": names}
    snap = {"horizons": {"1M": {"score": 70.0}}}
    scores = {n: {"composite": 90 - 8 * i, "rating": "Buy", "news_score": 0.1, "name": n} for i, n in enumerate(names[:8])}
    bench = mk(0.05)["close"]
    p = PL.build_picks(theme, snap, hist, bench, scores, R)
    assert {x["reason"] for x in p["excluded"]} == {"below liquidity minimum", "no price data"}
    lead, lag = [x["ticker"] for x in p["leaders"]], [x["ticker"] for x in p["laggards"]]
    assert len(lead) == len(lag) == 4 and not set(lead) & set(lag)
    assert p["leaders"][0]["rank"] >= p["leaders"][-1]["rank"] >= p["laggards"][-1]["rank"]  # leaders best-first, laggards worst-first


# ------------------------------------------------------------------ storage + grading
@pytest.fixture()
def sqlite_store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PG", False)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_ready", False)
    return store


def test_predictions_are_logged_once_per_day_and_graded(sqlite_store):
    now = int(time.time())
    base = {"theme": "energy", "horizon": "1W", "made_at": now - 10 * 86400, "day": "2026-10-01", "label": "Up", "score": 70.0,
            "prob_up": 0.8, "confidence": "Medium", "baseline_label": "Flat", "bench": "XLE", "evaluate_at": now - 3 * 86400}
    store.log_prediction(base)
    store.log_prediction({**base, "score": 99.0})  # same theme/horizon/day: ignored
    store.log_prediction({**base, "horizon": "1M", "label": "Down", "baseline_label": "Down", "day": "2026-10-01", "evaluate_at": now + 86400})
    due = store.due_predictions(now)
    assert len(due) == 1 and due[0]["score"] == 70.0  # the 1M prediction has not matured

    store.save_outcome(due[0]["id"], 110.0, 101.0, 0.04, "Up", 1, 0)
    acc = store.accuracy()
    assert acc["overall"]["n"] == 1 and acc["overall"]["hitRate"] == 100.0 and acc["overall"]["baselineHitRate"] == 0.0
    assert acc["byHorizon"]["1W"]["directionalCalls"] == 1
    assert acc["byHorizon"]["1M"]["n"] == 0 and acc["pending"] == 1
    assert store.due_predictions(now) == []  # graded predictions are not re-graded


def test_events_news_and_snapshots_round_trip(sqlite_store):
    ev = {"id": "tariffs:2026-10-18", "type": "tariffs", "severity": "Med", "first_seen": 1, "last_seen": int(time.time()),
          "n_headlines": 2, "n_sources": 2, "headlines": [{"title": "t", "url": "u", "source": "s"}]}
    store.upsert_event(ev)
    store.upsert_event({**ev, "severity": "High"})
    got = store.recent_events()
    assert len(got) == 1 and got[0]["severity"] == "High" and got[0]["headlines"][0]["title"] == "t"

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    row = lambda tk: {"hash": PL._row_hash(tk, "Same headline"), "title": "Same headline", "url": "u", "source": "s", "time": now,  # noqa: E731
                      "sentiment": "Bullish", "impact": "High", "catalyst": "none", "reason": "r", "method": "lexicon", "ticker": tk}
    store.save_news([row("XLE"), row("XOM")])
    assert len(store.known_news_hashes([row("XLE")["hash"], "nope"])) == 1
    assert len(store.news_for(["XLE", "XOM"], "2000-01-01")) == 1  # one headline tagged to two tickers counts once

    run = store.start_run()
    store.save_snapshot(run, "energy", 100, {"theme": "energy", "horizons": {"1M": {"score": 60.0}}})
    store.save_snapshot(run, "energy", 200, {"theme": "energy", "horizons": {"1M": {"score": 65.0}}})
    assert store.latest_snapshot("energy")["asOf"] == 200
    assert [r["1M"] for r in store.score_history("energy")] == [60.0, 65.0]
    store.finish_run(run, "ok", {"themes": 1})
    assert store.last_runs(1)[0]["status"] == "ok"
