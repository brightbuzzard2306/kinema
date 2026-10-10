"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import * as Popover from "@radix-ui/react-popover";
import { useReducedMotion } from "motion/react";
import { AboutCard } from "./AboutCard";
import DecryptedText from "./bits/DecryptedText";
import { useWorkspaceOptional } from "./WorkspaceProvider";
import { useStage, type Stage } from "@/lib/stage";
import { cn } from "@/lib/utils";

const LABEL = "RS MINI PROJECT";
const STRATEGY: Record<string, string> = { hybrid: "HYBRID", popular: "POPULAR", content: "CONTENT", collaborative: "COLLABORATIVE" };

// narrow screens have no room for the longer lines, so the rotation only adds the dataset line from `lg` up
const LG = "(min-width: 1024px)";
const subscribeLg = (cb: () => void) => {
  const m = window.matchMedia(LG);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
};
const useIsLg = () => useSyncExternalStore(subscribeLg, () => window.matchMedia(LG).matches, () => false);

/** Real server milestones, as short status text. */
function stageText(stage: NonNullable<Stage>): string {
  if (stage.step === "interpret") return "READING YOUR REQUEST";
  if (stage.step === "rank") return `RANKING · ${STRATEGY[stage.strategy ?? "hybrid"] ?? "HYBRID"}`;
  return "WRITING THE REPLY";
}

/**
 * "RS Mini Project" badge for the top bar (React Bits "DecryptedText" effect):
 *  - at rest it alternates between the project name and live dataset numbers, re-scrambling every few seconds;
 *  - while a request is running it shows what the server is REALLY doing (reading → ranking → writing);
 *  - clicking it opens the About card. Reduced-motion users get plain, non-animated text.
 * Hidden on phones (no room); the same credit is in the page footer.
 */
export function ProjectTag({ className }: { className?: string }) {
  const reduce = useReducedMotion();
  const ws = useWorkspaceOptional();
  const stage = useStage();
  const isLg = useIsLg();
  const [round, setRound] = useState(0);
  const busyRef = useRef(false);
  useEffect(() => {
    busyRef.current = stage !== null;
  }, [stage]);

  useEffect(() => {
    if (reduce) return;
    const t = setInterval(() => !busyRef.current && setRound((r) => r + 1), 9000);
    return () => clearInterval(t);
  }, [reduce]);

  const d = ws?.health?.dataset;
  const lines = [LABEL];
  if (isLg && d?.movies && d.ratings) lines.push(`${d.movies.toLocaleString("en-US")} FILMS · ${d.ratings.toLocaleString("en-US")} RATINGS`);
  const shown = stage ? stageText(stage) : lines[round % lines.length];

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label="About this project: RS Mini Project"
          className={cn(
            "hidden w-[15rem] items-center gap-2.5 overflow-hidden whitespace-nowrap rounded-full border-l border-white/12 py-1 pl-4 text-left lg:w-[19.5rem] md:flex",
            className,
          )}
        >
          <span className="relative grid h-2 w-2 shrink-0 place-items-center" aria-hidden>
            <span className="absolute inset-0 rounded-full bg-white" />
            {!reduce && <span className="absolute inset-0 rounded-full bg-white" style={{ animation: "pulse-ring 2.6s ease-out infinite" }} />}
          </span>
          {reduce ? (
            <span className="font-mono text-[11px] tracking-[0.24em] text-white/70">{shown}</span>
          ) : (
            <DecryptedText
              key={`${shown}|${stage ? "live" : round}`}
              text={shown}
              animateOn="inViewHover"
              sequential
              revealDirection="start"
              speed={38}
              maxIterations={12}
              characters="01ABCDEFGHIJKLMNOPQRSTUVWXYZ#$%&*"
              parentClassName="font-mono text-[11px] tracking-[0.24em] whitespace-nowrap"
              className="text-white/75"
              encryptedClassName="text-white/25"
            />
          )}
        </button>
      </Popover.Trigger>
      <AboutCard />
    </Popover.Root>
  );
}
