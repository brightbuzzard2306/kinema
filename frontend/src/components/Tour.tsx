"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";
import { useWorkspace } from "./WorkspaceProvider";
import { finishTour, goToStep, loadTour, TOUR_STEPS, useTour } from "@/lib/tour";
import { cn } from "@/lib/utils";

const STEPS = [
  { target: "prompt", title: "Say what you're in the mood for", body: "Type a mood, a genre or a film you loved, or tap an example. Press Enter to send.", cta: "Got it" },
  { target: "card", title: "Every pick is a real MovieLens film", body: "Hover a card to see why it was chosen. The thumbs teach Kinema your taste, and a film you dislike never comes back.", cta: "Next" },
  { target: "why", title: "See exactly why", body: "The sparkle button opens the score breakdown: how similar content, people like you and overall quality each pushed this film up.", cta: "Next" },
  { target: "compare", title: "Compare the algorithms", body: "Rank the same request with Popular, Content, People like you and Hybrid side by side.", cta: "Done" },
] as const;

const PAD = 8;

/** The newest visible element for a tour target (the latest results are the last in the DOM). */
function findTarget(name: string): HTMLElement | null {
  const all = document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`);
  for (let i = all.length - 1; i >= 0; i--) {
    const r = all[i].getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return all[i];
  }
  return null;
}

/**
 * First-visit tour: a spotlight that follows the real element plus an explanation card.
 * Non-blocking (clicks go through to the real UI), keyboard friendly (Esc skips), remembers progress, never nags once finished,
 * and waits quietly when the thing it points at doesn't exist yet (e.g. movie cards before the first search).
 */
export function Tour() {
  const tour = useTour();
  const reduce = useReducedMotion();
  const { messages } = useWorkspace();
  const [armed, setArmed] = useState(false);
  const [found, setFound] = useState<{ step: number; ok: boolean }>({ step: -1, ok: false });
  const spotRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const settling = useRef(false);

  useEffect(() => {
    loadTour();
    const t = setTimeout(() => setArmed(true), 1400); // let the page settle before anything pops up
    return () => clearTimeout(t);
  }, []);

  const active = armed && !tour.loading && !tour.done;
  const step = STEPS[Math.min(tour.step, TOUR_STEPS - 1)];
  const hasMessages = messages.length > 0;

  // the user has already started chatting: step 1 ("say what you want") is moot
  useEffect(() => {
    if (active && tour.step === 0 && hasMessages) goToStep(1);
  }, [active, tour.step, hasMessages]);

  // follow the target on every frame while it exists; poll slowly while we wait for it to appear
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let lastOk = false;
    settling.current = true;
    const settle = setTimeout(() => (settling.current = false), 650);

    const tick = () => {
      const el = findTarget(step.target);
      const ok = !!el;
      if (ok !== lastOk) {
        lastOk = ok;
        setFound({ step: tour.step, ok });
        if (el) {
          const r = el.getBoundingClientRect();
          if (r.top < 90 || r.bottom > window.innerHeight - 120) el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
        }
      }
      const spot = spotRef.current;
      const card = cardRef.current;
      if (el && spot && card) {
        const r = el.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const cw = card.offsetWidth;
        const ch = card.offsetHeight;
        const ease = settling.current && !reduce ? "0.5s cubic-bezier(0.22,1,0.36,1)" : "none";
        spot.style.transition = `transform ${ease}, width ${ease}, height ${ease}`;
        card.style.transition = `transform ${ease}`;
        spot.style.transform = `translate3d(${r.left - PAD}px, ${r.top - PAD}px, 0)`;
        spot.style.width = `${r.width + PAD * 2}px`;
        spot.style.height = `${r.height + PAD * 2}px`;
        const below = r.bottom + PAD + 14;
        const above = r.top - PAD - 14 - ch;
        const y = below + ch + 12 <= vh ? below : above >= 12 ? above : Math.max(12, vh - ch - 16);
        const x = Math.min(Math.max(r.left + r.width / 2 - cw / 2, 12), Math.max(12, vw - cw - 12));
        card.style.transform = `translate3d(${x}px, ${y}px, 0)`;
        raf = requestAnimationFrame(tick);
      } else {
        timer = setTimeout(tick, 250);
      }
    };
    tick();
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
      clearTimeout(settle);
    };
  }, [active, tour.step, step.target, reduce]);

  // Esc skips (unless a dialog is open: Esc belongs to it then)
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.querySelector('[role="dialog"][data-state="open"]')) finishTour();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active]);

  const visible = active && found.step === tour.step && found.ok;
  if (!active || typeof document === "undefined") return null;

  return createPortal(
    <div className={cn("pointer-events-none fixed inset-0 z-[45]", !visible && "invisible")} aria-hidden={!visible}>
      <div
        ref={spotRef}
        className="absolute left-0 top-0 rounded-[26px] border border-white/60"
        style={{ boxShadow: "0 0 0 9999px rgba(3,3,4,0.62), 0 0 36px rgba(255,255,255,0.25)" }}
      />
      <div
        ref={cardRef}
        role="dialog"
        aria-label="Kinema quick tour"
        aria-describedby="tour-body"
        className="glass glass-strong pointer-events-auto absolute left-0 top-0 w-[min(88vw,340px)] rounded-[24px] p-5"
        style={{ background: "linear-gradient(180deg, rgba(34,34,38,0.94), rgba(16,16,18,0.96))" }}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={tour.step}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -6 }}
            transition={{ duration: 0.22 }}
          >
            <p className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-white/45">
              Quick tour · {tour.step + 1} of {TOUR_STEPS}
            </p>
            <h3 className="mt-2 font-display text-[1.65rem] leading-[1.05]">{step.title}</h3>
            <p id="tour-body" className="mt-2 text-[13.5px] leading-relaxed text-white/65">
              {step.body}
            </p>
          </motion.div>
        </AnimatePresence>
        <div className="mt-4 flex items-center gap-2">
          <span className="flex gap-1.5" aria-hidden>
            {STEPS.map((_, i) => (
              <span key={i} className={cn("h-1.5 rounded-full transition-all", i === tour.step ? "w-5 bg-white" : "w-1.5 bg-white/25")} />
            ))}
          </span>
          <span className="flex-1" />
          <button type="button" onClick={finishTour} className="press rounded-full px-3 py-2 text-[12.5px] text-white/55 hover:text-white">
            Skip
          </button>
          <button
            type="button"
            onClick={() => (tour.step >= TOUR_STEPS - 1 ? finishTour() : goToStep(tour.step + 1))}
            className="press flex items-center gap-1.5 rounded-full bg-white px-4 py-2 text-[12.5px] font-medium text-black"
          >
            {step.cta} {tour.step < TOUR_STEPS - 1 && <ArrowRight className="h-3.5 w-3.5" aria-hidden />}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
