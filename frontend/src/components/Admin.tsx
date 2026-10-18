import { useEffect, useState } from "react";
import { adminOverview, adminPipeline } from "../api";
import { Card, Skeleton } from "./ui";
import { RegionBar, when } from "./MyActivity";

function Bars({ values, labels, color = "var(--brand)" }: { values: number[]; labels: string[]; color?: string }) {
  const max = Math.max(1, ...values);
  return (
    <div>
      <div className="flex h-28 items-end gap-1">
        {values.map((v, i) => (
          <div key={i} className="flex flex-1 flex-col items-center justify-end" title={`${labels[i]}: ${v}`}>
            <span className="num mb-0.5 text-[10px] text-mute">{v || ""}</span>
            <div className="w-full rounded-t" style={{ height: `${Math.max(v ? 6 : 2, (v / max) * 84)}px`, background: color, opacity: v ? 1 : 0.25 }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-mute"><span>{labels[0]?.slice(5)}</span><span>{labels[labels.length - 1]?.slice(5)}</span></div>
    </div>
  );
}

export default function Admin() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<"users" | "feedback">("users");
  const [pipe, setPipe] = useState<any>(null);
  useEffect(() => { adminPipeline().then(setPipe).catch(() => setPipe(null)); }, []);
  useEffect(() => { adminOverview().then(setD).catch((e) => setErr(e.message)); }, []);

  if (err) return <Card title="Admin"><p className="text-sm text-bear">{err}</p></Card>;
  if (!d) return <Skeleton h={300} />;
  const s = d.stats;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[["Users", s.users], ["Active (24h)", s.activeToday], ["Ticker lookups", s.totalViews], ["Feedback", s.feedback], ["Avg rating", s.avgRating ?? "–"]].map(([k, v]: any) => (
          <div key={k} className="rounded-xl border border-line bg-card p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-mute">{k}</div>
            <div className="num mt-1 text-2xl font-bold">{v}</div>
          </div>
        ))}
      </div>
      {d.metrics && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[["New users (7d)", d.metrics.newUsers7d], ["Returning users", d.metrics.returningRate == null ? "–" : `${d.metrics.returningRate}%`],
              ["Tickers / user", d.metrics.avgTickersPerUser ?? "–"], ["Lookups / user", d.metrics.avgLookupsPerUser ?? "–"]].map(([k, v]: any) => (
              <div key={k} className="rounded-xl border border-line bg-card p-4">
                <div className="text-xs font-medium uppercase tracking-wide text-mute">{k}</div>
                <div className="num mt-1 text-2xl font-bold">{v}</div>
              </div>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Sign-ups (14 days)"><Bars values={d.metrics.signupsByDay} labels={d.metrics.days} /></Card>
            <Card title="Daily active users (14 days)"><Bars values={d.metrics.activeByDay} labels={d.metrics.days} color="#60a5fa" /></Card>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Market mix (all lookups)"><RegionBar split={d.metrics.regionSplit} /></Card>
            <Card title="Most active users">
              <ul className="space-y-1.5 text-sm">
                {d.metrics.topUsers.map((u: any) => <li key={u.email} className="flex justify-between"><span className="truncate">{u.name}</span><span className="num text-mute">{u.lookups}</span></li>)}
                {d.metrics.topUsers.length === 0 && <li className="text-mute">No users yet.</li>}
              </ul>
            </Card>
            <Card title="Feedback ratings">
              <ul className="space-y-1 text-sm">
                {[5, 4, 3, 2, 1].map((n) => {
                  const v = d.metrics.ratingDist[String(n)] || 0, tot = Object.values(d.metrics.ratingDist as Record<string, number>).reduce((a, b) => a + b, 0) || 1;
                  return <li key={n} className="flex items-center gap-2"><span className="w-6 text-mute">{n}★</span>
                    <div className="h-2 flex-1 rounded-full bg-line"><div className="h-2 rounded-full" style={{ width: `${(v / tot) * 100}%`, background: "#f59e0b" }} /></div>
                    <span className="num w-5 text-right text-mute">{v}</span></li>;
                })}
              </ul>
            </Card>
          </div>
        </>
      )}
      {pipe && (
        <Card title="Sector Pulse pipeline" className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead><tr className="text-left text-xs uppercase text-mute"><th className="pb-2">Run</th><th>Status</th><th>Finished</th><th>Themes</th><th>Headlines</th><th>Stocks refreshed</th><th>Seconds</th></tr></thead>
            <tbody>
              {pipe.runs.map((r: any) => (
                <tr key={r.id} className="border-t border-line" title={(r.stats?.errors || []).join("\n")}>
                  <td className="py-1.5">#{r.id}</td>
                  <td style={{ color: r.status === "ok" ? "#22c55e" : r.status === "degraded" ? "#f59e0b" : "#f43f5e" }}>{r.status}</td>
                  <td className="text-xs text-mute">{r.finished ? when(r.finished) : "running…"}</td>
                  <td className="num">{r.stats?.themes ?? "–"}</td><td className="num">{r.stats?.news?.headlines ?? "–"}</td>
                  <td className="num">{r.stats?.stockScores?.refreshed ?? "–"}</td><td className="num">{r.stats?.seconds ?? "–"}</td>
                </tr>
              ))}
              {pipe.runs.length === 0 && <tr><td colSpan={7} className="py-4 text-center text-mute">The pipeline has not run yet.</td></tr>}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-mute">Predictions graded: {pipe.accuracy.overall.n} · waiting: {pipe.accuracy.pending}. Hover a run to see its errors.</p>
        </Card>
      )}
      {s.topTickers.length > 0 && (
        <Card title="Most viewed tickers (all users)">
          <div className="flex flex-wrap gap-2">{s.topTickers.map((t: any) => <span key={t.ticker} className="rounded-full border border-line px-3 py-1 text-xs"><b>{t.ticker}</b> <span className="text-mute">{t.views}×</span></span>)}</div>
        </Card>
      )}
      <div className="flex gap-2">
        {(["users", "feedback"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === t ? "bg-fg text-bg" : "border border-line text-mute"}`}>
            {t === "users" ? `Users (${d.users.length})` : `Feedback (${d.feedback.length})`}
          </button>
        ))}
      </div>
      {tab === "users" ? (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead><tr className="text-left text-xs uppercase text-mute"><th className="pb-2">User</th><th>Tickers</th><th>Lookups</th><th>Top tickers</th><th>Logins</th><th>Last seen</th></tr></thead>
            <tbody>
              {d.users.map((u: any) => (
                <tr key={u.id} className="border-t border-line">
                  <td className="py-2"><div className="flex items-center gap-2">
                    {u.picture && <img src={u.picture} alt="" referrerPolicy="no-referrer" className="h-6 w-6 rounded-full" />}
                    <div><div className="font-medium">{u.name}</div><div className="text-xs text-mute">{u.email}</div></div></div></td>
                  <td className="num">{u.distinctTickers}</td><td className="num">{u.totalViews}</td>
                  <td className="text-xs">{u.topTickers.join(", ") || "–"}</td>
                  <td className="num">{u.login_count}</td><td className="text-xs text-mute">{when(u.last_seen)}</td>
                </tr>
              ))}
              {d.users.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-mute">No users yet.</td></tr>}
            </tbody>
          </table>
        </Card>
      ) : (
        <div className="space-y-3">
          {d.feedback.map((f: any) => (
            <div key={f.id} className="rounded-xl border border-line bg-card p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span><b>{f.name || "Guest"}</b> {f.email && <span className="text-mute">· {f.email}</span>}</span>
                <span className="text-xs text-mute">{f.rating ? "★".repeat(f.rating) + "☆".repeat(5 - f.rating) + " · " : ""}{when(f.created_at)}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm">{f.message}</p>
            </div>
          ))}
          {d.feedback.length === 0 && <p className="text-sm text-mute">No feedback yet.</p>}
        </div>
      )}
    </div>
  );
}
