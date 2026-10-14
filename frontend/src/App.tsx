import { useCallback, useEffect, useState } from "react";
import { analyze } from "./api";
import { Header, Hero, Verdict } from "./components/Top";
import PriceChart from "./components/PriceChart";
import { PillarCards, TechSummary } from "./components/Pillars";
import { Analyst, Fundamentals, Narrative, News, Risk, SmartMoney } from "./components/Panels";
import Compare from "./components/Compare";
import { Card, Section, Skeleton } from "./components/ui";

const ls = {
  get: (k: string, d: any) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set: (k: string, v: any) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ignore */ } },
};

export default function App() {
  const [ticker, setTicker] = useState<string>(ls.get("ticker", "AAPL"));
  const [profile, setProfile] = useState<string>(ls.get("profile", "balanced"));
  const [watch, setWatch] = useState<string[]>(ls.get("watchlist_v2", ["AAPL", "NVDA", "TSLA", "STX", "WDC"]));
  const [dark, setDark] = useState<boolean>(ls.get("dark", true));
  const [view, setView] = useState<"analyze" | "compare">("analyze");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { document.documentElement.classList.toggle("dark", dark); ls.set("dark", dark); }, [dark]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setData(await analyze(ticker, profile)); }
    catch (e: any) { setError(e.message || "Failed to load"); setData(null); }
    finally { setLoading(false); }
  }, [ticker, profile]);

  useEffect(() => { ls.set("ticker", ticker); ls.set("profile", profile); load(); }, [load]);

  const toggleWatch = () => {
    const next = watch.includes(ticker) ? watch.filter((t) => t !== ticker) : [...watch, ticker];
    setWatch(next); ls.set("watchlist_v2", next);
  };

  return (
    <div className="min-h-screen pb-16">
      <Header onSelect={(t: string) => { setTicker(t); setView("analyze"); }} profile={profile} setProfile={setProfile} onRefresh={load}
        asOf={data?.asOf} watchlist={watch} current={ticker} toggleWatch={toggleWatch} dark={dark} toggleDark={() => setDark(!dark)} view={view} setView={setView} />
      <main className="mx-auto max-w-7xl space-y-4 px-4 py-4">
        {view === "compare" ? <Compare profile={profile} initial={watch} /> : (
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
      <footer className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-card/95 px-4 py-2 text-center text-xs text-mute backdrop-blur">
        {data?.disclaimer || "Educational analysis only — not financial advice. Data may be delayed."}
      </footer>
    </div>
  );
}
