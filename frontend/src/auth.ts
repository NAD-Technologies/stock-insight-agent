export type User = { id: string; email: string; name: string; picture?: string };
export type Session = { mode: "guest" } | { mode: "google"; token: string; user: User };

const KEY = "session_v1";

export const loadSession = (): Session | null => {
  try { const v = localStorage.getItem(KEY); return v ? JSON.parse(v) : null; } catch { return null; }
};
export const saveSession = (s: Session | null) => {
  try { s ? localStorage.setItem(KEY, JSON.stringify(s)) : localStorage.removeItem(KEY); } catch { /* ignore */ }
};

export async function authConfig(): Promise<{ googleEnabled: boolean; googleClientId: string | null }> {
  try { const r = await fetch("/api/auth/config"); if (r.ok) return r.json(); } catch { /* ignore */ }
  return { googleEnabled: false, googleClientId: null };
}

export async function googleLogin(credential: string): Promise<{ token: string; user: User }> {
  const r = await fetch("/api/auth/google", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ credential }),
  });
  if (!r.ok) {
    let msg = `Sign-in failed (${r.status})`;
    try { msg = (await r.json()).detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}

/** True if the stored token is still accepted by the server (false on 401; true on network errors so offline use keeps working). */
export async function validate(token: string): Promise<boolean> {
  try { return (await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } })).status !== 401; }
  catch { return true; }
}
