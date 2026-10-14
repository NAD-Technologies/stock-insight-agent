"""Run the real API in-process for a list of tickers and save the JSON under docs/demo/.

    python scripts/demo.py AAPL NVDA TSLA
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "demo"
OUT.mkdir(parents=True, exist_ok=True)

with TestClient(app) as c:
    for t in sys.argv[1:] or ["AAPL", "NVDA", "TSLA"]:
        r = c.get(f"/api/analyze/{t}")
        print(t, r.status_code, f"{len(r.content) // 1024} KB")
        if r.status_code != 200:
            print("  ", r.text[:200])
            continue
        d = r.json()
        (OUT / f"{t}.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
        rec = d["recommendation"]
        (OUT / f"{t}.summary.json").write_text(json.dumps({
            "ticker": d["ticker"], "asOf": d["asOf"], "price": d["quote"]["price"], "rating": rec["rating"],
            "compositeScore": rec["compositeScore"], "confidence": rec["confidence"], "pillarScores": rec["pillarScores"],
            "horizons": rec["horizons"], "tradePlan": rec["tradePlan"], "drivers": rec["drivers"],
            "narrative": d["narrative"], "failedTools": [s for s in d["agentTrace"] if not s["ok"]]}, indent=1), encoding="utf-8")
        print(f'  {rec["rating"]} {rec["compositeScore"]} conf={rec["confidence"]["level"]} pillars={rec["pillarScores"]}')
