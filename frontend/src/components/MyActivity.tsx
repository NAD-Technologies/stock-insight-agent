import { useEffect, useState } from "react";
import { compare, myActivity, watchlistSummary } from "../api";
import { Badge, Card, Skeleton } from "./ui";
import { inferCurrency, pct, usd } from "../lib/format";

export const when = (ts: number) => new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export function GuestNotice({ onSignUp }: { onSignUp: () => void }) {
  return (
    <div className="rounded-xl border border-line bg-card p-5">
      <h3 className="text-base font-semibold">You're browsing as a guest</h3>
      <p className="mt-1 text-sm text-mute">
        Guests see generic market information only. Log in with Google, it's free, to get a personalised view: the tickers you've
        explored, your most-viewed stocks, and a watchlist saved to your account.
      </p>
      <button onClick={onSignUp} className="mt-3 rounded-lg bg-fg px-4 py-2 text-sm font-semibold text-bg">Log in for a personalised view</button>
    </div>
  );
}

function Spark({ data, up }: { data: number[]; up: boolean }) {
  if (!data || data.length < 2) return <div className="h-9" />;
  const min = Math.min(...data), max = Math.max(...data), w = 120, h = 36;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - 2 - ((v - min) / (max - min || 1)) * (h - 4)}`).join(" ");
  return <svg viewBox={`0 0 ${w} ${h}`} className="h-9 w-full" preserveAspectRatio="none"><polyline points={pts} fill="none" stroke={up ? "#22c55e" : "#f43f5e"} strokeWidth="2" strokeLinejoin="round" /></svg>;
}

function Watchlist({ tickers, profile, onSelect }: { tickers: string[]; profile: string; onSelect: (t: string) => void }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [ratings, setRatings] = useState<Record<string, any>>({});
  const key = tickers.join(",");

  useEffect(() => {
    let dead = false;
    setRows(null);
    if (!tickers.length) { setRows([]); return; }
    watchlistSummary(tickers).then((r) => { if (!dead) setRows(r.results); }).catch(() => { if (!dead) setRows([]); });
    // Ratings come from the full engine, so fill them in progressively. /api/compare needs 2-4 tickers per call.
    (async () => {
      const chunks: string[][] = [];
      for (let i = 0; i < tickers.length; i += 4) chunks.push(tickers.slice(i, i + 4));
      if (chunks.length > 1 && chunks[chunks.length - 1].length < 2) chunks[chunks.length - 2].push(...chunks.pop()!);
      for (const ch of chunks) {
        if (dead || ch.length < 2) continue;
        try {
          const r = await compare(ch, profile);
          if (!dead) setRatings((p) => ({ ...p, ...Object.fromEntries(r.results.filter((x: any) => x.rating).map((x: any) => [x.ticker, x])) }));
        } catch { /* ignore */ }
      }
    })();
    return () => { dead = true; };
  }, [key, profile]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!rows) return <Skeleton h={160} />;
  const ok = rows.filter((r) => r.price != null && r.changePct != null);
  const sorted = [...ok].sort((a, b) => b.changePct - a.changePct);
  const gain = sorted[0], loss = sorted[sorted.length - 1];
  return (
    <div className="space-y-3">
      {ok.length >= 2 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {[["Top gainer today", gain], ["Biggest drop today", loss]].map(([label, r]: any) => (
            <button key={label} onClick={() => onSelect(r.ticker)} className="rounded-xl border border-line bg-card p-4 text-left hover:border-fg">
              <div className="text-xs font-medium uppercase tracking-wide text-mute">{label}</div>
              <div className="mt-1 flex items-baseline justify-between"><span className="text-lg font-bold">{r.ticker}</span>
                <span className="num text-lg font-bold" style={{ color: r.changePct >= 0 ? "#22c55e" : "#f43f5e" }}>{pct(r.changePct)}</span></div>
              <div className="num text-sm text-mute">{usd(r.price, 2, r.currency || inferCurrency(r.ticker))}</div>
            </button>
          ))}
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((r) => {
          const rt = ratings[r.ticker];
          return (
            <button key={r.ticker} onClick={() => onSelect(r.ticker)} className="rounded-xl border border-line bg-card p-4 text-left hover:border-fg">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0"><div className="font-bold">{r.ticker}</div><div className="truncate text-xs text-mute">{r.name || (r.error && "Unavailable")}</div></div>
                {rt ? <Badge text={rt.rating} /> : !r.error && <span className="text-xs text-mute">rating…</span>}
              </div>
              {r.error ? null : (
                <>
                  <div className="mt-2 flex items-baseline justify-between">
                    <span className="num text-xl font-bold">{usd(r.price, 2, r.currency || inferCurrency(r.ticker))}</span>
                    <span className="num text-sm font-semibold" style={{ color: (r.changePct ?? 0) >= 0 ? "#22c55e" : "#f43f5e" }}>{pct(r.changePct)}</span>
                  </div>
                  <Spark data={r.spark} up={(r.changePct ?? 0) >= 0} />
                </>
              )}
            </button>
          );
        })}
        {rows.length === 0 && <p className="text-sm text-mute">Your watchlist is empty. Open a stock and click "add".</p>}
      </div>
    </div>
  );
}

export function RegionBar({ split }: { split: { India: number; Global: number } }) {
  const total = (split?.India || 0) + (split?.Global || 0);
  if (!total) return <p className="text-sm text-mute">Explore some stocks to see your mix.</p>;
  const i = Math.round(((split.India || 0) / total) * 100);
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-line">
        <div style={{ width: `${i}%`, background: "var(--brand)" }} /><div style={{ width: `${100 - i}%`, background: "#60a5fa" }} />
      </div>
      <div className="mt-2 flex justify-between text-xs text-mute">
        <span><b style={{ color: "var(--brand)" }}>●</b> India (₹) {i}%</span><span><b style={{ color: "#60a5fa" }}>●</b> Global ($) {100 - i}%</span>
      </div>
    </div>
  );
}

export default function MyActivity({ session, onSelect, onSignUp, watchlist, profile }: any) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const signedIn = session.mode === "google";

  useEffect(() => { if (signedIn) myActivity().then(setD).catch((e) => setErr(e.message)); }, [signedIn]);

  if (!signedIn) return <GuestNotice onSignUp={onSignUp} />;
  if (err) return <Card title="My view"><p className="text-sm text-bear">{err}</p></Card>;
  if (!d) return <Skeleton h={240} />;

  const max = Math.max(1, ...d.tickers.map((t: any) => t.count));
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {[["Tickers explored", d.distinctTickers], ["Total lookups", d.totalViews], ["On your watchlist", watchlist.length]].map(([k, v]: any) => (
          <div key={k} className="rounded-xl border border-line bg-card p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-mute">{k}</div>
            <div className="num mt-1 text-3xl font-bold">{v}</div>
          </div>
        ))}
      </div>
      <Card title="Your watchlist today"><Watchlist tickers={watchlist} profile={profile} onSelect={onSelect} /></Card>
      <Card title="Your market mix"><RegionBar split={d.regionSplit} /></Card>
      <Card title="Your most viewed tickers">
        {d.tickers.length === 0 ? <p className="text-sm text-mute">Nothing yet. Search a ticker and it will show up here.</p> : (
          <ul className="space-y-2">
            {d.tickers.slice(0, 10).map((t: any) => (
              <li key={t.ticker} className="flex items-center gap-3 text-sm">
                <button onClick={() => onSelect(t.ticker)} className="w-28 text-left font-semibold hover:underline">{t.ticker}</button>
                <div className="h-2 flex-1 rounded-full bg-line"><div className="h-2 rounded-full" style={{ width: `${(t.count / max) * 100}%`, background: "var(--brand)" }} /></div>
                <span className="num w-16 text-right text-mute">{t.count}×</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Recently viewed">
        <div className="flex flex-wrap gap-2">
          {d.recent.map((t: any) => (
            <button key={t.ticker} onClick={() => onSelect(t.ticker)} className="rounded-full border border-line px-3 py-1 text-xs hover:border-fg" title={when(t.last_viewed)}>{t.ticker}</button>
          ))}
          {d.recent.length === 0 && <span className="text-sm text-mute">No history yet.</span>}
        </div>
      </Card>
    </div>
  );
}
