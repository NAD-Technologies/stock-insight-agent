export type User = { id: string; email: string; name: string; picture?: string; isAdmin?: boolean };
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

/** Checks the stored token with the server. Returns the fresh user (incl. isAdmin), null if rejected (401),
 *  or undefined on network errors so offline use keeps working. */
export async function validate(token: string): Promise<User | null | undefined> {
  try {
    const r = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } });
    if (r.status === 401) return null;
    return r.ok ? (await r.json()).user : undefined;
  } catch { return undefined; }
}
