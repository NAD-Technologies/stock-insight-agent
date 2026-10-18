"""Agent registry and the message bus used by the pipeline.

The "agents" are specialised workers in the Sector Pulse pipeline. They do not chat in free text: each hands the next one a
small, structured message (a topic, a summary and a payload sample). The bus records every handoff so the dashboard can show
who talked to whom, with what, and how long it took.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from . import store

log = logging.getLogger("sector_pulse.bus")

# kind: control | collector | llm | engine | quant | publisher
AGENTS: list[dict] = [
    {"id": "scheduler", "name": "Orchestrator", "kind": "control", "tech": "Python, GitHub Actions cron",
     "role": "Starts each run, sets the plan and budget, and hands tasks to the other agents. Never scores anything itself."},
    {"id": "price_agent", "name": "Market Data Agent", "kind": "collector", "tech": "yfinance",
     "role": "Downloads one year of daily prices for SPY, every theme ETF and every constituent."},
    {"id": "news_agent", "name": "News Collector", "kind": "collector", "tech": "Yahoo Finance news",
     "role": "Fetches recent headlines for each theme's ETF and leading constituents and de-duplicates against the cache."},
    {"id": "sentiment_agent", "name": "Sentiment Classifier", "kind": "llm", "tech": "LLM (NVIDIA NIM / Claude) with keyword fallback",
     "role": "Reads each new headline once and tags it Bullish/Neutral/Bearish with an impact level. Output is validated JSON."},
    {"id": "event_agent", "name": "Event Detector", "kind": "collector", "tech": "GDELT + Yahoo macro news, keyword rules",
     "role": "Spots war, sanctions, oil, rate and tariff stories and rates their severity by how many outlets report them."},
    {"id": "stock_agent", "name": "Stock Analyst (Module A)", "kind": "engine", "tech": "Module A engine: 5 pillars",
     "role": "Runs the full single-stock analysis (technical, fundamental, analyst, sentiment, risk) and stores the composite score."},
    {"id": "quant_agent", "name": "Quant Scorer", "kind": "quant", "tech": "Deterministic Python (no LLM)",
     "role": "Turns prices, news, events and flows into factor scores, then a 0-100 sector score, direction and confidence per horizon."},
    {"id": "picker_agent", "name": "Stock Picker", "kind": "quant", "tech": "Deterministic Python",
     "role": "Ranks each theme's constituents (stock score, news, relative strength, beta) into leaders and laggards."},
    {"id": "publisher_agent", "name": "Publisher", "kind": "publisher", "tech": "Postgres (Neon)",
     "role": "Writes the snapshots, logs predictions and records outcomes. The web app only reads what it publishes."},
    {"id": "evaluator_agent", "name": "Evaluator", "kind": "quant", "tech": "Deterministic Python",
     "role": "Grades past predictions against what the sector actually did versus SPY and compares with a naive baseline."},
]
AGENT_IDS = {a["id"] for a in AGENTS}


class Bus:
    """Records agent-to-agent messages for one pipeline run. Logging must never break the pipeline."""

    def __init__(self, run_id: int):
        self.run_id = run_id
        self.seq = 0

    def send(self, sender: str, receiver: str, topic: str, summary: str, items: Optional[int] = None,
             sample: Any = None, status: str = "ok", ms: Optional[int] = None) -> None:
        self.seq += 1
        try:
            blob = json.dumps(sample, default=str)[:700] if sample is not None else None
            store.save_message(self.run_id, self.seq, int(time.time() * 1000), sender, receiver, topic, summary[:300], items, ms, status, blob)
        except Exception as e:  # noqa: BLE001
            log.warning("could not log message %s->%s: %s", sender, receiver, e)


def ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
