import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Card, Gauge } from "./ui";
import { ago, big, na, num, pct, ratingColor, sym, usd } from "../lib/format";

const axis = { stroke: "var(--mute)", fontSize: 11 };
const tip = { contentStyle: { background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 } };
const yr = (p: string) => (p || "").slice(0, 7);

export function Fundamentals({ f, price }: { f: any; price: number }) {
  if (!f) return <Card title="Fundamentals"><p className="text-sm text-mute">Data unavailable.</p></Card>;
  const vs = Object.entries(f.vsSector || {}).map(([k, v]: any) => ({ name: k, Stock: v.value, "Sector median": v.sectorMedian }));
  const q = f.series?.quarterly || {}, a = f.series?.annual || {};
  const merge = (s: any, keys: string[]) => {
    const rows: Record<string, any> = {};
    keys.forEach((k) => (s[k] || []).forEach((p: any) => { rows[p.period] = { ...(rows[p.period] || { period: yr(p.period) }), [k]: p.value }; }));
    return Object.values(rows);
  };
  const growth = merge(q, ["revenue", "eps"]).map((r: any) => ({ ...r, revenue: r.revenue != null ? r.revenue / 1e9 : null }));
  const annual = merge(a, ["revenue", "eps"]).map((r: any) => ({ ...r, revenue: r.revenue != null ? r.revenue / 1e9 : null }));
  const margins = merge(a, ["grossMargin", "operatingMargin", "netMargin"]).map((r: any) => ({
    period: r.period, Gross: r.grossMargin * 100, Operating: r.operatingMargin * 100, Net: r.netMargin * 100,
  }));
  const fv = f.fairValue || {};
  const hi = Math.max(fv.high || 0, price || 0) * 1.1 || 1;
  const p = (v: number) => `${Math.min(100, Math.max(0, (v / hi) * 100))}%`;
  return (
    <Card title="Fundamentals" right={<Badge text={f.verdict || ""} />}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs text-mute">Valuation vs sector median</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={vs}><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="name" {...axis} /><YAxis {...axis} /><Tooltip {...tip} /><Legend />
              <Bar dataKey="Stock" fill="#3b82f6" /><Bar dataKey="Sector median" fill="#64748b" /></BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <div className="mb-1 text-xs text-mute">Fair value vs price</div>
          {fv.base ? (
            <div className="pt-6">
              <div className="relative h-3 rounded bg-line">
                <div className="absolute h-3 rounded bg-blue-500/50" style={{ left: p(fv.low), width: `calc(${p(fv.high)} - ${p(fv.low)})` }} />
                <div className="absolute -top-1 h-5 w-0.5 bg-blue-400" style={{ left: p(fv.base) }} title="Base" />
                <div className="absolute -top-2 h-7 w-1 rounded bg-fg" style={{ left: p(price) }} title="Price" />
              </div>
              <div className="num mt-3 flex justify-between text-xs text-mute"><span>Low {usd(fv.low)}</span><span>Base {usd(fv.base)}</span><span>High {usd(fv.high)}</span></div>
              <div className="mt-3 text-sm">Price {usd(price)} · Margin of safety{" "}
                <b style={{ color: (fv.marginOfSafety ?? 0) >= 0 ? "#16a34a" : "#dc2626" }}>{pct(fv.marginOfSafety, 1)}</b></div>
              <div className="mt-1 text-xs text-mute">DCF {usd(fv.dcf)} · Graham {usd(fv.graham)} · WACC {num((fv.assumptions?.wacc ?? 0) * 100, 1)}% · terminal g {num((fv.assumptions?.terminalGrowth ?? 0) * 100, 1)}%</div>
            </div>
          ) : <p className="text-sm text-mute">Fair value N/A (insufficient cash-flow data).</p>}
        </div>
        <div>
          <div className="mb-1 text-xs text-mute">Quarterly revenue ({sym()}B) &amp; EPS</div>
          <GrowthBars data={growth} />
        </div>
        <div>
          <div className="mb-1 text-xs text-mute">Annual revenue ({sym()}B) &amp; EPS</div>
          <GrowthBars data={annual} />
        </div>
        <div className="lg:col-span-2">
          <div className="mb-1 text-xs text-mute">Margin trend (annual, %)</div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={margins}><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="period" {...axis} /><YAxis {...axis} /><Tooltip {...tip} /><Legend />
              <Line dataKey="Gross" stroke="#16a34a" dot={false} /><Line dataKey="Operating" stroke="#3b82f6" dot={false} /><Line dataKey="Net" stroke="#f59e0b" dot={false} /></LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </Card>
  );
}

function GrowthBars({ data }: { data: any[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data}><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="period" {...axis} />
        <YAxis yAxisId="l" {...axis} /><YAxis yAxisId="r" orientation="right" {...axis} /><Tooltip {...tip} /><Legend />
        <Bar yAxisId="l" dataKey="revenue" name={`Revenue ${sym()}B`} fill="#3b82f6" /><Bar yAxisId="r" dataKey="eps" name="EPS" fill="#16a34a" /></BarChart>
    </ResponsiveContainer>
  );
}

export function Analyst({ a, price }: { a: any; price: number }) {
  if (!a) return <Card title="Analysts & earnings"><p className="text-sm text-mute">Data unavailable.</p></Card>;
  const dist = a.distribution || {};
  const parts: [string, string, string][] = [["strongBuy", "Strong Buy", "#15803d"], ["buy", "Buy", "#22c55e"], ["hold", "Hold", "#f59e0b"], ["sell", "Sell", "#f87171"], ["strongSell", "Strong Sell", "#b91c1c"]];
  const total = parts.reduce((s, [k]) => s + (dist[k] || 0), 0);
  const t = a.targets || {};
  const hi = Math.max(t.high || 0, price || 0) * 1.05 || 1, lo = Math.min(t.low || price || 0, price || 0) * 0.95;
  const p = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  const sur = (a.surprises || []).slice().reverse().map((s: any) => ({ date: yr(s.date), pct: s.surprisePct }));
  return (
    <Card title="Analysts & earnings" right={<Badge text={a.verdict || ""} />}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs text-mute">Rating distribution ({a.numAnalysts ?? total} analysts)</div>
          {total > 0 ? (
            <>
              <div className="flex h-6 overflow-hidden rounded">
                {parts.map(([k, , c]) => dist[k] ? <div key={k} style={{ width: `${(dist[k] / total) * 100}%`, background: c }} title={`${k}: ${dist[k]}`} /> : null)}
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs">{parts.map(([k, l, c]) => <span key={k}><span style={{ color: c }}>●</span> {l} {dist[k] ?? 0}</span>)}</div>
            </>
          ) : <p className="text-sm text-mute">N/A</p>}
          <div className="mt-5 mb-1 text-xs text-mute">Price target range</div>
          {t.mean ? (
            <div className="pt-4">
              <div className="relative h-2 rounded bg-line">
                <div className="absolute h-2 rounded bg-blue-500/50" style={{ left: p(t.low), width: `calc(${p(t.high)} - ${p(t.low)})` }} />
                <div className="absolute -top-1 h-4 w-0.5 bg-blue-400" style={{ left: p(t.mean) }} />
                <div className="absolute -top-2 h-6 w-1 rounded bg-fg" style={{ left: p(price) }} />
              </div>
              <div className="num mt-3 flex justify-between text-xs text-mute"><span>Low {usd(t.low)}</span><span>Mean {usd(t.mean)}</span><span>High {usd(t.high)}</span></div>
              <div className="mt-2 text-sm">Implied upside <b style={{ color: (a.upsidePct ?? 0) >= 0 ? "#16a34a" : "#dc2626" }}>{pct(a.upsidePct, 1)}</b>
                {" "}· Net upgrades 90d <b>{a.netUpgrades90d ?? "N/A"}</b> · Estimate revisions net <b>{a.revisionNet ?? "N/A"}</b></div>
            </div>
          ) : <p className="text-sm text-mute">N/A</p>}
        </div>
        <div>
          <div className="mb-1 text-xs text-mute">EPS surprise % (beat rate {na(a.beatRate) ? "N/A" : Math.round(a.beatRate * 100) + "%"})</div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={sur}><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="date" {...axis} /><YAxis {...axis} /><Tooltip {...tip} /><ReferenceLine y={0} stroke="var(--mute)" />
              <Bar dataKey="pct" name="Surprise %">{sur.map((s: any, i: number) => <Cell key={i} fill={s.pct >= 0 ? "#16a34a" : "#dc2626"} />)}</Bar></BarChart>
          </ResponsiveContainer>
          <div className="mt-2 mb-1 text-xs text-mute">Recent upgrades / downgrades</div>
          <ul className="max-h-40 space-y-1 overflow-auto text-xs">
            {(a.upgradesDowngrades || []).slice(0, 12).map((u: any, i: number) => (
              <li key={i} className="flex justify-between border-b border-line pb-1">
                <span className="text-mute">{u.date}</span><span>{u.firm}</span>
                <span style={{ color: u.action === "up" ? "#16a34a" : u.action === "down" ? "#dc2626" : "var(--mute)" }}>{u.from || "–"} → {u.to}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

export function News({ s }: { s: any }) {
  const news = s?.news || [];
  const score = s?.newsScore;
  return (
    <Card title="News & sentiment" right={s?.newsMethod && <span className="text-xs text-mute">classifier: {s.newsMethod}</span>}>
      {!news.length ? <p className="text-sm text-mute">No recent news available.</p> : (
        <div className="grid gap-4 lg:grid-cols-[200px_1fr]">
          <div className="text-center">
            <Gauge value={((score ?? 0) + 1) * 50} label="News sentiment" size={190} color={score > 0.15 ? "#16a34a" : score < -0.15 ? "#dc2626" : "#f59e0b"} />
            {(s.catalysts || []).length > 0 && (
              <div className="mt-2 flex flex-wrap justify-center gap-1">{s.catalysts.map((c: string) => <Badge key={c} text={c} color="#3b82f6" />)}</div>
            )}
          </div>
          <ul className="max-h-96 space-y-2 overflow-auto">
            {news.map((n: any, i: number) => (
              <li key={i} className="border-b border-line pb-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge text={n.sentiment} /><Badge text={`${n.impact} impact`} color="#64748b" />
                  {n.catalyst && n.catalyst !== "none" && <Badge text={n.catalyst} color="#3b82f6" />}
                  <span className="text-xs text-mute">{n.source} · {ago(n.time)}</span>
                </div>
                <a href={n.url} target="_blank" rel="noreferrer" className="mt-1 block text-sm font-medium hover:underline">{n.title}</a>
                <div className="text-xs text-mute">{n.reason}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

export function SmartMoney({ s }: { s: any }) {
  if (!s) return <Card title="Smart money"><p className="text-sm text-mute">Data unavailable.</p></Card>;
  const ins = s.insider || {}, sh = s.short || {}, op = s.options || {};
  const kv = (k: string, v: any) => <div><div className="text-xs text-mute">{k}</div><div className="num text-sm font-semibold">{v}</div></div>;
  return (
    <Card title="Smart money">
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {kv("Institutional %", na(ins.institutionPct) ? "N/A" : num(ins.institutionPct, 1) + "%")}
        {kv("Inst. change", na(ins.institutionalChangePct) ? "N/A" : pct(ins.institutionalChangePct, 1))}
        {kv("Insider net (6m)", na(ins.netValue) ? "N/A" : sym() + big(ins.netValue))}
        {kv("Buys / Sells", `${ins.buys ?? 0} / ${ins.sells ?? 0}`)}
        {kv("Short % float", na(sh.pctFloat) ? "N/A" : num(sh.pctFloat) + "%")}
        {kv("Days to cover", num(sh.daysToCover, 1))}
        {kv("Put/Call (OI)", num(op.putCall))}
        {kv("IV / percentile", na(op.iv) ? "N/A" : `${num(op.iv, 1)}% / ${na(op.ivPercentile) ? "N/A" : num(op.ivPercentile, 0)}`)}
      </div>
      <div className="mb-1 text-xs text-mute">Recent insider transactions</div>
      <table className="w-full text-xs">
        <tbody>
          {(ins.transactions || []).slice(0, 8).map((t: any, i: number) => (
            <tr key={i} className="border-t border-line">
              <td className="py-1 text-mute">{t.date}</td><td>{t.insider}</td><td className="text-mute">{t.position}</td>
              <td style={{ color: ratingColor(t.type) }}>{t.type}</td><td className="num text-right">{big(t.shares)}</td><td className="num text-right">{na(t.value) ? "" : sym() + big(t.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export function Risk({ r }: { r: any }) {
  if (!r) return <Card title="Risk & market context"><p className="text-sm text-mute">Data unavailable.</p></Card>;
  const st = r.stats || {};
  const rows = ["1M", "3M", "6M", "1Y"];
  const kv = (k: string, v: any) => <div><div className="text-xs text-mute">{k}</div><div className="num text-sm font-semibold">{v}</div></div>;
  return (
    <Card title="Risk & market context">
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {kv("Beta", num(r.beta))}{kv("Volatility (ann.)", na(st.volatility) ? "N/A" : num(st.volatility, 1) + "%")}
        {kv("Max drawdown 1Y", na(st.maxDrawdown) ? "N/A" : num(st.maxDrawdown, 1) + "%")}{kv("Sharpe / Sortino", `${num(st.sharpe)} / ${num(st.sortino)}`)}
        {kv("VIX", `${num(r.vix, 1)} (${r.vixRegime ?? "N/A"})`)}{kv("10Y yield", r.tenYear ? `${num(r.tenYear.level)}% (${r.tenYear.change3mBps > 0 ? "+" : ""}${num(r.tenYear.change3mBps, 0)}bps 3m)` : "N/A")}
      </div>
      <table className="w-full text-xs">
        <thead><tr className="text-left text-mute"><th>Excess return</th>{rows.map((x) => <th key={x} className="text-right">{x}</th>)}</tr></thead>
        <tbody>
          {[["vs SPY", r.relativeStrength], [`vs ${r.sectorEtf ?? "sector"}`, r.sectorRelativeStrength]].map(([label, rs]: any) => (
            <tr key={label} className="border-t border-line"><td className="py-1">{label}</td>
              {rows.map((x) => { const v = rs?.[x]?.excess; return <td key={x} className="num text-right" style={{ color: na(v) ? undefined : v >= 0 ? "#16a34a" : "#dc2626" }}>{na(v) ? "N/A" : pct(v, 1)}</td>; })}
            </tr>
          ))}
        </tbody>
      </table>
      {(r.events || []).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {r.events.map((e: any, i: number) => <Badge key={i} text={`${e.type} ${e.date} (${e.daysAway}d)${e.risk ? " ⚠ within 14d" : ""}`} color={e.risk ? "#dc2626" : "#64748b"} />)}
        </div>
      )}
    </Card>
  );
}

export function Narrative({ n }: { n: any }) {
  if (!n) return <Card title="AI analyst summary"><p className="text-sm text-mute">Data unavailable.</p></Card>;
  return (
    <Card title="AI analyst summary" right={<span className="text-xs text-mute">{n.source === "llm" ? "Written by Claude from the data above" : "Template summary (no LLM key)"}</span>}>
      <p className="mb-4 text-sm leading-relaxed">{n.summary}</p>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border p-3" style={{ borderColor: "#16a34a55" }}>
          <div className="mb-1 font-semibold text-bull">Bull case</div>
          <ul className="list-disc space-y-1 pl-4 text-sm">{(n.bullCase || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
        </div>
        <div className="rounded-lg border p-3" style={{ borderColor: "#dc262655" }}>
          <div className="mb-1 font-semibold text-bear">Bear case</div>
          <ul className="list-disc space-y-1 pl-4 text-sm">{(n.bearCase || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
        </div>
      </div>
      <div className="mt-4">
        <div className="mb-1 font-semibold text-neutral">Key risks</div>
        <ul className="list-disc space-y-1 pl-4 text-sm">{(n.keyRisks || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
      </div>
    </Card>
  );
}
