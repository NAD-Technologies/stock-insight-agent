import { Logo } from "./Logo";
import { useEffect, useRef, useState } from "react";
import { search } from "../api";
import { Badge, Card, Gauge } from "./ui";
import { ago, big, fmtMetric, num, pct, ratioPct, ratingColor, usd } from "../lib/format";

export function Header({ onSelect, profile, setProfile, onRefresh, asOf, watchlist, current, toggleWatch, dark, toggleDark, view, setView, session, onSignOut, onFeedback }: any) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<any>();

  useEffect(() => {
    clearTimeout(timer.current);
    if (q.trim().length < 1) { setRes([]); return; }
    timer.current = setTimeout(() => search(q).then((r) => setRes(r.results || [])).catch(() => setRes([])), 250);
  }, [q]);

  const go = (t: string) => { onSelect(t.toUpperCase()); setQ(""); setOpen(false); };
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <Logo size={34} />
          <span className="hidden h-8 w-px bg-line sm:block" />
          <span className="text-lg font-bold">Stock Insight</span>
        </div>
        <div className="relative min-w-[220px] flex-1 sm:max-w-sm">
          <input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
            onKeyDown={(e) => e.key === "Enter" && q.trim() && go(q.trim())}
            placeholder="Search ticker or company (AAPL, RELIANCE.NS…)"
            className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm outline-none focus:border-fg" />
          {open && res.length > 0 && (
            <ul className="absolute mt-1 max-h-72 w-full overflow-auto rounded-lg border border-line bg-card shadow-lg">
              {res.map((r) => (
                <li key={r.symbol} onMouseDown={() => go(r.symbol)} className="flex cursor-pointer justify-between px-3 py-2 text-sm hover:bg-line">
                  <span><b>{r.symbol}</b> <span className="text-mute">{r.name}</span></span>
                  <span className="text-xs text-mute">{r.exchange}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <select value={profile} onChange={(e) => setProfile(e.target.value)} className="rounded-lg border border-line bg-card px-2 py-2 text-sm">
          <option value="balanced">Balanced</option>
          <option value="trader">Short-term trader</option>
          <option value="investor">Long-term investor</option>
        </select>
        <button onClick={() => setView(view === "compare" ? "analyze" : "compare")} className="rounded-lg border border-line px-3 py-2 text-sm">
          {view === "compare" ? "Analyze" : "Compare"}
        </button>
        <button onClick={() => setView(view === "pulse" || view === "sector" ? "analyze" : "pulse")} className={`rounded-lg border px-3 py-2 text-sm ${view === "pulse" || view === "sector" ? "border-fg" : "border-line"}`}>Market Pulse</button>
        <button onClick={() => setView(view === "me" ? "analyze" : "me")} className={`rounded-lg border px-3 py-2 text-sm ${view === "me" ? "border-fg" : "border-line"}`}>My view</button>
        {session?.mode === "google" && session.user.isAdmin && (
          <button onClick={() => setView(view === "admin" ? "analyze" : "admin")} className={`rounded-lg border px-3 py-2 text-sm ${view === "admin" ? "border-fg" : "border-line"}`}>Admin</button>
        )}
        <button onClick={onFeedback} className="rounded-lg border border-line px-3 py-2 text-sm">Feedback</button>
        <button onClick={onRefresh} className="rounded-lg border border-line px-3 py-2 text-sm">↻ Refresh</button>
        <button onClick={toggleDark} className="rounded-lg border border-line px-3 py-2 text-sm">{dark ? "☀" : "🌙"}</button>
        {asOf && <span className="text-xs text-mute">Updated {ago(asOf)}</span>}
        {session && (
          <div className="ml-auto flex items-center gap-2 text-sm">
            {session.mode === "google" ? (
              <>
                {session.user.picture && <img src={session.user.picture} alt="" referrerPolicy="no-referrer" className="h-7 w-7 rounded-full" />}
                <span className="hidden max-w-[140px] truncate sm:inline" title={session.user.email}>{session.user.name}</span>
                <button onClick={onSignOut} className="rounded-lg border border-line px-3 py-2 text-sm">Sign out</button>
              </>
            ) : (
              <>
                <span className="text-xs text-mute">Guest</span>
                <button onClick={onSignOut} className="rounded-lg border border-line px-3 py-2 text-sm">Log in</button>
              </>
            )}
          </div>
        )}
      </div>
      <div className="mx-auto flex max-w-7xl items-center gap-2 overflow-x-auto px-4 pb-2 text-sm">
        <span className="text-xs text-mute">Watchlist</span>
        {watchlist.map((t: string) => (
          <button key={t} onClick={() => onSelect(t)} className={`rounded-full border px-2 py-0.5 text-xs ${t === current ? "border-fg" : "border-line text-mute"}`}>{t}</button>
        ))}
        {current && (
          <button onClick={toggleWatch} className="rounded-full px-2 py-0.5 text-xs text-mute hover:text-fg">
            {watchlist.includes(current) ? "★ remove" : "☆ add " + current}
          </button>
        )}
      </div>
    </header>
  );
}

const STATE: Record<string, string> = { REGULAR: "Market open", PRE: "Pre-market", PREPRE: "Pre-market", POST: "After hours", POSTPOST: "After hours", CLOSED: "Market closed" };

export function Hero({ d }: { d: any }) {
  const q = d.quote;
  const up = (q.change ?? 0) >= 0;
  const col = up ? "#16a34a" : "#dc2626";
  const range = q.fiftyTwoWeekHigh - q.fiftyTwoWeekLow;
  const pos = range > 0 ? Math.min(100, Math.max(0, ((q.price - q.fiftyTwoWeekLow) / range) * 100)) : 0;
  const earn = (d.risk?.events || []).find((e: any) => e.type === "Earnings");
  const stats: [string, string][] = [
    ["Mkt Cap", big(q.marketCap)], ["P/E", num(q.pe)], ["Volume vs Avg", q.volumeVsAvg ? `${num(q.volumeVsAvg)}x` : "N/A"],
    ["Beta", num(q.beta)], ["Div Yield", q.dividendYield ? ratioPct(q.dividendYield) : "N/A"],
    ["Next Earnings", earn ? `${earn.date} (${earn.daysAway}d)` : "N/A"],
  ];
  return (
    <Card>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">{d.company}</h1>
            <span className="text-mute">{d.ticker}</span>
          </div>
          <div className="text-xs text-mute">{q.exchange} · {q.sector}{q.industry ? ` · ${q.industry}` : ""} · {STATE[q.marketState] || q.marketState}</div>
        </div>
        <div className="text-right">
          <div className="num text-4xl font-bold">{usd(q.price)} <span className="text-sm text-mute">{q.currency}</span></div>
          <div className="num font-semibold" style={{ color: col }}>{up ? "▲" : "▼"} {num(Math.abs(q.change))} ({pct(q.changePct)})</div>
          {q.postMarketPrice && <div className="text-xs text-mute">After hours {usd(q.postMarketPrice)}</div>}
          {q.preMarketPrice && <div className="text-xs text-mute">Pre-market {usd(q.preMarketPrice)}</div>}
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {stats.map(([k, v]) => (
          <div key={k}><div className="text-xs text-mute">{k}</div><div className="num text-sm font-semibold">{v}</div></div>
        ))}
        <div className="col-span-2">
          <div className="text-xs text-mute">52w range</div>
          <div className="relative mt-2 h-1.5 rounded bg-line">
            <div className="absolute -top-1 h-3.5 w-1 rounded bg-fg" style={{ left: `${pos}%` }} />
          </div>
          <div className="num mt-1 flex justify-between text-xs text-mute"><span>{num(q.fiftyTwoWeekLow)}</span><span>{num(q.fiftyTwoWeekHigh)}</span></div>
        </div>
      </div>
      {q.summary && <p className="mt-3 line-clamp-2 text-sm text-mute">{q.summary}</p>}
    </Card>
  );
}

export function Verdict({ d }: { d: any }) {
  const r = d.recommendation;
  const tp = r.tradePlan || {};
  const col = ratingColor(r.rating);
  const conf = r.confidence?.level;
  return (
    <Card className="border-2" >
      <div className="grid gap-6 md:grid-cols-[260px_1fr]">
        <div className="flex flex-col items-center">
          <span className="rounded-lg px-4 py-2 text-2xl font-extrabold" style={{ background: col + "26", color: col }}>{r.rating.toUpperCase()}</span>
          <Gauge value={r.compositeScore} label={`Composite · ${r.profile}`} color={col} />
          <span className="rounded-full border border-line px-3 py-1 text-xs" title={(r.confidence?.reasons || []).join("; ")}>
            Confidence: <b>{conf}</b>
          </span>
          <div className="mt-1 max-w-[240px] text-center text-xs text-mute">{(r.confidence?.reasons || []).join("; ")}</div>
        </div>
        <div>
          <div className="mb-4 grid grid-cols-3 gap-2">
            {(["short", "medium", "long"] as const).map((h) => (
              <div key={h} className="rounded-lg border border-line p-2 text-center">
                <div className="text-xs text-mute">{h === "short" ? "Short (1–4w)" : h === "medium" ? "Medium (3–6m)" : "Long (1y+)"}</div>
                <div className="text-sm font-bold" style={{ color: ratingColor(r.horizons[h].rating) }}>{r.horizons[h].rating}</div>
                <div className="num text-xs text-mute">{num(r.horizons[h].score, 0)}/100</div>
              </div>
            ))}
          </div>
          <table className="w-full text-sm">
            <tbody>
              {[
                ["Entry zone", tp.entryZone ? `${usd(tp.entryZone[0])} – ${usd(tp.entryZone[1])}` : "N/A"],
                ["Stop loss", usd(tp.stopLoss)], ["Target 1", usd(tp.t1)], ["Target 2", usd(tp.t2)],
                ["Risk / Reward", tp.riskReward != null ? `${num(tp.riskReward, 1)} : 1` : "N/A"],
              ].map(([k, v]) => (
                <tr key={k} className="border-b border-line last:border-0">
                  <td className="py-1.5 text-mute">{k}</td><td className="num py-1.5 text-right font-semibold">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Drivers title="Top positives" items={r.drivers.positive} color="#16a34a" icon="✔" />
            <Drivers title="Top negatives" items={r.drivers.negative} color="#dc2626" icon="✖" />
          </div>
        </div>
      </div>
    </Card>
  );
}

function Drivers({ title, items, color, icon }: any) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase text-mute">{title}</div>
      <ul className="space-y-1 text-sm">
        {(items || []).map((x: any, i: number) => (
          <li key={i}><span style={{ color }}>{icon}</span> {x.metric}: <b className="num">{typeof x.value === "number" ? num(x.value) : x.value}</b>{" "}
            <span className="text-xs text-mute">({x.pillar})</span></li>
        ))}
        {(!items || items.length === 0) && <li className="text-mute">N/A</li>}
      </ul>
    </div>
  );
}
