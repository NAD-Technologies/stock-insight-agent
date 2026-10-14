"""Narrative generation with a grounding check: LLM text may only cite numbers present in the payload."""
from __future__ import annotations

import json
import re
from typing import Any

from . import llm

_NUM = re.compile(r"(?<![\w.])-?\$?\d[\d,]*\.?\d*")


def _collect(o: Any, acc: set[float]):
    if isinstance(o, bool) or o is None:
        return
    if isinstance(o, (int, float)):
        acc.add(float(o))
    elif isinstance(o, dict):
        for v in o.values():
            _collect(v, acc)
    elif isinstance(o, (list, tuple)):
        for v in o:
            _collect(v, acc)
    elif isinstance(o, str):
        for m in _NUM.findall(o):
            try:
                acc.add(float(m.replace("$", "").replace(",", "")))
            except ValueError:
                pass


def _close(x: float, known: set[float]) -> bool:
    for k in known:
        for scale in (1, 100, 0.01, 1e3, 1e-3, 1e6, 1e-6, 1e9, 1e-9, 1e12, 1e-12):
            v = k * scale
            tol = max(abs(x) * 0.006, 0.006)  # rounding tolerance (<0.6%)
            if abs(v - x) <= tol:
                return True
    return False


def ungrounded_numbers(text: str, payload: Any) -> list[str]:
    known: set[float] = set()
    _collect(payload, known)
    bad = []
    for m in _NUM.findall(text):
        raw = m.replace("$", "").replace(",", "")
        try:
            x = float(raw)
        except ValueError:
            continue
        if abs(x) < 32 and "." not in raw:  # small integers: counts, "3-month", days
            continue
        if 1990 <= x <= 2100 and "." not in raw:
            continue
        if not _close(x, known):
            bad.append(m)
    return bad


def _fmt(v, d=1, suffix=""):
    return "N/A" if v is None else f"{v:,.{d}f}{suffix}"


def template_narrative(p: dict) -> dict:
    """Deterministic fallback built only from the payload."""
    r, q = p["recommendation"], p["quote"]
    pos, neg = r["drivers"]["positive"], r["drivers"]["negative"]
    line = lambda d: f'{d["metric"]}: {d["value"]} ({d["pillar"]})'  # noqa: E731
    summary = (f'{q["name"]} ({p["ticker"]}) scores {_fmt(r["compositeScore"])}/100 on the {r["profile"]} profile, rated {r["rating"]} '
               f'with {r["confidence"]["level"].lower()} confidence. Pillar scores: ' +
               ", ".join(f'{k} {_fmt(v, 0)}' for k, v in r["pillarScores"].items()) + ".")
    risks = [f'Confidence reduced: {x}' for x in r["confidence"]["reasons"] if "complete and" not in x]
    for e in p["risk"].get("events", []):
        if e.get("risk"):
            risks.append(f'{e["type"]} in {e["daysAway"]} days ({e["date"]}).')
    st = p["risk"].get("stats") or {}
    if st.get("maxDrawdown") is not None:
        risks.append(f'1Y max drawdown {st["maxDrawdown"]}% and annualized volatility {st.get("volatility")}%.')
    return {"summary": summary, "bullCase": [line(d) for d in pos] or ["No strongly positive drivers identified."],
            "bearCase": [line(d) for d in neg] or ["No strongly negative drivers identified."],
            "keyRisks": risks or ["No specific risks flagged by the scoring engine."], "source": "template"}


async def synthesize(payload: dict, model: str) -> dict:
    slim = {k: payload[k] for k in ("ticker", "quote", "recommendation", "technical", "fundamental", "analyst", "sentiment", "risk")}
    # Drop bulky arrays the model does not need.
    slim = json.loads(json.dumps(slim, default=str))
    slim["technical"].pop("signals", None)
    slim["quote"].pop("summary", None)
    res = await llm.call_tool(
        model, llm.REPORT_TOOL,
        "Write the research narrative for this analysis. Every figure must come from the JSON below.\n<analysis_json>\n"
        + json.dumps(slim, default=str) + "\n</analysis_json>")
    if res:
        def _lst(v):  # open models sometimes return a string / newline-joined text instead of a list
            if isinstance(v, str):
                v = [x.strip("-• ") for x in v.splitlines() if x.strip()]
            return [str(x) for x in v] if isinstance(v, list) else []
        res = {"summary": str(res.get("summary", "")), **{k: _lst(res.get(k)) for k in ("bullCase", "bearCase", "keyRisks")}}
        if not res["summary"] or not (res["bullCase"] and res["bearCase"]):
            return template_narrative(payload)
        text = " ".join([res.get("summary", "")] + res.get("bullCase", []) + res.get("bearCase", []) + res.get("keyRisks", []))
        bad = ungrounded_numbers(text, slim)
        total = len(_NUM.findall(text)) or 1
        if len(bad) / total <= 0.15 and len(bad) <= 3:
            return {**{k: res[k] for k in ("summary", "bullCase", "bearCase", "keyRisks")}, "source": "llm"}
        out = template_narrative(payload)
        out["note"] = f"LLM narrative rejected: {len(bad)} figure(s) not found in data ({', '.join(bad[:5])})."
        return out
    return template_narrative(payload)
