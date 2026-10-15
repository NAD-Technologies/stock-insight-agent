import { loadSession } from "./auth";

const headers = (): Record<string, string> => {
  const s = loadSession();
  return s?.mode === "google" ? { Authorization: `Bearer ${s.token}` } : {};
};

async function req(path: string, init: RequestInit = {}) {
  const r = await fetch(path, { ...init, headers: { ...headers(), ...(init.headers || {}) } });
  if (!r.ok) {
    let msg = `Request failed (${r.status})`;
    try { msg = (await r.json()).detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}
const get = (path: string) => req(path);

export const analyze = (t: string, profile: string) => get(`/api/analyze/${encodeURIComponent(t)}?profile=${profile}`);
export const search = (q: string) => get(`/api/search?q=${encodeURIComponent(q)}`);
export const compare = (tickers: string[], profile: string) =>
  get(`/api/compare?tickers=${tickers.join(",")}&profile=${profile}`);
export const myActivity = () => get("/api/me/activity");
export const adminOverview = () => get("/api/admin/overview");
export const sendFeedback = (b: { message: string; rating?: number | null; name?: string; email?: string }) =>
  req("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
export const watchlistSummary = (tickers: string[]) => get(`/api/watchlist/summary?tickers=${tickers.join(",")}`);
export const getPrefs = () => get("/api/me/prefs");
export const putPrefs = (p: Record<string, any>) =>
  req("/api/me/prefs", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) });
