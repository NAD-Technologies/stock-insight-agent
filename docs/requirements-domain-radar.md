# Domain Radar: Requirements (draft v0.1)

**Product:** Stock Insight by NAD Technologies
**Feature:** Domain Radar, a sector and theme outlook with stock picks inside each domain
**Status:** Requirements for review. No implementation yet.

---

## 1. Purpose

Today Stock Insight analyses **one ticker at a time**. Users also ask a higher-level question: *"Which parts of the market are doing well right now, which are about to turn, and which stocks inside those areas are worth a look?"*

Domain Radar answers that. It continuously collects news, earnings, macro/geopolitical events and social signals; scores each **domain** (Blue chip, Health care, Oil & gas, Nuclear, Education, Space & defence, and so on); predicts whether each is heading **up, down or sideways** over defined horizons; explains **why** with cited evidence; and then surfaces the best-ranked **tickers inside each domain** using the existing per-stock engine.

### Goals
1. Give a clear, explainable outlook (Up / Neutral / Down + confidence) for every tracked domain.
2. React to real-world events (war, sanctions, regulation, earnings season, commodity moves) and show their domain-level impact.
3. Drill from domain to tickers, reusing the existing Buy/Hold/Sell composite score.
4. Be **cheap enough to run on free tiers** and **auditable** (every claim traceable to a source; every prediction scored against what actually happened).

### Non-goals (v1)
- Not trading signals, order placement or portfolio advice. Educational analysis only, as today.
- No real-time (sub-minute) updates. Data refreshes on a schedule.
- No attempt to predict individual-stock earnings surprises.
- Not an "LLM guesses the market" feature. The LLM reads and structures text; **all scoring math is done in code.**

---

## 2. Guiding principles

| Principle | What it means |
|---|---|
| **Compute offline, serve cached** | A scheduled pipeline does the heavy work and stores results. User requests only read the latest snapshot. Nothing expensive runs per page view. |
| **LLM reads, code calculates** | LLMs extract entities, sentiment, event type and impact direction from text into structured JSON. Scores, weights, z-scores and aggregation are deterministic code. This makes results reproducible and testable. |
| **Evidence or it didn't happen** | Every domain outlook links to the specific articles, filings and data points behind it. |
| **Honest uncertainty** | Every prediction has a confidence, and confidence is lowered when data is thin or signals disagree (as the stock engine already does). |
| **Measure ourselves** | Every prediction is stored and later compared with realised returns. Hit rate is shown, not hidden. |
| **Graceful degradation** | If the LLM or a data source is down, fall back to lexicon sentiment and price-only signals, as the stock engine already does. |

---

## 3. Domains

### 3.1 Initial taxonomy (config-driven, editable without code changes)

| Domain | Price proxy (benchmark) | Example constituents (to be curated) |
|---|---|---|
| Blue chip / large cap | DIA, SPY; India: NIFTY 50 | AAPL, MSFT, JNJ, KO; India: RELIANCE.NS, TCS.NS, HDFCBANK.NS |
| Health care & pharma | XLV, IBB; India: NIFTY Pharma | JNJ, LLY, PFE; India: SUNPHARMA.NS |
| Oil, gas & energy | XLE, XOP; India: NIFTY Energy | XOM, CVX; India: ONGC.NS, RELIANCE.NS |
| Nuclear & uranium | URA, NLR | CCJ, UEC, LEU; India: NTPC.NS (partial) |
| Education | no clean ETF: use an equal-weight basket | CHGG, COUR, DUOL, LRN |
| Space & defence | ITA, ARKX, UFO | LMT, RTX, RKLB; India: HAL.NS, BEL.NS |
| Technology / AI & semiconductors | XLK, SMH; India: NIFTY IT | NVDA, AMD; India: INFY.NS |
| Financials / banks | XLF; India: NIFTY Bank | JPM; India: HDFCBANK.NS |
| (extensible) Gold & metals, EV & clean energy, Real estate, Consumer, Shipping and more | | |

- The taxonomy lives in a YAML file (like `config.yaml`): domain id, display name, benchmark symbols, constituent tickers, keywords and synonyms used to route news, and region tags (US, India, Global).
- **Domain membership rules:** a ticker may belong to several domains. Weights are optional.
- **Dynamic discovery (v2):** the system proposes new domains or constituents when a recurring theme shows up in news and no domain covers it (human approves).

### 3.2 Scope of markets
US and India first, because the app already supports both (including ₹ display). Region tag is a filter, so each domain can show US, India or Global constituents.

---

## 4. Functional requirements

### FR-1 Data ingestion (scheduled)

Collect, normalise, de-duplicate and store raw items with source, timestamp, URL, domain tags and region.

| Signal | Candidate sources (free first) | Notes |
|---|---|---|
| **News** | Yahoo Finance news (already integrated), GDELT (free global events/news), Finnhub / Alpha Vantage news (optional keys), RSS from Reuters, Google News queries, Indian sources (Economic Times, Moneycontrol RSS) | De-duplicate near-identical headlines. Keep the publisher for credibility weighting. |
| **Earnings and fundamentals** | yfinance earnings dates and surprises, SEC EDGAR filings (8-K, 10-Q) | Beat/miss rate, guidance changes and revenue growth rolled up by domain. |
| **Geopolitical / macro events** | GDELT events, news classified as war, sanctions, tariffs, regulation, elections, supply disruption; FRED (rates, CPI) and EIA (oil inventories) if keys are available | Event to affected-domain mapping (see FR-4). |
| **Market data** | Price history of domain benchmarks and constituents (already integrated), VIX, 10Y yield | Momentum, breadth, relative strength vs SPY or Nifty, volume. |
| **Social / attention** | Reddit (subreddit mention counts), StockTwits (public streams), Google Trends, Wikipedia page views | See risk R-3: X/Twitter is paid and fragile; treat as optional. Social is a **minor, capped** signal. |

Requirements:
- Each source sits behind an adapter with a common interface (see §6) and a per-source health flag. One failing source must not stop a run.
- Respect rate limits, robots/ToS and caching. Store raw text only as long as needed (retention policy in §8).
- Every item gets a content hash for de-duplication.

### FR-2 Understanding (LLM extraction into structured signals)

For each new item, an LLM call returns strict JSON (validated; retry then fall back to lexicon):

```json
{
  "domains": ["oil_gas", "space_defence"],
  "entities": ["XOM", "Russia"],
  "event_type": "war | sanctions | earnings | regulation | supply | demand | macro | product | other",
  "direction": "bullish | bearish | neutral",
  "impact": 1,
  "horizon": "days | weeks | months",
  "novelty": 0.0,
  "confidence": 0.0,
  "rationale": "one sentence, quoting the source"
}
```

- `impact` is 1 to 5 and `novelty` discounts repeated or stale stories.
- Batch items per call to control cost. Cache by content hash so the same item is never classified twice.
- Prompts are versioned. Outputs are validated against a schema; invalid output is rejected, not guessed at.

### FR-3 Domain scoring (deterministic math)

For each domain and each horizon (**1 to 4 weeks, 1 to 3 months, 6 to 12 months**) compute component scores, each normalised to 0 to 100 (z-score against its own history or a peer set):

| Component | Inputs |
|---|---|
| **Price momentum** | Benchmark / basket returns (1w, 1m, 3m, 6m), relative strength vs market, trend (moving averages), breadth (% of constituents above their 50-day average) |
| **News sentiment** | Time-decayed, impact-weighted, credibility-weighted sentiment of domain-tagged items; volume-of-news change vs baseline |
| **Earnings** | Share of constituents beating estimates, average surprise, guidance raises vs cuts, revenue growth |
| **Event impact** | Sum of active events' directional impact on this domain, decaying over time (war, sanctions, regulation, supply shocks) |
| **Social / attention** | Mention-volume z-score and sentiment, **capped at a small weight** |
| **Macro fit** | Rate, inflation and commodity sensitivity of the domain vs current macro regime |
| **Risk / volatility** | Domain volatility, drawdown, dispersion across constituents |

- **Composite domain score** = weighted sum of components, weights **per horizon and configurable** in YAML (same pattern as `profiles` and `horizons` in `config.yaml`). Short horizon leans on momentum and events; long horizon leans on earnings and macro.
- **Outlook label:** Strong Up / Up / Neutral / Down / Strong Down from score bands (configurable).
- **Confidence:** reduced by thin data, stale data, disagreement between components, and low LLM extraction confidence, mirroring the stock engine's confidence logic.
- **Predicted direction** is expressed as a probability or score plus a label, **not** a price target.
- All formulas, weights and thresholds are documented and unit-tested. No LLM is used for arithmetic.

### FR-4 Event to domain impact mapping (war, sanctions and similar)

- Maintain an **event-impact matrix** (YAML, human-reviewed): event type x domain -> expected direction and typical magnitude (for example, regional conflict -> defence up, energy up, airlines down, broad market down; new tariffs -> importers down, domestic producers up).
- The LLM proposes affected domains for a specific event. The matrix and the LLM proposal are reconciled: the matrix is the prior, the LLM refines. Disagreements are flagged for human review.
- Active events show on the dashboard as **"Events driving the market"** with affected domains, start date and decay.

### FR-5 Outlook generation and explanation

For each domain, produce:
- Outlook label, score, confidence and horizon.
- **Top drivers** (3 to 5 bullets), each with a link to its evidence.
- **Counter-signals** (what argues against the call).
- **Key risks and upcoming catalysts** (earnings dates, central bank meetings, scheduled events).
- A short LLM-written narrative, **generated only from the structured inputs and cited items**, with a post-check that every number in the text exists in the inputs (the stock narrative module already does this).

### FR-6 Stock picks inside a domain

- For each domain, rank constituents using the **existing per-stock composite score** (technical, fundamental, analyst, sentiment, risk) plus a **domain tailwind adjustment** (an up-trending domain lifts its constituents' rank; a down-trending one lowers it).
- Show top N picks and bottom N "avoid" names with rating, score, ₹ or $ price (correct currency), 3-month sparkline and one-line reason.
- Filters: region (US / India / Global), market cap, risk profile (Balanced / Trader / Investor, reusing the existing profiles).
- Clicking a pick opens the existing stock analysis page.

### FR-7 User experience

- **Domain Radar page:** heatmap or grid of domains with outlook label, score, 1-week change in score, and a trend arrow. Sort and filter by horizon and region.
- **Domain detail page:** outlook, drivers with source links, event timeline, benchmark chart with overlaid key events, constituent table and top picks.
- **"Events driving the market"** panel on the Radar.
- **Personalisation (signed-in users):** follow domains, "My domains" strip on My view, a change feed ("Nuclear moved from Neutral to Up since you last visited"). Alerts are phase 3.
- **Guests:** see the Radar and domain summaries (generic info). Following domains and the change feed require login, consistent with the current guest and login model.
- Every page shows "as of <timestamp>", data freshness, the prediction horizon and the disclaimer.

### FR-8 Prediction tracking and evaluation (accountability)

- Persist every prediction snapshot: domain, horizon, label, score, confidence, inputs hash, model and prompt versions.
- After each horizon elapses, compute the **realised return** of the domain benchmark versus the market and record whether the call was correct.
- Publish on an "Accuracy" panel: hit rate by horizon and domain, calibration (do 70%-confidence calls win about 70% of the time?), and a comparison against naive baselines (momentum-only, random).
- Use this to tune weights offline. Weight changes are versioned and never silently applied.

### FR-9 Admin and operations

- Admin page additions: last run time and status per pipeline stage, per-source health, item counts, LLM calls and estimated cost, failures, accuracy trend.
- Manual controls: re-run a domain, mute a noisy source, edit the taxonomy and event matrix (initially via config and PR; UI later).
- Alerting (email or log) when a run fails or a source has been down for more than 24 hours.

---

## 5. Prediction methodology (summary)

1. Gather signals per domain and normalise each to a 0 to 100 score against its own history.
2. Blend with horizon-specific weights into a composite.
3. Adjust confidence for data quality and signal agreement.
4. Convert to Up / Neutral / Down.
5. Store it, then score it against reality later (FR-8).

**Honesty about limits:** markets are noisy. v1 aims to be a **well-organised, explainable, measured** view of momentum and events, not a promise of accuracy. If the tracked hit rate does not beat baselines, the UI says so and the weights are revisited rather than the claim being dressed up.

---

## 6. Architecture options

### 6.1 Recommended: staged pipeline with agents, scheduled, results cached

```
Scheduler (GitHub Actions cron, every 3-6h)  ->  Pipeline run
  1. Ingest agents      -> raw items (news, filings, social, prices)
  2. Extraction agent   -> structured signals (LLM -> validated JSON)
  3. Retrieval (RAG)    -> relevant, de-duplicated evidence per domain
  4. Domain analyst     -> one analyst per domain (supervised, parallel)
  5. Quant scorer       -> deterministic scoring and confidence (code)
  6. Picker             -> ranks tickers with existing stock engine
  7. Narrator           -> cited summary, number-checked
  8. Publisher          -> writes snapshot + predictions to Postgres
API (FastAPI, existing)  -> reads latest snapshot  ->  React UI
Evaluator (daily cron)   -> scores past predictions vs realised returns
```

| Component | Choice | Why |
|---|---|---|
| **Orchestration** | A **supervisor agent** coordinating specialist agents ("agents of agents"): News, Earnings, Geopolitics, Social, Quant, and one Domain Analyst per domain | Specialists have narrow prompts and tools, which is easier to test and cheaper to run. The supervisor merges results and resolves conflicts. A plain Python pipeline first, with an agent framework (LangGraph or the Claude Agent SDK) only where branching or tool-use truly helps. |
| **RAG** | Postgres with **pgvector** on the same Neon database already in use. Embeddings from a hosted API (NVIDIA NIM embedding endpoint or similar) | No new infrastructure, free tier, and no heavy model in the 512 MB web service. Retrieval is filtered by domain, region and recency, with time-decay. Citations come from retrieved item IDs. |
| **MCP** | Wrap data tools (news search, filings lookup, market data, domain scores) as **MCP servers** so any agent or client can call them uniformly | Useful for reuse (for example, Claude Desktop or other agents querying the same tools), but **optional for v1**. Adapters with a common interface give the same benefit with less moving parts. Revisit in phase 2. |
| **LLM** | Provider-agnostic wrapper (already present in `llm.py`: Anthropic, NVIDIA NIM, OpenAI-compatible). Cheap model for bulk extraction, stronger model for the narrator and conflict resolution | Controls cost. Free NVIDIA NIM tier is the default. |
| **Compute location** | The **pipeline runs outside the web service** (GitHub Actions cron or a similar free scheduler) and writes to Postgres. The web service only reads. | Render's free instance sleeps and has 512 MB RAM and ephemeral disk. Batch work there would be slow, fragile and would block users. |
| **Storage** | Neon Postgres: raw items, extracted signals, embeddings, domain snapshots, predictions, evaluation results | Persistent, free, already integrated. |

### 6.2 Alternatives considered

- **Single "ask the LLM what's hot" call per request:** simplest, but slow, costly, non-reproducible, hallucination-prone and untestable. Rejected.
- **Heavy streaming stack (Kafka, Spark):** unnecessary at this scale. Rejected.
- **Fully agentic with free-form tool use everywhere:** flexible but harder to bound cost and verify. Use agents for reading and reasoning steps; keep scoring deterministic.

---

## 7. Data model (sketch)

| Table | Key fields |
|---|---|
| `domains` | id, name, region tags, benchmark symbols, keywords (from YAML) |
| `domain_members` | domain_id, ticker, weight |
| `raw_items` | id, source, url, published_at, title, text, hash, region, fetched_at |
| `item_signals` | item_id, domains[], entities[], event_type, direction, impact, novelty, confidence, model_version, prompt_version |
| `item_embeddings` | item_id, vector |
| `events` | id, type, region, start, affected_domains, direction, magnitude, decay, status |
| `domain_snapshots` | domain_id, as_of, horizon, component_scores (JSON), composite, label, confidence, drivers (JSON), narrative, versions |
| `domain_picks` | snapshot_id, ticker, rank, composite, domain_adjustment, reason |
| `predictions` | domain_id, horizon, made_at, label, score, confidence, evaluate_at, realised_return, hit |
| `pipeline_runs` | id, started, finished, stage statuses, item counts, LLM calls, cost estimate |

Existing tables (users, ticker views, feedback, activity) are unchanged. New: `user_followed_domains`.

---

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| **Cost** | Runs within free tiers (Neon, GitHub Actions, NVIDIA NIM free, Render free). Hard daily cap on LLM calls and tokens. Estimated cost shown in the admin page. |
| **Latency** | Radar and domain pages load from cached snapshots in under 2 s (excluding cold start of the free host). |
| **Freshness** | Snapshots refresh every 3 to 6 hours (configurable). Each domain shows its data age. Stale (over 24 h) snapshots are visibly flagged. |
| **Reliability** | Pipeline stages are idempotent and resumable. A failed source or stage degrades only its own signals. The previous good snapshot stays live until a new one is validated. |
| **Reproducibility** | Same inputs plus same versions give the same scores. Prompts, models and weights are versioned and stored with each snapshot. |
| **Security and privacy** | Secrets only in environment variables. Admin endpoints stay admin-only. No user data is sent to LLMs. Only public content is processed. |
| **Compliance** | Respect each source's ToS and rate limits. Store excerpts and links, not full copyrighted articles, beyond a short retention window (for example, 30 days for raw text; derived signals kept longer). Prominent "not financial advice" disclaimer. |
| **Testing** | Unit tests for scoring math and normalisation. Golden-file tests for extraction (fixed articles -> expected JSON shape). Replay tests that re-run a past date range. Mock adapters so tests never hit the network. |
| **Observability** | Structured logs per run and stage, source health and a pipeline-run history in the admin page. |
| **Accessibility and design** | Same design system as the app: light and dark themes, ₹ and $ aware formatting, colour never the only signal (arrows and labels as well). |

---

## 9. Phased delivery

**Phase 1: MVP (prove value cheaply)**
- Domain taxonomy (about 8 domains, US and India) in YAML.
- Market-data-only scoring (momentum, breadth, relative strength) plus Yahoo news sentiment using the existing classifier.
- Scheduled pipeline writing snapshots to Postgres, with a Radar page, domain detail page and top picks via the existing stock engine.
- Prediction logging begins immediately (so accuracy history accrues from day one).

**Phase 2: Intelligence**
- GDELT and RSS ingestion, LLM extraction, event matrix with war and sanctions handling.
- RAG with pgvector, cited drivers and narrative with number-checking.
- Earnings aggregation, following domains, change feed, Accuracy panel.

**Phase 3: Depth**
- Social signals (Reddit, StockTwits, Google Trends), alerts, MCP tool servers, dynamic domain discovery, weight tuning from evaluation data, admin editing of taxonomy.

---

## 10. Acceptance criteria (MVP)

1. The Radar lists at least 8 domains with outlook label, score, confidence and as-of time, loading from cache in under 2 s.
2. Each domain detail page shows at least 3 drivers, each linked to a real source item or data point.
3. A simulated "war" event fed into the event matrix visibly raises Space & defence and Oil & gas, and lowers the broad market and airlines, with an explanation.
4. Top picks per domain use the existing composite score and show the correct currency (₹ for Indian tickers).
5. Disabling the LLM still produces a (lexicon-based, lower-confidence) snapshot with a visible "degraded" flag.
6. Every snapshot writes prediction records. A nightly job fills in realised outcomes for expired ones.
7. The scoring module has unit-test coverage for normalisation, weighting, confidence and band assignment.
8. A failed source or LLM outage never produces a blank page; the last good snapshot is shown with its age.

---

## 11. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R-1 | **Hallucination or biased LLM reads** | Strict JSON schema, rationale quoting the source, number-checking, lexicon cross-check, confidence discount on disagreement |
| R-2 | **Low predictive accuracy** (markets are efficient and noisy) | Honest framing, accuracy tracking against baselines, no price targets, emphasis on explaining drivers |
| R-3 | **Social data access** (X/Twitter is paid; Reddit and others limit access) | Social is optional and capped; start with Google Trends, Reddit and StockTwits; design adapters so sources can be swapped |
| R-4 | **Free-tier limits** (LLM quotas, GitHub Actions minutes, Neon storage) | Batch calls, cache by hash, hard caps, retention limits, cost panel; measure before expanding |
| R-5 | **News licensing / ToS** | Use APIs and RSS as permitted, store excerpts and links, short retention |
| R-6 | **Over-reaction to one loud headline** | Novelty decay, de-duplication, source credibility weighting, impact capped per item |
| R-7 | **Look-ahead bias in evaluation** | Evaluate only with data available at prediction time (timestamps on everything) |
| R-8 | **Regulatory perception** (looks like advice) | Disclaimers on every page, educational framing, no "buy this now" language |
| R-9 | **Domain definition disputes** (is a stock "nuclear"?) | Transparent membership in YAML, multi-domain membership, easy to edit |

---

## 12. Open questions for decision

1. **Markets:** US and India only for v1, or add other regions?
2. **Horizon emphasis:** which matters most to your users: weeks (trader) or months to years (investor)?
3. **Budget:** is it strictly free-tier, or is a small monthly budget acceptable (for example, for a better news API or a stronger LLM)?
4. **Social media:** is X/Twitter essential (paid), or are Reddit, StockTwits and Google Trends acceptable?
5. **Domain list:** confirm the starter domains, and add any specific ones (for example, EV, gold, banks, shipping, agriculture, India IT or PSU).
6. **Where picks should come from:** curated constituent lists only, or also auto-screened from a wider universe?
7. **Alerts:** email, in-app, or both, and is it phase 2 or 3?
8. **Public vs login:** should the Radar be fully public (guests included) or partly gated to drive sign-ups?
9. **Hosting of the pipeline:** is GitHub Actions cron acceptable as the scheduler, or do you want a dedicated worker later?
