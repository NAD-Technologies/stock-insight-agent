export const na = (v: any) => v === null || v === undefined || (typeof v === "number" && !isFinite(v));
export const num = (v: any, d = 2) => (na(v) ? "N/A" : Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
// Display currency follows the stock being viewed (set from quote.currency); Indian stocks show in INR.
const SYMBOLS: Record<string, string> = { USD: "$", INR: "₹", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥", HKD: "HK$", CAD: "C$", AUD: "A$", SGD: "S$" };
const SUFFIX_CCY: [string, string][] = [[".NS", "INR"], [".BO", "INR"], [".T", "JPY"], [".HK", "HKD"], [".TO", "CAD"], [".AX", "AUD"], [".L", "GBP"], [".DE", "EUR"], [".PA", "EUR"]];
/** Safety net when the API sends no currency: guess from the exchange suffix (RELIANCE.NS -> INR). */
export const inferCurrency = (ticker?: string) => SUFFIX_CCY.find(([s]) => (ticker || "").toUpperCase().endsWith(s))?.[1] ?? "USD";
let currentCurrency = "USD";
export const setCurrency = (c?: string | null) => { currentCurrency = (c || "USD").toUpperCase(); };
export const sym = (c?: string | null) => { const k = (c || currentCurrency).toUpperCase(); return SYMBOLS[k] ?? k + " "; };
const locale = (c?: string | null) => ((c || currentCurrency).toUpperCase() === "INR" ? "en-IN" : undefined);
export const usd = (v: any, d = 2, c?: string | null) =>
  na(v) ? "N/A" : sym(c) + Number(v).toLocaleString(locale(c), { minimumFractionDigits: d, maximumFractionDigits: d });
export const pct = (v: any, d = 2) => (na(v) ? "N/A" : `${v > 0 ? "+" : ""}${num(v, d)}%`);
export const ratioPct = (v: any, d = 1) => (na(v) ? "N/A" : `${num(v * 100, d)}%`);
export const big = (v: any, c?: string | null) => {
  if (na(v)) return "N/A";
  const a = Math.abs(v);
  if ((c || currentCurrency).toUpperCase() === "INR" && a >= 1e7) {  // Indian convention: crore / lakh crore
    const s = a >= 1e12 ? (a / 1e12).toFixed(2) + " L Cr" : (a / 1e7).toFixed(2) + " Cr";
    return (v < 0 ? "-" : "") + s;
  }
  const s = a >= 1e12 ? (a / 1e12).toFixed(2) + "T" : a >= 1e9 ? (a / 1e9).toFixed(2) + "B" : a >= 1e6 ? (a / 1e6).toFixed(2) + "M" : a >= 1e3 ? (a / 1e3).toFixed(1) + "K" : a.toFixed(0);
  return (v < 0 ? "-" : "") + s;
};
export const ago = (iso: string) => {
  const m = Math.max(0, (Date.now() - new Date(iso).getTime()) / 60000);
  if (isNaN(m)) return "";
  if (m < 60) return `${Math.round(m)}m ago`;
  if (m < 1440) return `${Math.round(m / 60)}h ago`;
  return `${Math.round(m / 1440)}d ago`;
};
export const ratingColor = (r: string) => {
  const s = (r || "").toLowerCase();
  if (s.includes("buy") || s === "bullish" || s === "good") return "#16a34a";
  if (s.includes("sell") || s === "bearish" || s === "bad") return "#dc2626";
  return "#f59e0b";
};
export const scoreColor = (s: number) => (s >= 65 ? "#16a34a" : s >= 45 ? "#f59e0b" : "#dc2626");
export const fmtMetric = (v: any, f: string) => {
  if (na(v)) return "N/A";
  if (f === "x") return num(v) + "x";
  if (f === "pct") return ratioPct(v);
  if (f === "usd") return big(v);
  return num(v);
};
