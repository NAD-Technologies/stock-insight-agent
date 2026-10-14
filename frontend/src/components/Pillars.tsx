import { useState } from "react";
import { Badge, Card, Gauge, ScoreBar } from "./ui";
import { fmtMetric, num, ratingColor, scoreColor } from "../lib/format";

const NAMES: Record<string, string> = {
  technical: "Technical", fundamental: "Fundamental", analyst: "Analyst & Earnings", sentiment: "Sentiment & Smart Money", risk: "Risk & Market",
};

const icon = (score: number | null) =>
  score == null ? <span className="text-mute">–</span> : score >= 62 ? <span className="text-bull">✔</span> : score <= 38 ? <span className="text-bear">✖</span> : <span className="text-neutral">–</span>;

export function PillarCards({ d }: { d: any }) {
  const w = d.recommendation.weights || {};
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Object.keys(NAMES).map((k) => (
        <Pillar key={k} name={NAMES[k]} weight={w[k]} data={d[k === "technical" ? "technical" : k]} kind={k} />
      ))}
    </div>
  );
}

function Pillar({ name, weight, data, kind }: any) {
  const [open, setOpen] = useState(false);
  if (!data || data.score == null) return <Card title={name}><p className="text-sm text-mute">Data unavailable.</p></Card>;
  const comps: any[] = data.pillar?.components || [];
  const sectorByName: Record<string, any> = {};
  if (kind === "fundamental") (data.metrics || []).forEach((m: any) => (sectorByName[m.name] = m));
  return (
    <Card title={name} right={weight != null && <span className="text-xs text-mute">weight {Math.round(weight * 100)}%</span>}>
      <div className="mb-2 flex items-end justify-between">
        <span className="num text-3xl font-bold" style={{ color: scoreColor(data.score) }}>{num(data.score, 0)}</span>
        <Badge text={data.verdict || data.pillar?.verdict || ""} />
      </div>
      <ScoreBar score={data.score} />
      <div className="mt-1 text-xs text-mute">Data coverage {Math.round((data.pillar?.coverage ?? 0) * 100)}%</div>
      <button onClick={() => setOpen(!open)} className="mt-3 text-xs text-mute underline">{open ? "Hide details" : "Show details"}</button>
      {open && (
        <table className="mt-2 w-full text-xs">
          <thead><tr className="text-left text-mute"><th>Metric</th><th className="text-right">Value</th><th className="text-right">Sector</th><th className="text-right"> </th></tr></thead>
          <tbody>
            {comps.map((c) => {
              const m = sectorByName[c.name];
              return (
                <tr key={c.name} className="border-t border-line">
                  <td className="py-1">{c.name}</td>
                  <td className="num text-right">{m ? fmtMetric(m.value, m.format) : c.display == null ? "N/A" : typeof c.display === "number" ? num(c.display) : c.display}</td>
                  <td className="num text-right text-mute">{m?.sectorMedian != null ? fmtMetric(m.sectorMedian, m.format) : "–"}</td>
                  <td className="text-right">{icon(c.score)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

const RV: Record<string, number> = { "Strong Sell": 5, Sell: 25, Neutral: 50, Buy: 75, "Strong Buy": 95 };

export function TechSummary({ t }: { t: any }) {
  if (!t?.available) return <Card title="Technical summary"><p className="text-sm text-mute">Data unavailable.</p></Card>;
  const s = t.summary;
  const groups: [string, any][] = [["Oscillators", s.oscillators], ["Summary", s.overall], ["Moving Averages", s.movingAverages]];
  return (
    <Card title="Technical summary">
      <div className="grid grid-cols-3 gap-2">
        {groups.map(([label, g]) => (
          <div key={label} className="text-center">
            <div className="text-xs text-mute">{label}</div>
            <Gauge value={RV[g.rating] ?? 50} size={170} color={ratingColor(g.rating)} />
            <div className="-mt-6 text-sm font-bold" style={{ color: ratingColor(g.rating) }}>{g.rating}</div>
            <div className="num text-xs text-mute">{g.sell} sell · {g.neutral} neutral · {g.buy} buy</div>
          </div>
        ))}
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {[["Oscillators", "osc"], ["Moving averages", "ma"]].map(([title, grp]) => (
          <table key={grp} className="w-full text-xs">
            <thead><tr className="text-left text-mute"><th>{title}</th><th className="text-right">Value</th><th className="text-right">Signal</th></tr></thead>
            <tbody>
              {t.signals.filter((x: any) => x.group === grp).map((x: any) => (
                <tr key={x.name} className="border-t border-line">
                  <td className="py-1">{x.name}</td><td className="num text-right">{num(x.value)}</td>
                  <td className="text-right font-semibold" style={{ color: ratingColor(x.signal) }}>{x.signal}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
      </div>
      {t.patterns && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {t.patterns.structure && <Badge text={`Structure: ${t.patterns.structure}`} color="#64748b" />}
          {t.patterns.bollingerSqueeze && <Badge text="Bollinger squeeze" color="#f59e0b" />}
          {t.patterns.breakout && <Badge text={String(t.patterns.breakout)} color="#16a34a" />}
          {t.patterns.divergence && <Badge text={String(t.patterns.divergence)} color="#f59e0b" />}
          {t.patterns.crossRecent && <Badge text={String(t.patterns.crossRecent)} color="#3b82f6" />}
        </div>
      )}
    </Card>
  );
}
