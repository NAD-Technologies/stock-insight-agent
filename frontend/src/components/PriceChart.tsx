import { useEffect, useRef, useState } from "react";
import { createChart, CrosshairMode, IChartApi } from "lightweight-charts";
import { Card } from "./ui";

const TFS = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y"];
const OVERLAYS: [string, string, string][] = [
  ["sma20", "SMA 20", "#f59e0b"], ["sma50", "SMA 50", "#3b82f6"], ["sma200", "SMA 200", "#a855f7"],
  ["bb", "Bollinger", "#64748b"], ["vwap", "VWAP", "#14b8a6"], ["levels", "S/R", "#94a3b8"], ["markers", "Signals", "#e5e9f0"],
];

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
  const [on, setOn] = useState<Record<string, boolean>>({ sma20: true, sma50: true, sma200: true, levels: true, markers: true });
  const main = useRef<HTMLDivElement>(null);
  const rsiEl = useRef<HTMLDivElement>(null);
  const macdEl = useRef<HTMLDivElement>(null);
  const intraday = tf === "1D";
  const hasIntraday = (chart.intraday || []).length > 0;

  useEffect(() => {
    if (!main.current) return;
    const dark = document.documentElement.classList.contains("dark");
    const grid = dark ? "#1b2433" : "#eef0f3";
    const base = {
      layout: { background: { color: "transparent" }, textColor: dark ? "#8b97ab" : "#64748b" },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: "#232d3f" },
      timeScale: { borderColor: "#232d3f", timeVisible: intraday },
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

    const c = mk(main.current, 380);
    const cut = cutoff(tf);
    const sel = (a: any[]) => (a || []).filter((p) => String(p.time) >= cut);
    const candles = c.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626", borderVisible: false });
    const vol = c.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", color: "#64748b55" });
    c.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    if (intraday && hasIntraday) {
      const id = chart.intraday;
      candles.setData(id.map((p: any) => ({ time: p.time, open: p.open, high: p.high, low: p.low, close: p.close })));
      vol.setData(id.map((p: any) => ({ time: p.time, value: p.volume, color: p.close >= p.open ? "#16a34a55" : "#dc262655" })));
      if (on.vwap) {
        c.addLineSeries({ color: "#14b8a6", lineWidth: 2, priceLineVisible: false })
          .setData(id.filter((p: any) => p.vwap != null).map((p: any) => ({ time: p.time, value: p.vwap })));
      }
    } else {
      const o = sel(chart.ohlcv);
      candles.setData(o);
      vol.setData(o.map((p: any) => ({ time: p.time, value: p.volume, color: p.close >= p.open ? "#16a34a55" : "#dc262655" })));
      const line = (key: string, color: string, dash = false) =>
        c.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, lineStyle: dash ? 2 : 0 })
          .setData(sel(chart.indicators[key]));
      ["sma20", "sma50", "sma200"].forEach((k, i) => { if (on[k]) line(k, OVERLAYS[i][2]); });
      if (on.bb) { line("bb_upper", "#64748b", true); line("bb_lower", "#64748b", true); }
      if (on.vwap) line("vwap", "#14b8a6");
      if (on.markers) {
        candles.setMarkers(sel(chart.markers).map((m: any) => ({
          time: m.time,
          position: m.type === "buy" ? "belowBar" : "aboveBar",
          shape: m.type === "buy" ? "arrowUp" : "arrowDown",
          color: m.type === "buy" ? "#16a34a" : "#dc2626",
          text: m.label,
        })));
      }
    }
    if (on.levels) {
      (chart.levels?.support || []).forEach((p: number) => candles.createPriceLine({ price: p, color: "#16a34a99", lineStyle: 2, lineWidth: 1, title: "S" }));
      (chart.levels?.resistance || []).forEach((p: number) => candles.createPriceLine({ price: p, color: "#dc262699", lineStyle: 2, lineWidth: 1, title: "R" }));
    }
    c.timeScale().fitContent();

    if (!intraday) {
      if (rsiEl.current) {
        const r = mk(rsiEl.current, 110);
        const s = r.addLineSeries({ color: "#a855f7", lineWidth: 1, priceLineVisible: false });
        s.setData(sel(chart.indicators.rsi));
        s.createPriceLine({ price: 70, color: "#dc262680", lineStyle: 2, lineWidth: 1, title: "" });
        s.createPriceLine({ price: 30, color: "#16a34a80", lineStyle: 2, lineWidth: 1, title: "" });
        r.timeScale().fitContent();
      }
      if (macdEl.current) {
        const m = mk(macdEl.current, 110);
        m.addHistogramSeries({ priceLineVisible: false })
          .setData(sel(chart.indicators.macd_hist).map((p: any) => ({ ...p, color: p.value >= 0 ? "#16a34a99" : "#dc262699" })));
        m.addLineSeries({ color: "#3b82f6", lineWidth: 1, priceLineVisible: false }).setData(sel(chart.indicators.macd));
        m.addLineSeries({ color: "#f59e0b", lineWidth: 1, priceLineVisible: false }).setData(sel(chart.indicators.macd_signal));
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
  }, [chart, tf, on]);

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
      <div className="mb-2 flex flex-wrap gap-2">
        {OVERLAYS.map(([k, label, col]) => (
          <button key={k} onClick={() => setOn({ ...on, [k]: !on[k] })}
            className={`rounded-full border px-2 py-0.5 text-xs ${on[k] ? "border-transparent text-bg" : "border-line text-mute"}`}
            style={on[k] ? { background: col } : undefined}>{label}</button>
        ))}
      </div>
      <div ref={main} />
      {!intraday && (
        <>
          <div className="mt-1 text-xs text-mute">RSI (14)</div>
          <div ref={rsiEl} />
          <div className="mt-1 text-xs text-mute">MACD (12,26,9)</div>
          <div ref={macdEl} />
        </>
      )}
    </Card>
  );
}
