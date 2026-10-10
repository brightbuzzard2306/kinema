"use client";

import { useRef } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import { Layers, Sparkles, Star, ThumbsDown, ThumbsUp } from "lucide-react";
import { Poster } from "./PosterArt";
import { useWorkspace } from "./WorkspaceProvider";
import { setSpotlight } from "@/lib/spotlight";
import { cn, formatCount } from "@/lib/utils";
import type { Confidence, MovieCardData } from "@/lib/types";

/** Three ascending signal bars: more filled bars = more confidence. */
export function ConfidenceDots({ level, className }: { level: Confidence; className?: string }) {
  const n = level === "high" ? 3 : level === "medium" ? 2 : 1;
  return (
    <span className={cn("inline-flex h-3 items-end gap-[3px]", className)} role="img" aria-label={`${level} confidence`}>
      {[0, 1, 2].map((i) => (
        <span key={i} className={cn("w-[3px] rounded-sm transition-colors", i < n ? "bg-white" : "bg-white/25")} style={{ height: 5 + i * 3.5 }} />
      ))}
    </span>
  );
}

function ActionButton({
  label,
  onClick,
  active,
  pressed,
  tour,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  pressed?: boolean;
  tour?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={pressed}
      data-tour={tour}
      title={label}
      className={cn(
        "press grid h-9 w-9 place-items-center rounded-full border text-white/80 backdrop-blur-xl",
        active ? "border-white bg-white text-black" : "border-white/15 bg-white/10 hover:border-white/40 hover:bg-white/20 hover:text-white",
      )}
    >
      {children}
    </button>
  );
}

export function MovieCard({ card, index = 0, compact = false }: { card: MovieCardData; index?: number; compact?: boolean }) {
  const { posters, feedbackFor, giveFeedback, moreLike, openWhy, busy } = useWorkspace();
  const reduce = useReducedMotion();
  const frame = useRef(0);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const feedback = feedbackFor(card.movie_id);

  // 3D tilt driven by pointer position
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const rx = useSpring(useTransform(py, [-0.5, 0.5], [7, -7]), { stiffness: 220, damping: 20 });
  const ry = useSpring(useTransform(px, [-0.5, 0.5], [-8, 8]), { stiffness: 220, damping: 20 });

  // one layout read + one write per animation frame (glow position and tilt together), however fast the mouse moves
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const { clientX, clientY } = e;
    const tilt = !reduce && e.pointerType !== "touch";
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${clientX - r.left}px`);
      el.style.setProperty("--my", `${clientY - r.top}px`);
      if (tilt) {
        px.set((clientX - r.left) / r.width - 0.5);
        py.set((clientY - r.top) / r.height - 0.5);
      }
    });
  };
  const enter = () => {
    if (leaveTimer.current) clearTimeout(leaveTimer.current);
    setSpotlight({ movieId: card.movie_id, title: card.title, year: card.year });
  };
  const leave = () => {
    cancelAnimationFrame(frame.current);
    px.set(0);
    py.set(0);
    leaveTimer.current = setTimeout(() => setSpotlight(null), 250);
  };

  const topReason = card.reasons[0]?.text;

  return (
    <motion.article
      initial={reduce ? false : { opacity: 0, y: 28, filter: "blur(10px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ duration: 0.7, delay: Math.min(index, 8) * 0.07, ease: [0.22, 1, 0.36, 1] }}
      style={{ perspective: 900 }}
      className={cn("shrink-0 snap-start", compact ? "w-[168px]" : "w-[216px] sm:w-[232px]")}
      aria-label={`${card.title}${card.year ? `, ${card.year}` : ""}`}
    >
      <motion.div
        onPointerMove={onMove}
        onPointerEnter={enter}
        onPointerLeave={leave}
        onFocus={enter}
        onBlur={leave}
        data-tour={index === 0 && !compact ? "card" : undefined}
        style={{ rotateX: rx, rotateY: ry, transformStyle: "preserve-3d" }}
        className="glass glass-flat spec group relative aspect-[2/3] overflow-hidden rounded-[28px] [container-type:inline-size]"
      >
        <Poster title={card.title} year={card.year} src={posters[card.movie_id]} />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/70 via-[38%] to-transparent to-[75%]" />

        <div className="absolute left-3.5 right-3.5 top-3.5 flex items-center justify-between">
          <span className="glass-pill rounded-full px-2.5 py-1.5" title={card.confidence_basis}>
            <ConfidenceDots level={card.confidence} />
          </span>
          {card.mean_rating !== null && (
            <span
              className="glass-pill flex items-center gap-1 rounded-full px-2.5 py-1 font-mono text-[11px] text-white"
              title="Average rating from MovieLens users (not IMDb or TMDB)"
            >
              <Star className="h-3 w-3 fill-white" aria-hidden />
              {card.mean_rating.toFixed(1)}
              <span className="sr-only"> MovieLens average from {card.n_ratings} ratings</span>
            </span>
          )}
        </div>

        <div className="absolute inset-x-0 bottom-0 p-3.5">
          <h3 className="font-display text-[1.65rem] leading-[1.02] tracking-tight text-white">{card.title}</h3>
          <p className="mt-1 text-[11.5px] text-white/60">
            {card.year ?? "—"} · {card.genres.slice(0, 3).join(" · ") || "No genres listed"}
          </p>
          <p className="mt-0.5 font-mono text-[10.5px] text-white/40">{formatCount(card.n_ratings)} MovieLens ratings</p>

          {topReason && !compact && (
            <p className="mt-2 line-clamp-2 max-h-0 overflow-hidden text-[12px] leading-snug text-white/75 opacity-0 transition-all duration-500 [transition-timing-function:var(--ease-out)] group-hover:max-h-12 group-hover:opacity-100 group-focus-within:max-h-12 group-focus-within:opacity-100 [@media(hover:none)]:max-h-12 [@media(hover:none)]:opacity-100">
              {topReason}
            </p>
          )}

          <div className="mt-3 flex items-center gap-1.5">
            <ActionButton label={feedback === "like" ? `Remove like from ${card.title}` : `Like ${card.title}`} pressed={feedback === "like"} active={feedback === "like"} onClick={() => giveFeedback(card.movie_id, feedback === "like" ? "clear" : "like")}>
              <ThumbsUp className="h-4 w-4" />
            </ActionButton>
            <ActionButton label={feedback === "dislike" ? `Remove dislike from ${card.title}` : `Dislike ${card.title}`} pressed={feedback === "dislike"} active={feedback === "dislike"} onClick={() => giveFeedback(card.movie_id, feedback === "dislike" ? "clear" : "dislike")}>
              <ThumbsDown className="h-4 w-4" />
            </ActionButton>
            <span className="flex-1" />
            <ActionButton label={`Why ${card.title}?`} tour={index === 0 ? "why" : undefined} onClick={() => openWhy(card)}>
              <Sparkles className="h-4 w-4" />
            </ActionButton>
            <button
              type="button"
              disabled={busy}
              onClick={() => moreLike(card)}
              aria-label={`More like ${card.title}`}
              title="More like this"
              className="press grid h-9 w-9 place-items-center rounded-full border border-white/15 bg-white/10 text-white/80 backdrop-blur-xl hover:border-white/40 hover:bg-white/20 hover:text-white disabled:opacity-40"
            >
              <Layers className="h-4 w-4" />
            </button>
          </div>
        </div>
      </motion.div>
    </motion.article>
  );
}

export function SkeletonCard({ compact }: { compact?: boolean }) {
  return (
    <div className={cn("shrink-0", compact ? "w-[168px]" : "w-[216px] sm:w-[232px]")} aria-hidden>
      <div className="skeleton aspect-[2/3] rounded-[28px] border border-white/10" />
    </div>
  );
}
