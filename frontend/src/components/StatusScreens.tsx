"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { ArrowRight, Loader2, LockKeyhole, RefreshCw, ServerCrash, X } from "lucide-react";
import { API_IS_LOCAL } from "@/lib/http";
import { Logo } from "./Nav";
import { useWorkspace } from "./WorkspaceProvider";

export function LoadingScreen() {
  const { waking } = useWorkspace();
  return (
    <div className="grid min-h-dvh place-items-center" role="status" aria-label="Loading Kinema">
      <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.8 }} className="flex flex-col items-center gap-6">
        <Logo busy />
        <div className="h-[3px] w-40 overflow-hidden rounded-full bg-white/10"><div className="skeleton h-full w-full" /></div>
        {waking ? (
          <p className="max-w-xs text-center text-[13px] leading-relaxed text-white/55" aria-live="polite">
            Waking the server up. Free hosting sleeps when nobody is around, so the first visit can take up to a minute.
          </p>
        ) : (
          <p className="text-[13px] text-white/40">Warming up the recommender…</p>
        )}
      </motion.div>
    </div>
  );
}

export function FatalScreen({ message }: { message: string }) {
  const { reload } = useWorkspace();
  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <div className="glass glass-strong w-full max-w-lg rounded-[34px] p-8 text-center" role="alert">
        <ServerCrash className="mx-auto h-9 w-9 text-white/80" aria-hidden />
        <h1 className="mt-5 font-display text-[2.2rem] leading-none">The recommender isn&apos;t reachable</h1>
        <p className="mt-3 text-[14.5px] leading-relaxed text-white/60">{message}</p>
        {API_IS_LOCAL && (
          <div className="mt-6 rounded-2xl border border-white/10 bg-black/40 p-4 text-left font-mono text-[12px] leading-relaxed text-white/70">
            <p className="text-white/40"># in another terminal</p>
            <p>cd backend</p>
            <p>.venv/bin/uvicorn app.main:app --port 8000</p>
          </div>
        )}
        <button type="button" onClick={reload} className="press mx-auto mt-6 flex items-center gap-2 rounded-full bg-white px-6 py-3 text-[14px] font-medium text-black">
          <RefreshCw className="h-4 w-4" /> Try again
        </button>
      </div>
    </div>
  );
}

/** Shown first when the site is private. The code is checked by the server; it is never part of the page. */
export function AccessScreen() {
  const { unlock } = useWorkspace();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const submit = async () => {
    if (!code.trim() || checking) return;
    setChecking(true);
    setError(null);
    try {
      await unlock(code);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't check the code. Please try again.");
      setChecking(false);
    }
  };

  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        className="glass glass-strong w-full max-w-md rounded-[34px] p-8 text-center"
      >
        <div className="mx-auto w-fit"><Logo busy={checking} /></div>
        <h1 className="mt-6 font-display text-[2.2rem] leading-none">This one is private</h1>
        <p className="mt-3 text-[14.5px] leading-relaxed text-white/60">Enter the access code you were given to continue.</p>
        <label htmlFor="access-code" className="sr-only">Access code</label>
        <div className="glass relative mt-6 flex items-center gap-2 rounded-full p-1.5 pl-5 focus-within:border-white/50">
          <LockKeyhole className="h-4 w-4 shrink-0 text-white/45" aria-hidden />
          <input
            id="access-code"
            type="password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoFocus
            autoComplete="off"
            maxLength={200}
            placeholder="Access code"
            aria-invalid={!!error}
            aria-describedby={error ? "access-error" : "access-privacy"}
            className="min-w-0 flex-1 bg-transparent py-2.5 text-[16px] text-white placeholder:text-white/35 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!code.trim() || checking}
            aria-label="Continue"
            className="press grid h-11 w-11 shrink-0 place-items-center rounded-full bg-white text-black disabled:bg-white/15 disabled:text-white/40"
          >
            {checking ? <Loader2 className="h-5 w-5 animate-spin" /> : <ArrowRight className="h-5 w-5" strokeWidth={2.2} />}
          </button>
        </div>
        {error && (
          <p id="access-error" role="alert" className="mt-3 text-[13px] text-white">
            {error}
          </p>
        )}
        <p id="access-privacy" className="mt-6 text-[11.5px] leading-relaxed text-white/40">
          No accounts. Your chats are kept against a random ID in this browser. When Claude is on, your messages are sent to Anthropic&apos;s API to be understood.
        </p>
      </form>
    </div>
  );
}

export function Toasts() {
  const { toasts, dismissToast } = useWorkspace();
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-28 z-[70] flex flex-col items-center gap-2 px-4" aria-live="polite" aria-atomic="false">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.97 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className="glass glass-strong pointer-events-auto flex max-w-md items-center gap-3 rounded-full py-2.5 pl-5 pr-2.5 text-[13.5px] text-white"
            role="status"
          >
            <span>{t.text}</span>
            <button type="button" onClick={() => dismissToast(t.id)} aria-label="Dismiss" className="press grid h-7 w-7 place-items-center rounded-full bg-white/10">
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
