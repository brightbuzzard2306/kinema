"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { AlertCircle, Check, Columns3, Info, RotateCcw } from "lucide-react";
import ShinyText from "./bits/ShinyText";
import { Carousel } from "./Carousel";
import { MovieCard, SkeletonCard } from "./MovieCard";
import { useWorkspace } from "./WorkspaceProvider";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";

function TypingDots({ label = "Finding your next watch…" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-3 py-2" role="status" aria-label="Kinema is thinking">
      <span className="inline-flex items-center gap-1.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-2 w-2 rounded-full bg-white/70" style={{ animation: `dot-bounce 1.2s ${i * 0.15}s infinite ease-in-out` }} />
        ))}
      </span>
      <span aria-hidden className="text-[15px]">
        <ShinyText text={label} color="rgba(245,245,247,0.45)" shineColor="#ffffff" speed={2.2} />
      </span>
    </span>
  );
}

/** Words fade in one by one (capped so long replies don't lag). */
function Reveal({ text, animate }: { text: string; animate: boolean }) {
  const reduce = useReducedMotion();
  if (!animate || reduce) return <>{text}</>;
  const words = text.split(" ");
  return (
    <span className="word-reveal" aria-label={text}>
      {words.map((w, i) => (
        <span key={i} aria-hidden style={{ animationDelay: `${Math.min(i, 45) * 28}ms` }}>
          {w}
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </span>
  );
}

function Chip({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return <span className="glass-pill flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] text-white/80">{icon}{children}</span>;
}

function UserBubble({ m }: { m: ChatMessage }) {
  const { retry, busy } = useWorkspace();
  return (
    <div className="flex w-full flex-col items-end gap-2">
      <div className="glass glass-strong max-w-[88%] rounded-[26px] rounded-br-lg px-5 py-3.5 text-[16px] leading-relaxed text-white sm:max-w-[70%]">{m.text}</div>
      {m.failed && (
        <div className="flex items-center gap-2 text-[12.5px] text-white/70" role="alert">
          <AlertCircle className="h-4 w-4" /> Not sent.
          <button type="button" disabled={busy} onClick={() => void retry(m.id)} className="press flex items-center gap-1.5 rounded-full bg-white px-3 py-1 font-medium text-black disabled:opacity-40">
            <RotateCcw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}
    </div>
  );
}

function AssistantBlock({ m, isLast }: { m: ChatMessage; isLast: boolean }) {
  const { send, busy, setCompareOpen } = useWorkspace();
  const hasCards = !!m.cards?.length;
  return (
    <div className="max-w-full">
      <div className="mb-3 flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-white/40">
        <span className="h-1.5 w-1.5 rounded-full bg-white" aria-hidden /> Kinema
      </div>

      {m.pending && !hasCards ? (
        <>
          <TypingDots />
          <div className="mt-4 flex gap-4 overflow-hidden" aria-hidden>
            {[0, 1, 2, 3, 4].map((i) => <SkeletonCard key={i} />)}
          </div>
        </>
      ) : (
        <>
          {m.pending ? (
            // the picks are already here (streamed ahead of the reply); only the sentence is still being written
            <TypingDots label="Writing the reply…" />
          ) : (
            <p className="max-w-3xl text-[19px] leading-[1.55] text-white/95 sm:text-[21px]" aria-live="polite">
              <Reveal text={m.text} animate={isLast} />
            </p>
          )}

          {!!m.changes?.length && (
            <ul className="mt-4 flex flex-wrap gap-2" aria-label="Changes to your taste profile">
              {m.changes.map((c) => <li key={c}><Chip icon={<Check className="h-3.5 w-3.5" />}>{c}</Chip></li>)}
            </ul>
          )}
          {!!m.notes?.length && (
            <ul className="mt-3 space-y-1.5">
              {m.notes.map((n) => (
                <li key={n} className="flex items-start gap-2 text-[13px] leading-snug text-white/55">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /> {n}
                </li>
              ))}
            </ul>
          )}
          {!!m.unresolved?.length && (
            <p className="mt-3 flex items-start gap-2 text-[13px] text-white/55">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /> I couldn&apos;t find &ldquo;{m.unresolved.join("”, “")}&rdquo; in MovieLens, so I ignored it.
            </p>
          )}

          {hasCards && (
            <Carousel label="Recommended movies" className="mt-5">
              {m.cards!.map((c, i) => <MovieCard key={c.movie_id} card={c} index={i} />)}
            </Carousel>
          )}

          {!m.pending && m.llm?.mode === "fallback" && m.llm.reason && (
            <p className="mt-1 text-[11.5px] text-white/30">Understood by the offline parser — {m.llm.reason.replace(/\.$/, "")}.</p>
          )}
          {!m.pending && m.llm?.mode === "claude" && m.llm.reason && <p className="mt-1 text-[11.5px] text-white/30">{m.llm.reason}</p>}

          {isLast && !m.pending && (hasCards || !!m.suggestions?.length) && (
            <div className="mt-4 flex flex-wrap gap-2" aria-label="Suggested follow-ups">
              {hasCards && (
                <button
                  type="button"
                  data-tour="compare"
                  onClick={() => setCompareOpen(true)}
                  className="glass-pill press flex items-center gap-2 rounded-full px-4 py-2 text-[13px] text-white hover:border-white/50"
                >
                  <Columns3 className="h-4 w-4" aria-hidden /> Compare strategies
                </button>
              )}
              {(m.suggestions ?? []).map((s) => (
                <button key={s} type="button" disabled={busy} onClick={() => void send(s)} className="glass-pill press rounded-full px-4 py-2 text-[13px] text-white/85 hover:border-white/40 disabled:opacity-40">
                  {s}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function ChatThread() {
  const { messages } = useWorkspace();
  const root = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  // Bring the start of the newest turn into view (the user's message, then the reply flows beneath it).
  const count = messages.length;
  useEffect(() => {
    const last = messages[count - 1];
    if (!last) return;
    const target = last.role === "assistant" && last.pending ? messages[count - 2] : last;
    if (!target) return;
    root.current?.querySelector(`[data-msg-id="${target.id}"]`)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [count, reduce]);

  return (
    <div ref={root} className="mx-auto w-full max-w-5xl space-y-10 px-4 pb-[70vh] pt-28 sm:px-6" role="log" aria-label="Conversation">
      <AnimatePresence initial={false}>
        {messages.map((m, i) => (
          <motion.div
            key={m.id}
            data-msg-id={m.id}
            layout="position"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className={cn("scroll-mt-28", m.role === "user" && "flex justify-end")}
          >
            {m.role === "user" ? <UserBubble m={m} /> : <AssistantBlock m={m} isLast={i === messages.length - 1} />}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
