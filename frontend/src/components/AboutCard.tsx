"use client";

import Link from "next/link";
import * as Popover from "@radix-ui/react-popover";
import { ArrowUpRight, Compass } from "lucide-react";
import { useWorkspaceOptional } from "./WorkspaceProvider";
import { CREDIT, hasCredit } from "@/lib/credit";
import { restartTour } from "@/lib/tour";

const ALGORITHMS = [
  ["Popular", "Bayesian-average rating. The same list for everyone: the cold-start baseline."],
  ["Content", "TF-IDF over genres, tags and titles finds look-alikes of what you liked."],
  ["People like you", "Item-item collaborative filtering: movies liked by the same people are similar."],
  ["Hybrid", "A weighted blend of all three, with weights tuned on held-out data."],
] as const;

/** The popover behind the "RS MINI PROJECT" badge: the project in 30 seconds, plus who made it (when configured). */
export function AboutCard() {
  const ws = useWorkspaceOptional();
  const d = ws?.health?.dataset;
  const stats = d && d.movies ? [`${d.movies.toLocaleString()} movies`, `${d.ratings.toLocaleString()} ratings`, d.users ? `${d.users.toLocaleString()} users` : null].filter(Boolean).join(" · ") : null;

  return (
    <Popover.Portal>
      <Popover.Content
        align="start"
        sideOffset={14}
        collisionPadding={12}
        className="glass glass-strong z-50 max-h-[var(--radix-popover-content-available-height)] w-[min(92vw,420px)] overflow-y-auto overscroll-contain rounded-[28px] p-5 text-white outline-none data-[state=open]:animate-[pop-in_0.25s_var(--ease-out)] sm:p-6"
      >
        <p className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-white/45">RS Mini Project</p>
        <h2 className="mt-1.5 font-display text-[2rem] leading-none">A conversational movie recommender</h2>
        <p className="mt-3 text-[13.5px] leading-relaxed text-white/60">
          Choosing a film is slow: search needs a title, and a chatbot alone can invent movies. Kinema ranks real MovieLens data with four
          recommendation algorithms; Claude only understands your sentence and words the reply.
        </p>

        <ul className="mt-4 space-y-2.5">
          {ALGORITHMS.map(([name, text]) => (
            <li key={name} className="grid grid-cols-[104px_1fr] gap-3 text-[12.5px] leading-snug">
              <span className="font-medium text-white">{name}</span>
              <span className="text-white/55">{text}</span>
            </li>
          ))}
        </ul>

        {stats && <p className="mt-4 font-mono text-[11px] leading-relaxed text-white/45">MovieLens ml-latest-small · {stats}</p>}

        <p className="mt-3 text-[11.5px] leading-relaxed text-white/40">
          Privacy: no accounts. Chats are kept on the server against a random ID stored in this browser, and when Claude is on your messages are sent to Anthropic&apos;s API to be understood.
        </p>

        {hasCredit && (
          <div className="mt-4 border-t border-white/10 pt-4 text-[13px] leading-relaxed">
            {CREDIT.author && <p>Made by <span className="text-white">{CREDIT.author}</span></p>}
            {[CREDIT.college, CREDIT.course].filter(Boolean).length > 0 && <p className="text-white/55">{[CREDIT.college, CREDIT.course].filter(Boolean).join(" · ")}</p>}
            {CREDIT.guide && <p className="text-white/55">Guide: {CREDIT.guide}</p>}
          </div>
        )}

        <div className="mt-5 flex flex-wrap gap-2">
          <Popover.Close asChild>
            <Link href="/evaluation" className="press glass-pill flex items-center gap-1.5 rounded-full px-4 py-2 text-[12.5px] text-white">
              See the evaluation <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          </Popover.Close>
          {ws && (
            <Popover.Close asChild>
              <button type="button" onClick={restartTour} className="press glass-pill flex items-center gap-1.5 rounded-full px-4 py-2 text-[12.5px] text-white">
                <Compass className="h-3.5 w-3.5" aria-hidden /> Take the tour
              </button>
            </Popover.Close>
          )}
        </div>
      </Popover.Content>
    </Popover.Portal>
  );
}
