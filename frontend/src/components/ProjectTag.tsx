"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import * as Popover from "@radix-ui/react-popover";
import { useReducedMotion } from "motion/react";
import { Info } from "lucide-react";
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
 * A visible pill at every width: icon-only on phones (no room for the text), the live text from `md` up.
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
          title="About this project"
          className={cn(
            "glass-pill press group/about flex h-9 shrink-0 items-center gap-2.5 overflow-hidden whitespace-nowrap rounded-full px-2.5 text-left",
            "md:w-[15.5rem] md:pl-3.5 md:pr-3 lg:w-[20rem]",
            className,
          )}
        >
          <span className="relative hidden h-2 w-2 shrink-0 place-items-center md:grid" aria-hidden>
            <span className="absolute inset-0 rounded-full bg-white" />
            {!reduce && <span className="absolute inset-0 rounded-full bg-white" style={{ animation: "pulse-ring 2.6s ease-out infinite" }} />}
          </span>
          <span className="hidden min-w-0 flex-1 md:block">
            {reduce ? (
              <span className="font-mono text-[11px] tracking-[0.22em] text-white/85">{shown}</span>
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
                parentClassName="font-mono text-[11px] tracking-[0.22em] whitespace-nowrap"
                className="text-white/90"
                encryptedClassName="text-white/30"
              />
            )}
          </span>
          <Info className="h-[17px] w-[17px] shrink-0 text-white/70 transition-colors group-hover/about:text-white" strokeWidth={1.9} aria-hidden />
        </button>
      </Popover.Trigger>
      <AboutCard />
    </Popover.Root>
  );
}
