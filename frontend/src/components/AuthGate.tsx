import { useEffect, useRef, useState } from "react";
import { Logo } from "./Logo";
import { authConfig, googleLogin, Session } from "../auth";

declare global { interface Window { google?: any } }

const GSI = "https://accounts.google.com/gsi/client";

function loadGsi(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve();
    const s = document.createElement("script");
    s.src = GSI; s.async = true; s.onload = () => resolve(); s.onerror = () => reject(new Error("Could not load Google sign-in"));
    document.head.appendChild(s);
  });
}

export default function AuthGate({ onSession }: { onSession: (s: Session) => void }) {
  const btn = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let dead = false;
    (async () => {
      const cfg = await authConfig();
      if (dead) return;
      setEnabled(cfg.googleEnabled);
      if (!cfg.googleEnabled || !cfg.googleClientId) return;
      try {
        await loadGsi();
        window.google.accounts.id.initialize({
          client_id: cfg.googleClientId,
          callback: async (resp: any) => {
            try { const { token, user } = await googleLogin(resp.credential); onSession({ mode: "google", token, user }); }
            catch (e: any) { setError(e.message); }
          },
        });
        if (btn.current) window.google.accounts.id.renderButton(btn.current, { theme: "outline", size: "large", text: "continue_with", shape: "pill", width: 280 });
      } catch (e: any) { setError(e.message); }
    })();
    return () => { dead = true; };
  }, [onSession]);

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-line bg-card p-8 text-center shadow-lg">
        <div className="flex justify-center"><Logo size={48} tagline /></div>
        <h1 className="mt-5 text-2xl font-bold">Stock Insight</h1>
        <p className="mt-1 text-sm text-mute">Sign up for a personalised view: your explored tickers, most-viewed stocks and a saved watchlist. Guests get generic market info only.</p>

        <div className="mt-6 flex flex-col items-center gap-3">
          <div ref={btn} className="min-h-[44px]" />
          {enabled === false && (
            <p className="text-xs text-mute">Google sign-in isn't configured on this server (set GOOGLE_CLIENT_ID).</p>
          )}
          {error && <p className="text-xs text-bear">{error}</p>}
          <div className="my-1 flex w-full items-center gap-3 text-xs text-mute"><span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" /></div>
          <button onClick={() => onSession({ mode: "guest" })}
            className="w-[280px] rounded-full border border-line px-4 py-2.5 text-sm font-medium hover:bg-line">
            Continue as guest
          </button>
        </div>
        <p className="mt-5 text-xs text-mute">Educational analysis only — not financial advice.</p>
      </div>
    </div>
  );
}
