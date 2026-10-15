import { useEffect, useState } from "react";
import { adminOverview } from "../api";
import { Card, Skeleton } from "./ui";
import { when } from "./MyActivity";

export default function Admin() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<"users" | "feedback">("users");
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
