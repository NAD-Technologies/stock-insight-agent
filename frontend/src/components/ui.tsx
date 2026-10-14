import React from "react";
import { ratingColor, scoreColor } from "../lib/format";

export function Card({ title, right, children, className = "" }: any) {
  return (
    <section className={`rounded-xl border border-line bg-card p-4 ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-mute">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Badge({ text, color }: { text: string; color?: string }) {
  const c = color || ratingColor(text);
  return (
    <span className="inline-block rounded-full px-2 py-0.5 text-xs font-semibold" style={{ background: c + "26", color: c }}>
      {text}
    </span>
  );
}

export function Skeleton({ h = 120 }: { h?: number }) {
  return <div className="skeleton w-full" style={{ height: h }} />;
}

export function ScoreBar({ score }: { score: number | null }) {
  const s = score ?? 0;
  return (
    <div className="h-2 w-full rounded-full bg-line">
      <div className="h-2 rounded-full" style={{ width: `${s}%`, background: scoreColor(s) }} />
    </div>
  );
}

/** Semi-circular gauge, value 0..100. */
export function Gauge({ value, label, size = 220, color }: { value: number; label?: string; size?: number; color?: string }) {
  const v = Math.max(0, Math.min(100, value ?? 0));
  const r = 80, cx = 100, cy = 100;
  const pt = (p: number) => {
    const a = Math.PI * (1 - p / 100);
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
  };
  const [x1, y1] = pt(0), [x2, y2] = pt(100), [vx, vy] = pt(v);
  const col = color || scoreColor(v);
  return (
    <svg viewBox="0 0 200 120" width={size} style={{ maxWidth: "100%" }}>
      <path d={`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`} stroke="var(--line)" strokeWidth="14" fill="none" strokeLinecap="round" />
      {v > 0 && <path d={`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${vx} ${vy}`} stroke={col} strokeWidth="14" fill="none" strokeLinecap="round" />}
      <text x="100" y="92" textAnchor="middle" fontSize="30" fontWeight="700" fill="currentColor" className="num">{Math.round(v)}</text>
      {label && <text x="100" y="112" textAnchor="middle" fontSize="10" fill="var(--mute)">{label}</text>}
    </svg>
  );
}

/** Wraps a section so one failure shows "data unavailable" instead of blanking the page. */
export class Section extends React.Component<{ title: string; children: any }, { err: boolean }> {
  state = { err: false };
  static getDerivedStateFromError() { return { err: true }; }
  render() {
    if (this.state.err)
      return <Card title={this.props.title}><p className="text-sm text-mute">Data unavailable for this section.</p></Card>;
    return this.props.children;
  }
}
