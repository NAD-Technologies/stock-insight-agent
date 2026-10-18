import { DirTag, tone } from "./MarketPulse";

/** Module A item A9: the sector context for the stock being viewed, with a warning when stock and sector disagree. */
export default function SectorOverlay({ o, onOpen }: { o: any; onOpen: (id: string) => void }) {
  if (!o?.themes?.length) return null;
  return (
    <div className="space-y-2">
      {o.flag && (
        <div className="rounded-xl border px-4 py-3 text-sm" style={{ borderColor: o.flag.level === "warn" ? "#f59e0b" : "var(--line)", background: o.flag.level === "warn" ? "rgba(245,158,11,.12)" : "var(--card)" }}>
          <b>{o.flag.level === "warn" ? "⚠ " : "ℹ "}</b>{o.flag.text}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-xs font-medium uppercase tracking-wide text-mute">Sector outlook</span>
        {o.themes.map((t: any) => {
          const x = t.horizons["1M"], c = tone(x.score);
          return (
            <button key={t.theme} onClick={() => onOpen(t.theme)} title={`${t.name}: 1W ${t.horizons["1W"].direction}, 1M ${x.direction}, 3M ${t.horizons["3M"].direction}`}
              className="flex items-center gap-2 rounded-full border border-line px-3 py-1 hover:border-fg" style={{ background: c.bg }}>
              <span className="font-medium">{t.name}</span><span className="num text-mute">{x.score}</span><DirTag d={x.direction} small />
            </button>
          );
        })}
      </div>
    </div>
  );
}
