import { useEffect, useState } from "react";
import { myActivity } from "../api";
import { Card, Skeleton } from "./ui";

export const when = (ts: number) => new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export function GuestNotice({ onSignUp }: { onSignUp: () => void }) {
  return (
    <div className="rounded-xl border border-line bg-card p-5">
      <h3 className="text-base font-semibold">You're browsing as a guest</h3>
      <p className="mt-1 text-sm text-mute">
        Guests see generic market information only. Sign up with Google, it's free, to get a personalised view: the tickers you've
        explored, your most-viewed stocks, and a watchlist saved to your account.
      </p>
      <button onClick={onSignUp} className="mt-3 rounded-lg bg-fg px-4 py-2 text-sm font-semibold text-bg">Sign up for a personalised view</button>
    </div>
  );
}

export default function MyActivity({ session, onSelect, onSignUp, watchlist }: any) {
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
