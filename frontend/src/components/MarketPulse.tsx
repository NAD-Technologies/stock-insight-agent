import { useEffect, useState } from "react";
import { sectorAccuracy, sectors } from "../api";
import { ago, pct } from "../lib/format";
import { Card, Skeleton } from "./ui";

export const HORIZONS = ["1W", "1M", "3M"] as const;
export type Horizon = (typeof HORIZONS)[number];
const HORIZON_LABEL: Record<Horizon, string> = { "1W": "1 week", "1M": "1 month", "3M": "3 months" };

/** red (0) -> amber (50) -> green (100) */
export const tone = (score: number | null | undefined) => {
  const h = Math.round(Math.max(0, Math.min(100, score ?? 50)) * 1.2);
  return { bg: `hsl(${h} 65% 45% / 0.16)`, border: `hsl(${h} 62% 42%)` };
};
export const ARROW: Record<string, string> = { Up: "▲", Down: "▼", Flat: "►" };
export const dirColor = (d: string) => (d === "Up" ? "#22c55e" : d === "Down" ? "#f43f5e" : "#f59e0b");

export function DirTag({ d, small }: { d: string; small?: boolean }) {
  return <span className={`font-semibold ${small ? "text-xs" : "text-sm"}`} style={{ color: dirColor(d) }}>{ARROW[d]} {d}</span>;
}

export function HorizonToggle({ value, onChange }: { value: Horizon; onChange: (h: Horizon) => void }) {
  return (
    <div className="inline-flex overflow-hidden rounded-lg border border-line" role="group" aria-label="Prediction horizon">
      {HORIZONS.map((h) => (
        <button key={h} onClick={() => onChange(h)} aria-pressed={value === h}
          className={`px-3 py-1.5 text-sm font-medium ${value === h ? "bg-fg text-bg" : "text-mute hover:text-fg"}`}>{h}</button>
      ))}
    </div>
  );
}

function Accuracy() {
  const [a, setA] = useState<any>(null);
  useEffect(() => { sectorAccuracy().then(setA).catch(() => setA(null)); }, []);
  if (!a) return null;
  const o = a.overall;
  return (
    <Card title="Track record">
      {o.n === 0 ? (
        <p className="text-sm text-mute">
          Every call is logged and graded against what the sector actually did versus SPY. {a.pending} predictions are waiting for their horizon to
          pass. The first 1-week results arrive about a week after launch, so no accuracy is claimed yet.
        </p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            {(["1W", "1M", "3M"] as const).map((h) => {
              const s = a.byHorizon[h];
              return (
                <div key={h} className="rounded-lg border border-line p-3">
                  <div className="text-xs font-medium uppercase tracking-wide text-mute">{HORIZON_LABEL[h]}</div>
                  <div className="num mt-1 text-2xl font-bold">{s.hitRate == null ? "–" : `${s.hitRate}%`}</div>
                  <div className="text-xs text-mute">model hit rate, n={s.n}</div>
                  <div className="text-xs text-mute">naive baseline {s.baselineHitRate == null ? "–" : `${s.baselineHitRate}%`}</div>
                </div>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-mute">The baseline assumes last month's relative move simply continues. The model should beat it before it is trusted.</p>
        </>
      )}
    </Card>
  );
}

export default function MarketPulse({ onOpen, isAdmin }: { onOpen: (id: string) => void; isAdmin?: boolean }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [h, setH] = useState<Horizon>("1M");
  const [group, setGroup] = useState<"all" | "gics" | "theme">("all");

  useEffect(() => { sectors().then(setD).catch((e) => setErr(e.message)); }, []);

  if (err) return <Card title="Market Pulse"><p className="text-sm text-bear">{err}</p></Card>;
  if (!d) return <div className="space-y-4"><Skeleton h={90} /><Skeleton h={420} /></div>;
  if (!d.ready) return <Card title="Market Pulse"><p className="text-sm text-mute">{d.message}</p></Card>;

  const all: any[] = d.themes;
  const bySel = [...all].sort((a, b) => (b.horizons[h].score ?? 0) - (a.horizons[h].score ?? 0));
  const shown = bySel.filter((t) => group === "all" || t.group === group);
  const rising = bySel.slice(0, 3), falling = bySel.slice(-3).reverse();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Market Pulse</h2>
          <p className="text-sm text-mute">
            Which sectors are gaining or losing momentum, and why. Updated {ago(new Date(d.asOf * 1000).toISOString())}
            {d.stale && <span className="ml-2 rounded bg-neutral/20 px-1.5 py-0.5 text-xs font-semibold text-neutral">stale</span>}
            {d.run?.status === "degraded" && isAdmin && <span className="ml-2 text-xs">(last run degraded)</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex overflow-hidden rounded-lg border border-line" role="group" aria-label="Filter">
            {([["all", "All"], ["gics", "Sectors"], ["theme", "Themes"]] as const).map(([k, label]) => (
              <button key={k} onClick={() => setGroup(k)} aria-pressed={group === k}
                className={`px-3 py-1.5 text-sm font-medium ${group === k ? "bg-fg text-bg" : "text-mute hover:text-fg"}`}>{label}</button>
            ))}
          </div>
          <HorizonToggle value={h} onChange={setH} />
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {[["Rising", rising, "#22c55e"], ["Falling", falling, "#f43f5e"]].map(([label, list, col]: any) => (
          <div key={label} className="rounded-xl border border-line bg-card p-4">
            <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: col }}>{label} ({HORIZON_LABEL[h]})</div>
            <ul className="mt-2 space-y-1.5">
              {list.map((t: any) => (
                <li key={t.theme}>
                  <button onClick={() => onOpen(t.theme)} className="flex w-full items-center justify-between gap-2 text-left text-sm hover:underline">
                    <span className="font-medium">{t.name}</span>
                    <span className="num text-mute">{t.horizons[h].score} · <DirTag d={t.horizons[h].direction} small /></span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {d.events.length > 0 && (
        <Card title="Events driving the market">
          <ul className="space-y-3">
            {d.events.map((e: any) => (
              <li key={e.type} className="text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <b>{e.label}</b>
                  <span className="rounded-full border border-line px-2 py-0.5 text-xs text-mute">{e.severity} severity · {e.nSources} outlets</span>
                </div>
                <div className="mt-1 text-xs text-mute">
                  {e.helps.length > 0 && <span><b style={{ color: "#22c55e" }}>▲ Helps:</b> {e.helps.map((x: any) => x.name).join(", ")}  </span>}
                  {e.hurts.length > 0 && <span><b style={{ color: "#f43f5e" }}>▼ Hurts:</b> {e.hurts.map((x: any) => x.name).join(", ")}</span>}
                </div>
                {e.headline?.url && <a href={e.headline.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-xs text-mute underline">{e.headline.title}</a>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {shown.map((t) => {
          const x = t.horizons[h], c = tone(x.score);
          return (
            <button key={t.theme} onClick={() => onOpen(t.theme)} className="rounded-xl border border-line p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md"
              style={{ background: c.bg, borderLeft: `5px solid ${c.border}` }}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-semibold">{t.name}</div>
                  <div className="text-xs text-mute">{t.benchmark}</div>
                </div>
                <div className="num text-3xl font-bold leading-none">{x.score ?? "–"}</div>
              </div>
              <div className="mt-2 flex items-center justify-between text-sm">
                <DirTag d={x.direction} />
                <span className="text-xs text-mute">{x.probUp != null && `${Math.round(x.probUp * 100)}% chance to beat SPY`}</span>
              </div>
              <div className="mt-1 flex items-center justify-between text-xs text-mute">
                <span>1M {pct((t.ret1M ?? 0) * 100, 1)} ({pct((t.excess1M ?? 0) * 100, 1)} vs SPY)</span>
                <span>{x.confidence} conf.</span>
              </div>
              {t.leaders.length > 0 && <div className="mt-2 truncate text-xs"><span className="text-mute">Leaders:</span> <b>{t.leaders.join(", ")}</b></div>}
            </button>
          );
        })}
      </div>

      <Accuracy />
      <p className="text-xs text-mute">
        Sector scores combine price momentum, news sentiment, detected events and a fund-flow proxy; earnings and social signals are not included yet,
        so confidence is capped. "Chance to beat SPY" is an uncalibrated estimate. Educational research only, not financial advice.
      </p>
    </div>
  );
}
