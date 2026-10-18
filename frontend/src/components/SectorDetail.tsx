import { useEffect, useState } from "react";
import { sectorDetail } from "../api";
import { ago, num, pct } from "../lib/format";
import { Badge, Card, Gauge, Skeleton } from "./ui";
import { DirTag, Horizon, HorizonToggle, dirColor, tone } from "./MarketPulse";

const FACTORS: [string, string, string][] = [
  ["momentum", "Price momentum", "Return vs SPY, share of stocks above their 50-day average, trend"],
  ["news", "News sentiment", "Recency- and impact-weighted sentiment of recent headlines"],
  ["events", "Event impact", "War, sanctions, rates and similar events mapped to this sector"],
  ["flows", "Fund flows (proxy)", "ETF trading-volume surge, signed by the 1M price trend"],
  ["earnings", "Earnings", "Beat rate and guidance (coming in a later phase)"],
  ["social", "Social attention", "Mention volume and sentiment (coming in a later phase)"],
];

function History({ rows, h }: { rows: any[]; h: Horizon }) {
  const pts = rows.filter((r) => r[h] != null);
  if (pts.length < 2) return <p className="text-sm text-mute">Score history builds up as the pipeline runs (every few hours).</p>;
  const w = 600, ht = 120, min = 0, max = 100;
  const x = (i: number) => (i / (pts.length - 1)) * w;
  const y = (v: number) => ht - ((v - min) / (max - min)) * ht;
  return (
    <svg viewBox={`0 0 ${w} ${ht}`} className="h-32 w-full" preserveAspectRatio="none" role="img" aria-label="Score history">
      <line x1="0" x2={w} y1={y(60)} y2={y(60)} stroke="#22c55e" strokeDasharray="4 4" opacity=".5" />
      <line x1="0" x2={w} y1={y(40)} y2={y(40)} stroke="#f43f5e" strokeDasharray="4 4" opacity=".5" />
      <polyline fill="none" stroke="var(--brand)" strokeWidth="2.5" strokeLinejoin="round" points={pts.map((r, i) => `${x(i)},${y(r[h])}`).join(" ")} />
    </svg>
  );
}

function Picks({ title, rows, onTicker, color }: { title: string; rows: any[]; onTicker: (t: string) => void; color: string }) {
  return (
    <Card title={title} className="overflow-x-auto">
      <table className="w-full min-w-[420px] text-sm">
        <thead><tr className="text-left text-xs uppercase text-mute"><th className="pb-2">Ticker</th><th>Rating</th><th className="text-right">Rank</th><th className="text-right">1M</th><th className="text-right">vs sector</th><th className="text-right">Beta</th></tr></thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.ticker} className="border-t border-line">
              <td className="py-2">
                <button onClick={() => onTicker(p.ticker)} className="text-left hover:underline">
                  <b style={{ color }}>{p.ticker}</b><div className="max-w-[160px] truncate text-xs text-mute">{p.name}</div>
                </button>
              </td>
              <td>{p.rating ? <Badge text={p.rating} /> : <span className="text-xs text-mute" title="Full analysis not yet run for this stock">pending</span>}</td>
              <td className="num text-right font-semibold">{p.rank}</td>
              <td className="num text-right">{p.ret1M == null ? "–" : pct(p.ret1M * 100, 1)}</td>
              <td className="num text-right">{p.relativeStrength == null ? "–" : pct(p.relativeStrength * 100, 1)}</td>
              <td className="num text-right">{p.beta ?? "–"}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={6} className="py-4 text-center text-mute">Not enough liquid constituents with data.</td></tr>}
        </tbody>
      </table>
    </Card>
  );
}

export default function SectorDetail({ id, onBack, onTicker }: { id: string; onBack: () => void; onTicker: (t: string) => void }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [h, setH] = useState<Horizon>("1M");
  useEffect(() => { setD(null); sectorDetail(id).then(setD).catch((e) => setErr(e.message)); }, [id]);

  if (err) return <Card title="Sector"><p className="text-sm text-bear">{err}</p><button onClick={onBack} className="mt-3 rounded-lg border border-line px-3 py-1.5 text-sm">Back</button></Card>;
  if (!d) return <Skeleton h={500} />;
  const x = d.horizons[h], c = tone(x.score), m = d.metrics;

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm text-mute hover:text-fg">← Market Pulse</button>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">{d.name}</h2>
          <p className="text-sm text-mute">
            Benchmark {d.benchmark.symbol}{d.benchmark.kind === "basket" ? " (no single ETF)" : ""} · rank {d.rank} of 26 · updated {ago(new Date(d.asOf * 1000).toISOString())}
            {d.stale && <span className="ml-2 rounded bg-neutral/20 px-1.5 py-0.5 text-xs font-semibold text-neutral">stale</span>}
          </p>
        </div>
        <HorizonToggle value={h} onChange={setH} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-line p-4 text-center" style={{ background: c.bg, borderLeft: `5px solid ${c.border}` }}>
          <Gauge value={x.score ?? 0} label={`Sector score · ${h}`} size={220} color={dirColor(x.direction)} />
          <div className="mt-1 text-lg"><DirTag d={x.direction} /></div>
          {x.probUp != null && <div className="text-sm text-mute">{Math.round(x.probUp * 100)}% chance to beat SPY <span className="text-xs">(uncalibrated)</span></div>}
          <div className="mt-2 text-sm">Confidence: <b>{x.confidence}</b></div>
          {x.confidenceReasons.length > 0 && <div className="text-xs text-mute">{x.confidenceReasons.join("; ")}</div>}
        </div>
        <Card title="Factor breakdown" className="lg:col-span-2">
          <ul className="space-y-3">
            {FACTORS.map(([k, label, hint]) => {
              const f = x.factors[k];
              const has = f && f.score != null;
              return (
                <li key={k} title={hint}>
                  <div className="flex justify-between text-sm">
                    <span className={has ? "font-medium" : "text-mute"}>{label}</span>
                    <span className="num text-mute">{has ? `${f.score} · weight ${Math.round(f.weight * 100)}%` : "no data yet"}</span>
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-line">
                    {has && <div className="h-2 rounded-full" style={{ width: `${f.score}%`, background: tone(f.score).border }} />}
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs text-mute">50 is neutral versus the market. Missing factors are left out and the remaining weights are rescaled, which lowers confidence.</p>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {([["Why it's strong", d.drivers.positive, "#22c55e", "▲"], ["Why it's weak", d.drivers.negative, "#f43f5e", "▼"]] as const).map(([title, list, col, mark]) => (
          <Card key={title} title={title}>
            <ul className="space-y-2.5">
              {list.map((dr: any, i: number) => (
                <li key={i} className="text-sm">
                  <span style={{ color: col }}>{mark}</span>{" "}
                  {dr.url ? <a href={dr.url} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2 hover:decoration-fg">{dr.text}</a> : dr.text}
                  <span className="ml-1 text-xs text-mute">{dr.source ? `· ${dr.source}` : `· ${dr.factor}`}</span>
                </li>
              ))}
              {list.length === 0 && <li className="text-sm text-mute">Nothing significant right now.</li>}
            </ul>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title={`Score history (${h})`}><History rows={d.history} h={h} /></Card>
        <Card title="Key numbers">
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            {[["1W return", m.returns["1W"]], ["1M return", m.returns["1M"]], ["3M return", m.returns["3M"]]].map(([k, v]: any) => (
              <div key={k} className="contents"><dt className="text-mute">{k}</dt><dd className="num text-right">{v == null ? "–" : pct(v * 100, 1)} <span className="text-xs text-mute">(SPY {pct((m.spyReturns[k.slice(0, 2)] ?? 0) * 100, 1)})</span></dd></div>
            ))}
            <dt className="text-mute">Constituents above 50-day avg</dt><dd className="num text-right">{m.breadth == null ? "–" : `${Math.round(m.breadth * 100)}%`}</dd>
            <dt className="text-mute">News items (7d)</dt><dd className="num text-right">{m.newsItems}</dd>
            <dt className="text-mute">News signal</dt><dd className="num text-right">{m.newsSignal == null ? "–" : num(m.newsSignal, 2)}</dd>
          </dl>
        </Card>
      </div>

      {d.events.length > 0 && (
        <Card title="Events affecting this sector">
          <ul className="space-y-2 text-sm">
            {d.events.map((e: any) => (
              <li key={e.type}>
                <b style={{ color: e.impact > 0 ? "#22c55e" : "#f43f5e" }}>{e.impact > 0 ? "▲ Tailwind" : "▼ Headwind"}</b> {e.type.replace(/_/g, " ")}
                <span className="text-xs text-mute"> · {e.severity} severity, {e.nSources} outlets, impact {e.impact > 0 ? "+" : ""}{e.impact}</span>
                {e.headline?.url && <a href={e.headline.url} target="_blank" rel="noreferrer" className="block truncate text-xs text-mute underline">{e.headline.title}</a>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Picks title="Leaders: stocks to watch" rows={d.picks.leaders} onTicker={onTicker} color="#22c55e" />
        <Picks title="Laggards: stocks to avoid" rows={d.picks.laggards} onTicker={onTicker} color="#f43f5e" />
      </div>
      <p className="text-xs text-mute">
        Rank = 50% full stock analysis score, 20% stock news momentum, 15% strength vs the sector, 15% sensitivity to the sector's direction. Names under the
        liquidity minimum are excluded. "Pending" means the full analysis has not run for that stock yet; it ranks as neutral until it has.
      </p>

      {d.news.length > 0 && (
        <Card title="Sector news">
          <ul className="space-y-2">
            {d.news.map((n: any, i: number) => (
              <li key={i} className="flex items-start justify-between gap-3 text-sm">
                <a href={n.url} target="_blank" rel="noreferrer" className="hover:underline">{n.title}<span className="ml-1 text-xs text-mute">· {n.source}</span></a>
                <Badge text={n.sentiment} />
              </li>
            ))}
          </ul>
        </Card>
      )}
      <p className="text-xs text-mute">Educational research only, not financial advice.</p>
    </div>
  );
}
