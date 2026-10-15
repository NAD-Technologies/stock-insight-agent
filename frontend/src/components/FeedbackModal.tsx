import { useState } from "react";
import { sendFeedback } from "../api";

export default function FeedbackModal({ onClose, session }: any) {
  const [rating, setRating] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  const [err, setErr] = useState("");
  const guest = session.mode !== "google";

  const submit = async () => {
    setState("sending"); setErr("");
    try { await sendFeedback({ message, rating, name, email }); setState("done"); }
    catch (e: any) { setErr(e.message); setState("idle"); }
  };
  const field = "w-full rounded-lg border border-line bg-card px-3 py-2 text-sm outline-none";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-line bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        {state === "done" ? (
          <div className="text-center"><div className="text-3xl">🙏</div><h3 className="mt-2 text-lg font-semibold">Thanks for your feedback!</h3>
            <button onClick={onClose} className="mt-4 rounded-lg bg-fg px-4 py-2 text-sm font-semibold text-bg">Close</button></div>
        ) : (
          <>
            <h3 className="text-lg font-semibold">Send feedback</h3>
            <p className="mt-1 text-sm text-mute">Tell NAD Technologies what's working and what isn't.</p>
            <div className="mt-4 flex gap-1" role="radiogroup" aria-label="Rating">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} onClick={() => setRating(n)} aria-label={`${n} star`} className="text-2xl" style={{ color: rating && n <= rating ? "#f59e0b" : "var(--line)" }}>★</button>
              ))}
            </div>
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} maxLength={2000} rows={5} placeholder="Your feedback…" className={`${field} mt-3`} />
            {guest && (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (optional)" maxLength={80} className={field} />
                <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email (optional)" maxLength={120} className={field} />
              </div>
            )}
            {err && <p className="mt-2 text-xs text-bear">{err}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm">Cancel</button>
              <button onClick={submit} disabled={message.trim().length < 3 || state === "sending"} className="rounded-lg bg-fg px-4 py-2 text-sm font-semibold text-bg disabled:opacity-40">
                {state === "sending" ? "Sending…" : "Send"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
