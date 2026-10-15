import { useCallback, useEffect, useState } from "react";
import { analyze, getPrefs, putPrefs } from "./api";
import { inferCurrency, setCurrency } from "./lib/format";
import { Header, Hero, Verdict } from "./components/Top";
import PriceChart from "./components/PriceChart";
import { PillarCards, TechSummary } from "./components/Pillars";
import { Analyst, Fundamentals, Narrative, News, Risk, SmartMoney } from "./components/Panels";
import Compare from "./components/Compare";
import { Card, Section, Skeleton } from "./components/ui";
import AuthGate from "./components/AuthGate";
import MyActivity, { GuestNotice } from "./components/MyActivity";
import Admin from "./components/Admin";
import FeedbackModal from "./components/FeedbackModal";
import { loadSession, saveSession, validate, Session } from "./auth";

const ls = {
  get: (k: string, d: any) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set: (k: string, v: any) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ignore */ } },
};

export default function App() {
  const [session, setSession] = useState<Session | null>(loadSession);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (session?.mode === "google") validate(session.token).then((u) => {
      if (u === null) { saveSession(null); setSession(null); }
      else if (u) { const next: Session = { mode: "google", token: session.token, user: u }; saveSession(next); setSession(next); }
      setChecked(true);
    });
    else setChecked(true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = useCallback((s: Session) => { saveSession(s); setSession(s); }, []);
  const signOut = () => {
    if (session?.mode === "google") try { (window as any).google?.accounts?.id?.disableAutoSelect(); } catch { /* ignore */ }
    saveSession(null); setSession(null);
  };

  if (!checked) return null;
  if (!session) return <AuthGate onSession={pick} />;
  return <Dashboard key={session.mode === "google" ? session.user.id : "guest"} session={session} onSignOut={signOut} />;
}

function Dashboard({ session, onSignOut }: { session: Session; onSignOut: () => void }) {
  const wlKey = session.mode === "google" ? `watchlist_v2:${session.user.id}` : "watchlist_v2";
  const [ticker, setTicker] = useState<string>(ls.get("ticker", "AAPL"));
  const [profile, setProfile] = useState<string>(ls.get("profile", "balanced"));
  const [watch, setWatch] = useState<string[]>(ls.get(wlKey, ["AAPL", "NVDA", "TSLA", "RELIANCE.NS", "TCS.NS", "INFY.NS"]));
  const [dark, setDark] = useState<boolean>(ls.get("dark", true));
  const [view, setView] = useState<"analyze" | "compare" | "me" | "admin">("analyze");
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [hideBanner, setHideBanner] = useState(false);
  const guest = session.mode !== "google";
  const [synced, setSynced] = useState(guest);

  // Signed-in users: pull saved preferences (last ticker, profile, watchlist, theme) once, then keep them synced.
  useEffect(() => {
    if (guest) return;
    getPrefs().then(({ prefs }) => {
      if (prefs) {
        if (prefs.ticker) setTicker(prefs.ticker);
        if (prefs.profile) setProfile(prefs.profile);
        if (Array.isArray(prefs.watchlist) && prefs.watchlist.length) setWatch(prefs.watchlist);
        if (typeof prefs.dark === "boolean") setDark(prefs.dark);
      }
    }).catch(() => { /* offline: fall back to local values */ }).finally(() => setSynced(true));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (guest || !synced) return;
    const t = setTimeout(() => { putPrefs({ ticker, profile, watchlist: watch, dark }).catch(() => {}); }, 800);
    return () => clearTimeout(t);
  }, [guest, synced, ticker, profile, watch, dark]);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { document.documentElement.classList.toggle("dark", dark); ls.set("dark", dark); }, [dark]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const d = await analyze(ticker, profile); setCurrency(d?.quote?.currency || inferCurrency(d?.ticker || ticker)); setData(d); }
    catch (e: any) { setError(e.message || "Failed to load"); setData(null); }
    finally { setLoading(false); }
  }, [ticker, profile]);

  useEffect(() => { ls.set("ticker", ticker); ls.set("profile", profile); load(); }, [load]);

  const toggleWatch = () => {
    const next = watch.includes(ticker) ? watch.filter((t) => t !== ticker) : [...watch, ticker];
    setWatch(next); ls.set(wlKey, next);
  };

  return (
    <div className="min-h-screen pb-16">
      <Header onSelect={(t: string) => { setTicker(t); setView("analyze"); }} profile={profile} setProfile={setProfile} onRefresh={load}
        asOf={data?.asOf} watchlist={watch} current={ticker} toggleWatch={toggleWatch} dark={dark} toggleDark={() => setDark(!dark)} view={view} setView={setView} session={session} onSignOut={onSignOut} onFeedback={() => setFeedbackOpen(true)} />
      <main className="mx-auto max-w-7xl space-y-4 px-4 py-4">
        {guest && !hideBanner && view !== "me" && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-card px-4 py-3 text-sm">
            <span>👋 You're a guest, so you're seeing <b>generic market info</b>. <b>Log in</b> for a personalised view of the tickers you explore.</span>
            <span className="flex gap-2">
              <button onClick={onSignOut} className="rounded-lg bg-fg px-3 py-1.5 text-xs font-semibold text-bg">Log in</button>
              <button onClick={() => setHideBanner(true)} className="rounded-lg border border-line px-3 py-1.5 text-xs">Dismiss</button>
            </span>
          </div>
        )}
        {view === "me" ? <MyActivity session={session} watchlist={watch} profile={profile} onSignUp={onSignOut} onSelect={(t: string) => { setTicker(t); setView("analyze"); }} />
          : view === "admin" ? (session.mode === "google" && session.user.isAdmin ? <Admin /> : <GuestNotice onSignUp={onSignOut} />)
          : view === "compare" ? <Compare profile={profile} initial={watch} /> : (
          <>
            {loading && <><Skeleton h={160} /><Skeleton h={320} /><Skeleton h={420} /></>}
            {!loading && error && (
              <Card title="Could not analyze"><p className="text-sm text-bear">{error}</p>
                <button onClick={load} className="mt-3 rounded-lg border border-line px-3 py-1.5 text-sm">Retry</button></Card>
            )}
            {!loading && data && (
              <>
                <Section title="Overview"><Hero d={data} /></Section>
                <Section title="Verdict"><Verdict d={data} /></Section>
                <Section title="Chart"><PriceChart chart={data.chart} /></Section>
                <Section title="Pillars"><PillarCards d={data} /></Section>
                <Section title="Technical summary"><TechSummary t={data.technical} /></Section>
                <Section title="Fundamentals"><Fundamentals f={data.fundamental} price={data.quote.price} /></Section>
                <Section title="Analysts"><Analyst a={data.analyst} price={data.quote.price} /></Section>
                <Section title="News"><News s={data.sentiment} /></Section>
                <Section title="Smart money"><SmartMoney s={data.sentiment} /></Section>
                <Section title="Risk"><Risk r={data.risk} /></Section>
                <Section title="AI analyst summary"><Narrative n={data.narrative} /></Section>
                <p className="text-xs text-mute">Sources: {(data.dataSources || []).join(", ")}</p>
              </>
            )}
          </>
        )}
      </main>
      {feedbackOpen && <FeedbackModal session={session} onClose={() => setFeedbackOpen(false)} />}
      <footer className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-card/95 px-4 py-2 text-center text-xs text-mute backdrop-blur">
        {data?.disclaimer || "Educational analysis only — not financial advice. Data may be delayed."} · © NAD Technologies
      </footer>
    </div>
  );
}
