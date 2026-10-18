import { useEffect, useMemo, useRef, useState } from "react";
import { adminAgents } from "../api";
import { when } from "./MyActivity";
import { Card, Skeleton } from "./ui";

const KIND: Record<string, { label: string; color: string }> = {
  control: { label: "Control", color: "#64748b" },
  collector: { label: "Collector", color: "#0ea5e9" },
  llm: { label: "LLM", color: "#a855f7" },
  engine: { label: "Engine", color: "#f59e0b" },
  quant: { label: "Quant", color: "#14b8a6" },
  publisher: { label: "Publisher", color: "#6366f1" },
};

// Fixed layout (viewBox 1080 x 520): left to right = the order work flows through the pipeline.
const POS: Record<string, [number, number]> = {
  scheduler: [95, 260], price_agent: [320, 60], news_agent: [320, 165], sentiment_agent: [525, 165], event_agent: [320, 275],
  stock_agent: [320, 395], quant_agent: [690, 225], picker_agent: [850, 335], publisher_agent: [985, 215], evaluator_agent: [690, 455],
};
const W = 150, H = 54;
const STATUS_COLOR: Record<string, string> = { ok: "#22c55e", warn: "#f59e0b", error: "#f43f5e" };

const dur = (ms?: number | null) => (ms == null ? "" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);

function anchor(from: string, to: string): { d: string; mid: [number, number] } | null {
  const a = POS[from], b = POS[to];
  if (!a || !b || from === to) return null;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  let p1: [number, number], p2: [number, number];
  if (Math.abs(dx) > W * 0.6) { const s = Math.sign(dx); p1 = [a[0] + s * W / 2, a[1]]; p2 = [b[0] - s * W / 2, b[1]]; }
  else { const s = Math.sign(dy); p1 = [a[0], a[1] + s * H / 2]; p2 = [b[0], b[1] - s * H / 2]; }
  const horizontal = Math.abs(dx) > W * 0.6;
  const c1: [number, number] = horizontal ? [p1[0] + (p2[0] - p1[0]) / 2, p1[1]] : [p1[0], p1[1] + (p2[1] - p1[1]) / 2];
  const c2: [number, number] = horizontal ? [p1[0] + (p2[0] - p1[0]) / 2, p2[1]] : [p2[0], p1[1] + (p2[1] - p1[1]) / 2];
  const mid: [number, number] = [(p1[0] + 3 * c1[0] + 3 * c2[0] + p2[0]) / 8, (p1[1] + 3 * c1[1] + 3 * c2[1] + p2[1]) / 8];
  return { d: `M ${p1[0]} ${p1[1]} C ${c1[0]} ${c1[1]}, ${c2[0]} ${c2[1]}, ${p2[0]} ${p2[1]}`, mid };
}

export default function AgentsDashboard() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [runId, setRunId] = useState<number | undefined>();
  const [idx, setIdx] = useState<number | null>(null); // replay position (index into messages); null = show everything
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [focus, setFocus] = useState<string | null>(null); // selected agent
  const [open, setOpen] = useState<number | null>(null);
  const rowRefs = useRef<Record<number, HTMLTableRowElement | null>>({});

  useEffect(() => {
    setD((p: any) => (p ? { ...p, loading: true } : p));
    adminAgents(runId).then((r) => { setD(r); setIdx(null); setPlaying(false); setOpen(null); }).catch((e) => setErr(e.message));
  }, [runId]);

  const msgs: any[] = d?.messages || [];
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setIdx((i) => {
      const n = (i == null ? -1 : i) + 1;
      if (n >= msgs.length) { setPlaying(false); return msgs.length - 1; }
      return n;
    }), 900 / speed);
    return () => clearInterval(t);
  }, [playing, speed, msgs.length]);
  useEffect(() => { if (idx != null) rowRefs.current[idx]?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [idx]);

  const active = idx != null ? msgs[idx] : null;
  const shown = useMemo(() => (focus ? msgs.filter((m) => m.sender === focus || m.receiver === focus) : msgs), [msgs, focus]);

  if (err) return <Card title="Agents"><p className="text-sm text-bear">{err}</p></Card>;
  if (!d) return <div className="space-y-4"><Skeleton h={80} /><Skeleton h={520} /></div>;
  if (!d.run) return <Card title="Agents"><p className="text-sm text-mute">No pipeline run has been recorded yet. Messages appear after the next Sector Pulse run.</p></Card>;

  const edgeActive = (e: any) => active && e.from === active.sender && e.to === active.receiver;
  const nodeActive = (id: string) => active && (active.sender === id || active.receiver === id);
  const dim = (cond: boolean) => (active && !cond ? 0.25 : 1);
  const names: Record<string, string> = Object.fromEntries(d.agents.map((a: any) => [a.id, a.name]));
  const a2 = active && anchor(active.sender, active.receiver);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Agents</h2>
          <p className="text-sm text-mute">
            How the Sector Pulse agents hand work to each other. Each arrow is a structured message, not free chat. Run #{d.run.id} ·
            <span style={{ color: d.run.status === "ok" ? "#22c55e" : d.run.status === "degraded" ? "#f59e0b" : "#f43f5e" }}> {d.run.status}</span>
            {d.run.seconds != null && ` · ${d.run.seconds}s`} · {msgs.length} messages · {d.run.finished ? when(d.run.finished) : "running…"}
          </p>
        </div>
        <select value={d.run.id} onChange={(e) => setRunId(Number(e.target.value))} className="rounded-lg border border-line bg-card px-2 py-2 text-sm" aria-label="Pipeline run">
          {d.runs.map((r: any) => <option key={r.id} value={r.id}>Run #{r.id} · {r.status}{r.finished ? ` · ${when(r.finished)}` : ""}</option>)}
        </select>
      </div>

      {d.run.errors?.length > 0 && (
        <div className="rounded-xl border px-4 py-3 text-sm" style={{ borderColor: "#f59e0b", background: "rgba(245,158,11,.1)" }}>
          <b>Run notes:</b> {d.run.errors.slice(0, 3).join(" · ")}
        </div>
      )}

      <Card title="Message flow">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button onClick={() => { if (idx != null && idx >= msgs.length - 1) setIdx(null); setPlaying(!playing); }}
            className="rounded-lg bg-fg px-3 py-1.5 text-sm font-semibold text-bg">{playing ? "⏸ Pause" : idx == null || idx >= msgs.length - 1 ? "▶ Replay run" : "▶ Resume"}</button>
          <button onClick={() => { setPlaying(false); setIdx((i) => Math.max(0, (i ?? 0) - 1)); }} className="rounded-lg border border-line px-3 py-1.5 text-sm" aria-label="Previous message">◀</button>
          <button onClick={() => { setPlaying(false); setIdx((i) => Math.min(msgs.length - 1, (i ?? -1) + 1)); }} className="rounded-lg border border-line px-3 py-1.5 text-sm" aria-label="Next message">▶</button>
          <button onClick={() => { setPlaying(false); setIdx(null); }} className="rounded-lg border border-line px-3 py-1.5 text-sm">Show all</button>
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className="rounded-lg border border-line bg-card px-2 py-1.5 text-sm" aria-label="Replay speed">
            <option value={0.5}>0.5×</option><option value={1}>1×</option><option value={3}>3×</option><option value={8}>8×</option>
          </select>
          <input type="range" min={0} max={Math.max(0, msgs.length - 1)} value={idx ?? msgs.length - 1}
            onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)); }} className="min-w-[160px] flex-1" aria-label="Scrub through messages" />
          <span className="num text-xs text-mute">{idx == null ? "all" : `${idx + 1} / ${msgs.length}`}</span>
        </div>

        <div className="overflow-x-auto">
          <svg viewBox="0 0 1080 520" className="min-w-[860px] w-full" role="img" aria-label="Agent communication graph">
            <defs>
              {[["a", "#94a3b8"], ["on", "var(--brand)"], ["err", "#f43f5e"]].map(([id, c]) => (
                <marker key={id} id={`arrow-${id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
                </marker>
              ))}
            </defs>
            {d.edges.map((e: any) => {
              const p = anchor(e.from, e.to);
              if (!p) return null;
              const on = edgeActive(e);
              const isFocus = !focus || e.from === focus || e.to === focus;
              const col = e.errors ? "#f43f5e" : on ? "var(--brand)" : "#94a3b8";
              return (
                <g key={`${e.from}>${e.to}`} opacity={on ? 1 : active ? 0.18 : isFocus ? 1 : 0.2}>
                  <path d={p.d} fill="none" stroke={col} strokeWidth={on ? 4 : Math.min(1.5 + e.count * 0.12, 3.5)} className={on ? "flow" : ""}
                    markerEnd={`url(#arrow-${e.errors ? "err" : on ? "on" : "a"})`} />
                  <g transform={`translate(${p.mid[0]} ${p.mid[1]})`}>
                    <rect x="-17" y="-10" width="34" height="20" rx="10" fill="var(--card)" stroke={col} strokeWidth="1.2" />
                    <text textAnchor="middle" y="4" fontSize="11" fontWeight="600" fill="currentColor">×{e.count}</text>
                  </g>
                </g>
              );
            })}
            {d.agents.map((a: any) => {
              const [x, y] = POS[a.id] || [0, 0];
              const k = KIND[a.kind];
              const on = nodeActive(a.id);
              return (
                <g key={a.id} transform={`translate(${x - W / 2} ${y - H / 2})`} onClick={() => setFocus(focus === a.id ? null : a.id)} style={{ cursor: "pointer" }}
                  opacity={focus && focus !== a.id && !active ? 0.55 : dim(!!on)}>
                  <rect width={W} height={H} rx="12" fill="var(--card)" stroke={on || focus === a.id ? "var(--brand)" : k.color} strokeWidth={on || focus === a.id ? 3 : 1.5} />
                  <rect width="6" height={H} rx="3" fill={k.color} />
                  <text x="16" y="22" fontSize="12.5" fontWeight="700" fill="currentColor">{a.name.length > 20 ? a.name.slice(0, 19) + "…" : a.name}</text>
                  <text x="16" y="40" fontSize="10.5" fill="var(--mute)">{k.label} · {a.stats.sent}↑ {a.stats.received}↓{a.stats.errors ? ` · ${a.stats.errors} err` : ""}</text>
                  {a.stats.errors > 0 && <circle cx={W - 8} cy="8" r="5" fill="#f43f5e" />}
                  {!a.stats.errors && a.stats.warnings > 0 && <circle cx={W - 8} cy="8" r="5" fill="#f59e0b" />}
                </g>
              );
            })}
            {active && a2 && (
              <g transform={`translate(${a2.mid[0]} ${a2.mid[1] - 30})`}>
                <rect x="-6" y="-14" width={Math.min(260, 12 + active.topic.length * 7.2)} height="24" rx="8" fill="var(--brand)" />
                <text x="2" y="3" fontSize="12" fontWeight="700" fill="#fff">{active.topic}</text>
              </g>
            )}
          </svg>
        </div>

        <div className="mt-3 min-h-[76px] rounded-lg border border-line p-3 text-sm" aria-live="polite">
          {active ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <b>{names[active.sender]}</b><span className="text-mute">→</span><b>{names[active.receiver]}</b>
                <span className="rounded-full border border-line px-2 py-0.5 text-xs">{active.topic}</span>
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: STATUS_COLOR[active.status] }} />
                {active.items != null && <span className="text-xs text-mute">{active.items} items</span>}
                {active.ms != null && <span className="text-xs text-mute">{dur(active.ms)}</span>}
              </div>
              <p className="mt-1">{active.summary}</p>
              {active.sample != null && <pre className="mt-2 max-h-28 overflow-auto rounded bg-line/50 p-2 text-xs">{typeof active.sample === "string" ? active.sample : JSON.stringify(active.sample, null, 1)}</pre>}
            </>
          ) : <p className="text-mute">Press <b>Replay run</b> to step through the messages in the order they happened, or click an agent to filter its conversations. Line thickness shows how many messages crossed it.</p>}
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-mute">
          {Object.entries(KIND).map(([k, v]) => <span key={k}><b style={{ color: v.color }}>■</b> {v.label}</span>)}
          <span>↑ sent · ↓ received</span><span><b style={{ color: "#f59e0b" }}>●</b> warning · <b style={{ color: "#f43f5e" }}>●</b> error</span>
        </div>
      </Card>

      <Card title={`Message log${focus ? ` · ${names[focus]}` : ""}`} right={focus ? <button onClick={() => setFocus(null)} className="text-xs text-mute underline">clear filter</button> : null} className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead><tr className="text-left text-xs uppercase text-mute"><th className="pb-2">#</th><th>+ time</th><th>From → To</th><th>Topic</th><th>Summary</th><th className="text-right">Items</th><th className="text-right">Took</th><th /></tr></thead>
          <tbody>
            {shown.map((m) => {
              const i = msgs.indexOf(m);
              const isActive = idx === i;
              return (
                <>
                  <tr key={m.seq} ref={(el) => { rowRefs.current[i] = el; }} onClick={() => { setPlaying(false); setIdx(i); setOpen(open === i ? null : i); }}
                    className="cursor-pointer border-t border-line align-top hover:bg-line/40" style={isActive ? { background: "var(--line)" } : undefined}>
                    <td className="num py-1.5 text-mute">{m.seq}</td>
                    <td className="num text-xs text-mute">+{(m.t / 1000).toFixed(1)}s</td>
                    <td className="whitespace-nowrap">{names[m.sender] || m.sender} <span className="text-mute">→</span> {names[m.receiver] || m.receiver}</td>
                    <td><span className="rounded-full border border-line px-2 py-0.5 text-xs">{m.topic}</span></td>
                    <td className="max-w-[360px]">{m.summary}</td>
                    <td className="num text-right">{m.items ?? ""}</td>
                    <td className="num text-right text-xs text-mute">{dur(m.ms)}</td>
                    <td><span className="inline-block h-2 w-2 rounded-full" style={{ background: STATUS_COLOR[m.status] }} title={m.status} /></td>
                  </tr>
                  {open === i && m.sample != null && (
                    <tr key={`${m.seq}-s`}><td colSpan={8} className="pb-2"><pre className="max-h-40 overflow-auto rounded bg-line/50 p-2 text-xs">{typeof m.sample === "string" ? m.sample : JSON.stringify(m.sample, null, 1)}</pre></td></tr>
                  )}
                </>
              );
            })}
            {shown.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-mute">No messages.</td></tr>}
          </tbody>
        </table>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {d.agents.map((a: any) => {
          const k = KIND[a.kind];
          return (
            <button key={a.id} onClick={() => setFocus(focus === a.id ? null : a.id)} className="rounded-xl border bg-card p-4 text-left hover:border-fg"
              style={{ borderColor: focus === a.id ? "var(--brand)" : "var(--line)", borderLeft: `5px solid ${k.color}` }}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold">{a.name}</span>
                <span className="rounded-full px-2 py-0.5 text-xs font-semibold" style={{ background: k.color + "26", color: k.color }}>{k.label}</span>
              </div>
              <div className="text-xs text-mute">{a.tech}</div>
              <p className="mt-2 text-sm">{a.role}</p>
              <div className="num mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-mute">
                <span>sent {a.stats.sent}</span><span>received {a.stats.received}</span><span>time {dur(a.stats.ms) || "–"}</span>
                {a.stats.warnings > 0 && <span style={{ color: "#f59e0b" }}>{a.stats.warnings} warning</span>}
                {a.stats.errors > 0 && <span style={{ color: "#f43f5e" }}>{a.stats.errors} error</span>}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
