"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";
import { ArrowUpRight } from "lucide-react";
import { MorphText } from "./MorphText";
import { useWorkspaceOptional } from "./WorkspaceProvider";
import { openProject } from "@/lib/project";
import { cn } from "@/lib/utils";

const LABEL = "NLP MINI PROJECT";

/**
 * The "NLP MINI PROJECT" mark, now at the top of the home page instead of the crowded navbar.
 * It alternates (every few seconds, with a decrypt effect from React Bits) between the project name and the real dataset numbers.
 * Clicking it opens the Project dialog. Reduced-motion users get plain static text.
 */
export function ProjectEyebrow({ className }: { className?: string }) {
  const reduce = useReducedMotion();
  const ws = useWorkspaceOptional();
  const [round, setRound] = useState(0);

  useEffect(() => {
    if (reduce) return;
    const t = setInterval(() => setRound((r) => r + 1), 5200);
    return () => clearInterval(t);
  }, [reduce]);

  const d = ws?.health?.dataset;
  const lines = [LABEL];
  if (d?.movies && d.ratings) lines.push(`${d.movies.toLocaleString("en-US")} FILMS · ${d.ratings.toLocaleString("en-US")} RATINGS`);
  const shown = lines[round % lines.length];
  const width = Math.max(...lines.map((l) => l.length)); // the box is as wide as the longest line, so it never resizes

  return (
    <button
      type="button"
      onClick={() => openProject("about")}
      aria-label="About this project: NLP Mini Project"
      className={cn(
        "glass-pill press group/eyebrow inline-flex items-center justify-center gap-2.5 rounded-full px-4 py-2 sm:gap-3 sm:px-5",
        "hover:border-white/45",
        className,
      )}
    >
      <span className="relative grid h-2 w-2 shrink-0 place-items-center" aria-hidden>
        <span className="absolute inset-0 rounded-full bg-white" />
        {!reduce && <span className="absolute inset-0 rounded-full bg-white" style={{ animation: "pulse-ring 2.6s ease-out infinite" }} />}
      </span>
      <MorphText text={shown} width={width} intro className="text-[10.5px] sm:text-[11.5px]" />
      <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-white/50 transition-all group-hover/eyebrow:translate-x-0.5 group-hover/eyebrow:-translate-y-0.5 group-hover/eyebrow:text-white" aria-hidden />
    </button>
  );
}
