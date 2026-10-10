"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { MorphText } from "./MorphText";
import { useStage, type Stage } from "@/lib/stage";

const STRATEGY: Record<string, string> = { hybrid: "HYBRID", popular: "POPULAR", content: "CONTENT", collaborative: "COLLABORATIVE" };

const CHIP_WIDTH = 22; // "RANKING · COLLABORATIVE" is the longest status; a fixed width keeps the chip from resizing

/** Real server milestones, as short status text. */
function stageText(stage: NonNullable<Stage>): string {
  if (stage.step === "interpret") return "READING YOUR REQUEST";
  if (stage.step === "rank") return `RANKING · ${STRATEGY[stage.strategy ?? "hybrid"] ?? "HYBRID"}`;
  return "WRITING THE REPLY";
}

/**
 * A small live status above the prompt while a request runs: what the server is REALLY doing (reading → ranking → writing),
 * driven by the streamed progress events, not a fake animation. Invisible when idle.
 */
export function StageChip() {
  const stage = useStage();
  const reduce = useReducedMotion();
  const text = stage ? stageText(stage) : null;

  return (
    <div className="pointer-events-none flex justify-center" aria-live="polite">
      <AnimatePresence initial={false}>
        {text && (
          <motion.div
            key="chip"
            initial={reduce ? false : { opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? undefined : { opacity: 0, y: 6, scale: 0.97 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="glass-pill flex items-center gap-2.5 rounded-full px-4 py-1.5"
          >
            <span className="relative grid h-2 w-2 place-items-center" aria-hidden>
              <span className="absolute inset-0 rounded-full bg-white" />
              {!reduce && <span className="absolute inset-0 rounded-full bg-white" style={{ animation: "pulse-ring 1.6s ease-out infinite" }} />}
            </span>
            <MorphText text={text} width={CHIP_WIDTH} className="text-[10.5px] sm:text-[11px]" />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
