import { useState } from "react";
import { compare } from "../api";
import { Badge, Card, ScoreBar, Skeleton } from "./ui";
import { big, num, pct, ratioPct, ratingColor, usd } from "../lib/format";

export default function Compare({ profile, initial }: { profile: string; initial: string[] }) {
  const [input, setInput] = useState(initial.slice(0, 4).join(", "));
  const [rows, setRows] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const run = async () => {
    const t = input.split(/[ ,]+/).map((x) => x.trim().toUpperCase()).filter(Boolean).slice(0, 4);
    if (t.length < 2) { setErr("Enter 2–4 tickers."); return; }
    setErr(""); setLoading(true);
    try { setRows((await compare(t, profile)).results); }
    catch (e: any) { setErr(e.message); setRows(null); }
    finally { setLoading(false); }
  };

  const metric: [string, (r: any) => string][] = [
    ["Price", (r) => usd(r.price)], ["Day change", (r) => pct(r.changePct)], ["Market cap", (r) => big(r.marketCap)],
    ["P/E", (r) => num(r.metrics?.pe)], ["Forward P/E", (r) => num(r.metrics?.forwardPe)],
    ["Revenue growth", (r) => ratioPct(r.metrics?.revenueGrowth)], ["Operating margin", (r) => ratioPct(r.metrics?.operatingMargin)],
    ["ROE", (r) => ratioPct(r.metrics?.roe)], ["Analyst upside", (r) => pct(r.upsidePct, 1)],
    ["RSI", (r) => num(r.rsi, 1)], ["Sharpe", (r) => num(r.sharpe)], ["Max drawdown", (r) => (r.maxDrawdown == null ? "N/A" : num(r.maxDrawdown, 1) + "%")],
  ];
  const pillars = ["technical", "fundamental", "analyst", "sentiment", "risk"];

  return (
    <div className="space-y-4">
      <Card title="Compare (2–4 tickers)">
        <div className="flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()}
            className="flex-1 rounded-lg border border-line bg-card px-3 py-2 text-sm" placeholder="AAPL, MSFT, NVDA" />
          <button onClick={run} className="rounded-lg bg-fg px-4 py-2 text-sm font-semibold text-bg">Compare</button>
        </div>
        {err && <p className="mt-2 text-sm text-bear">{err}</p>}
      </Card>
      {loading && <Skeleton h={300} />}
      {rows && !loading && (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr><th />{rows.map((r) => <th key={r.ticker} className="px-2 pb-2 text-left">{r.ticker}</th>)}</tr>
              </thead>
              <tbody>
                <tr className="border-t border-line"><td className="py-2 text-mute">Rating</td>
                  {rows.map((r) => <td key={r.ticker} className="px-2">{r.error ? <span className="text-mute">unavailable</span> : <Badge text={r.rating} />}</td>)}</tr>
                <tr className="border-t border-line"><td className="py-2 text-mute">Composite</td>
                  {rows.map((r) => <td key={r.ticker} className="px-2"><div className="num font-bold" style={{ color: ratingColor(r.rating || "") }}>{r.error ? "–" : num(r.compositeScore, 0)}</div>{!r.error && <ScoreBar score={r.compositeScore} />}</td>)}</tr>
                <tr className="border-t border-line"><td className="py-2 text-mute">Confidence</td>
                  {rows.map((r) => <td key={r.ticker} className="px-2">{r.confidence ?? "–"}</td>)}</tr>
                {pillars.map((p) => (
                  <tr key={p} className="border-t border-line"><td className="py-2 capitalize text-mute">{p}</td>
                    {rows.map((r) => <td key={r.ticker} className="num px-2">{r.pillarScores?.[p] == null ? "N/A" : num(r.pillarScores[p], 0)}</td>)}</tr>
                ))}
                {metric.map(([label, fn]) => (
                  <tr key={label} className="border-t border-line"><td className="py-2 text-mute">{label}</td>
                    {rows.map((r) => <td key={r.ticker} className="num px-2">{r.error ? "–" : fn(r)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
