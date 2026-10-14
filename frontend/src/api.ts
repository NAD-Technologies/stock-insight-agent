async function get(path: string) {
  const r = await fetch(path);
  if (!r.ok) {
    let msg = `Request failed (${r.status})`;
    try { msg = (await r.json()).detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}
export const analyze = (t: string, profile: string) => get(`/api/analyze/${encodeURIComponent(t)}?profile=${profile}`);
export const search = (q: string) => get(`/api/search?q=${encodeURIComponent(q)}`);
export const compare = (tickers: string[], profile: string) =>
  get(`/api/compare?tickers=${tickers.join(",")}&profile=${profile}`);
