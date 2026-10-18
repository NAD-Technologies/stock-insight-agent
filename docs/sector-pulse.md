# Sector Pulse (Module B): implementation notes

Implements the first slice of Module B from *Market Intelligence Agent: Requirements* (rules-based, US markets, personal tool under NAD Technologies).

## What it does
A scheduled pipeline scores 26 sectors/themes (11 GICS + 15 custom) for **1W / 1M / 3M**, explains each call, lists leaders and laggards inside each, logs every prediction and later grades it against what happened.

| Requirement | Status |
|---|---|
| B1 news ingestion + tagging | Partial: Yahoo headlines for each theme ETF and its leading constituents, classified once and cached (LLM if a key is set, keyword fallback otherwise). Refresh every 4h, not 15 min. |
| B4 / B5 events + impact matrix | Done for war/sanctions/oil/rates/inflation/tariffs/regulation/recession/ceasefire. Detected from Yahoo macro headlines and GDELT; effect on each sector comes from `impact_matrix` in `rules.yaml`. |
| B6 price momentum | Done: return vs SPY, breadth, trend. Fund flows are a **dollar-volume proxy**, not true flows. |
| B7 score + direction | Done (Up/Flat/Down, probability, confidence). |
| B9 leaders / laggards | Done, using Module A composite + news + relative strength + beta. |
| B10 explain every call | Done: top 3 positive / negative drivers with source links. |
| B12 prediction tracking | Done: logged daily per theme/horizon, graded after the horizon, compared with the "last month continues" baseline. |
| A9 sector overlay | Done as a badge plus a warning when stock and sector disagree. It is **not** blended into the stock's composite score. |
| B2 earnings, B3 social, B11 chat, B13 briefings, B8 alerts, B14 rotation | Not in this slice. Missing factors are dropped, weights renormalised, confidence lowered and the gap shown. |

## Deliberate differences from the requirements document
1. **Absolute scores instead of cross-sector z-scores.** A z-score across sectors is always centred on the average sector, so about half would read "Up" even in a falling market. Each factor is instead mapped to 0-100 against the market (50 = neutral vs SPY), so Up means "expected to beat SPY".
2. **Direction bands are 60 / 40** (symmetric around 50) rather than 65 / 40. Both are in `rules.yaml`.
3. **Leaders and laggards never overlap.** With 8 constituents per theme that gives 4 + 4; lists grow to 5 + 5 once a theme has 10 or more.
4. **News shrinkage** (`news.shrink`) stops a single headline from swinging a sector.
5. **Probabilities are uncalibrated** until enough graded outcomes exist; the UI says so.

## Files
- `backend/sector_pulse/themes.yaml`: taxonomy (ETF + constituents). Edit freely.
- `backend/sector_pulse/rules.yaml`: weights, scales, bands, event keywords, impact matrix, half-lives.
- `scoring.py` (pure math, unit-tested), `events.py`, `pipeline.py`, `store.py`, `overlay.py`.
- `backend/api/sectors.py`: read-only endpoints (`/api/sectors`, `/api/sectors/{id}`, `/api/sectors/accuracy`, `/api/sectors/for/{ticker}`).
- `.github/workflows/sector-pulse.yml`: the schedule.

## Running it
```
cd backend
python -m sector_pulse run --budget 200     # first run: fills every stock ranking (slow)
python -m sector_pulse run                  # normal run (budget 40 stale/missing stocks)
python -m sector_pulse evaluate             # grade matured predictions
```
Needs `DATABASE_URL` for Postgres (otherwise a local SQLite file). On GitHub add the `DATABASE_URL` secret, then run the workflow once manually with budget 200.

## Honest limits
- Free news feeds do not provide point-in-time history, so news/event factors cannot be back-tested; they are validated forward through the logged predictions.
- Keyword sentiment is crude. Setting `NVIDIA_API_KEY` improves classification.
- Heuristics to review: the flow proxy, the event keywords (for example "ceasefire collapse" also matches the de-escalation list), and the impact-matrix values, which are judgement calls.
