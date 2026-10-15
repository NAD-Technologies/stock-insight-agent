import { useEffect, useRef, useState } from "react";
import { createChart, CrosshairMode, IChartApi } from "lightweight-charts";
import { Card } from "./ui";

const TFS = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y"];
const OVERLAYS: [string, string, string, string][] = [
  ["sma20", "Short-term trend (20d)", "#fbbf24", "Average price over the last 20 days. Price above it = short-term strength."],
  ["sma50", "Medium-term trend (50d)", "#60a5fa", "Average price over the last 50 days."],
  ["sma200", "Long-term trend (200d)", "#c084fc", "Average price over the last 200 days. The classic long-term trend line."],
  ["bb", "Volatility band", "#94a3b8", "Bollinger bands: price usually stays inside; touching an edge means a stretched move."],
  ["vwap", "Day average (VWAP)", "#2dd4bf", "Volume-weighted average price for the day."],
  ["levels", "Support / resistance", "#cbd5e1", "S = price floors where buyers stepped in, R = ceilings where sellers did."],
  ["markers", "Buy / sell signals", "#f1f5f9", "Arrows where the indicators flagged a possible entry or exit."],
];
const UP = "#22c55e", DOWN = "#f43f5e";

function cutoff(tf: string): string {
  const d = new Date();
  if (tf === "5D") d.setDate(d.getDate() - 7);
  else if (tf === "1M") d.setMonth(d.getMonth() - 1);
  else if (tf === "6M") d.setMonth(d.getMonth() - 6);
  else if (tf === "YTD") return `${d.getFullYear()}-01-01`;
  else if (tf === "1Y") d.setFullYear(d.getFullYear() - 1);
  else return "0000";
  return d.toISOString().slice(0, 10);
}

export default function PriceChart({ chart }: { chart: any }) {
  const [tf, setTf] = useState<string>("6M");
  const [adv, setAdv] = useState(false);
  const [on, setOn] = useState<Record<string, boolean>>({ sma50: true, sma200: true });
  const main = useRef<HTMLDivElement>(null);
  const rsiEl = useRef<HTMLDivElement>(null);
  const macdEl = useRef<HTMLDivElement>(null);
  const intraday = tf === "1D";
  const showSub = adv && !intraday;
  const hasIntraday = (chart.intraday || []).length > 0;

  useEffect(() => {
    if (!main.current) return;
    const dark = document.documentElement.classList.contains("dark");
    const grid = dark ? "#222c3d" : "#dbe2ec";
    const base = {
      layout: { background: { color: "transparent" }, textColor: dark ? "#c4cddc" : "#334155", fontSize: 13 },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: dark ? "#3a475c" : "#b8c3d3" },
      timeScale: { borderColor: dark ? "#3a475c" : "#b8c3d3", timeVisible: intraday },
      crosshair: { mode: CrosshairMode.Normal },
    };
    const charts: IChartApi[] = [];
    const els: (HTMLDivElement | null)[] = [];
    const mk = (el: HTMLDivElement, h: number) => {
      const c = createChart(el, { ...base, height: h, width: el.clientWidth } as any);
      charts.push(c);
      els.push(el);
      return c;
    };

    const c = mk(main.current, 440);
    const cut = cutoff(tf);
    const sel = (a: any[]) => (a || []).filter((p) => String(p.time) >= cut);
    const candles = c.addCandlestickSeries({ upColor: UP, downColor: DOWN, wickUpColor: UP, wickDownColor: DOWN, borderVisible: false });
    const vol = c.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", color: "#64748b55" });
    c.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    if (intraday && hasIntraday) {
      const id = chart.intraday;
      candles.setData(id.map((p: any) => ({ time: p.time, open: p.open, high: p.high, low: p.low, close: p.close })));
      vol.setData(id.map((p: any) => ({ time: p.time, value: p.volume, color: p.close >= p.open ? UP + "66" : DOWN + "66" })));
      if (on.vwap) {
        c.addLineSeries({ color: "#14b8a6", lineWidth: 2, priceLineVisible: false })
          .setData(id.filter((p: any) => p.vwap != null).map((p: any) => ({ time: p.time, value: p.vwap })));
      }
    } else {
      const o = sel(chart.ohlcv);
      candles.setData(o);
      vol.setData(o.map((p: any) => ({ time: p.time, value: p.volume, color: p.close >= p.open ? UP + "66" : DOWN + "66" })));
      const line = (key: string, color: string, dash = false) =>
        c.addLineSeries({ color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, lineStyle: dash ? 2 : 0 })
          .setData(sel(chart.indicators[key]));
      ["sma20", "sma50", "sma200"].forEach((k, i) => { if (on[k]) line(k, OVERLAYS[i][2]); });
      if (on.bb) { line("bb_upper", "#94a3b8", true); line("bb_lower", "#94a3b8", true); }
      if (on.vwap) line("vwap", "#2dd4bf");
      if (on.markers) {
        candles.setMarkers(sel(chart.markers).map((m: any) => ({
          time: m.time,
          position: m.type === "buy" ? "belowBar" : "aboveBar",
          shape: m.type === "buy" ? "arrowUp" : "arrowDown",
          color: m.type === "buy" ? UP : DOWN,
          text: m.label,
        })));
      }
    }
    if (on.levels) {
      (chart.levels?.support || []).forEach((p: number) => candles.createPriceLine({ price: p, color: UP + "bb", lineStyle: 2, lineWidth: 2, title: "Support" }));
      (chart.levels?.resistance || []).forEach((p: number) => candles.createPriceLine({ price: p, color: DOWN + "bb", lineStyle: 2, lineWidth: 2, title: "Resistance" }));
    }
    c.timeScale().fitContent();

    if (showSub) {
      if (rsiEl.current) {
        const r = mk(rsiEl.current, 110);
        const s = r.addLineSeries({ color: "#c084fc", lineWidth: 2, priceLineVisible: false });
        s.setData(sel(chart.indicators.rsi));
        s.createPriceLine({ price: 70, color: DOWN + "99", lineStyle: 2, lineWidth: 1, title: "Overbought" });
        s.createPriceLine({ price: 30, color: UP + "99", lineStyle: 2, lineWidth: 1, title: "Oversold" });
        r.timeScale().fitContent();
      }
      if (macdEl.current) {
        const m = mk(macdEl.current, 110);
        m.addHistogramSeries({ priceLineVisible: false })
          .setData(sel(chart.indicators.macd_hist).map((p: any) => ({ ...p, color: p.value >= 0 ? UP + "aa" : DOWN + "aa" })));
        m.addLineSeries({ color: "#60a5fa", lineWidth: 2, priceLineVisible: false }).setData(sel(chart.indicators.macd));
        m.addLineSeries({ color: "#fbbf24", lineWidth: 2, priceLineVisible: false }).setData(sel(chart.indicators.macd_signal));
        m.timeScale().fitContent();
      }
      // keep the sub-panes' visible range in sync with the main chart
      c.timeScale().subscribeVisibleLogicalRangeChange((rg) => {
        if (rg) charts.slice(1).forEach((x) => x.timeScale().setVisibleLogicalRange(rg));
      });
    }
    const onResize = () => charts.forEach((x, i) => x.applyOptions({ width: els[i]?.clientWidth || 600 }));
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      charts.forEach((x) => x.remove());
    };
  }, [chart, tf, on, adv]);

  return (
    <Card
      title="Price chart"
      right={
        <div className="flex flex-wrap gap-1">
          {TFS.map((t) => (
            <button key={t} onClick={() => setTf(t)} disabled={t === "1D" && !hasIntraday}
              className={`rounded px-2 py-1 text-xs font-medium disabled:opacity-30 ${tf === t ? "bg-fg text-bg" : "text-mute hover:text-fg"}`}>{t}</button>
          ))}
        </div>
      }
    >
      <div className="mb-1 flex items-center gap-4 text-xs text-mute">
        <span><b style={{ color: UP }}>■</b> Price up</span>
        <span><b style={{ color: DOWN }}>■</b> Price down</span>
        <span>Bars at the bottom = trading volume</span>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-mute">Lines:</span>
        {OVERLAYS.filter(([k]) => !(k === "vwap" && !intraday)).map(([k, label, col, hint]) => (
          <button key={k} onClick={() => setOn({ ...on, [k]: !on[k] })} title={hint} aria-pressed={!!on[k]}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${on[k] ? "border-fg" : "border-line text-mute"}`}>
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: col, opacity: on[k] ? 1 : 0.4 }} />{label}
          </button>
        ))}
        {!intraday && (
          <button onClick={() => setAdv(!adv)} className={`ml-auto rounded-full border px-2.5 py-1 text-xs font-medium ${adv ? "border-fg" : "border-line text-mute"}`}>
            {adv ? "Hide" : "Show"} momentum (RSI / MACD)
          </button>
        )}
      </div>
      <div ref={main} />
      {showSub && (
        <>
          <div className="mt-2 text-xs text-mute"><b className="text-fg">RSI</b> — above 70 = may be overheated, below 30 = may be oversold</div>
          <div ref={rsiEl} />
          <div className="mt-2 text-xs text-mute"><b className="text-fg">MACD</b> — green bars = momentum rising, red bars = momentum fading</div>
          <div ref={macdEl} />
        </>
      )}
    </Card>
  );
}
