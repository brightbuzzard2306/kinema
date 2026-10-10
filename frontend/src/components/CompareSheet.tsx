"use client";

import { useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { motion } from "motion/react";
import { Info, RefreshCw, X } from "lucide-react";
import { Poster } from "./PosterArt";
import { useWorkspace } from "./WorkspaceProvider";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { CompareResponse, CompareStrategy, MovieCardData } from "@/lib/types";

const COLUMNS: { key: CompareStrategy; name: string; how: string }[] = [
  { key: "popular", name: "Popular", how: "Highest Bayesian-average rating. The same list for everyone." },
  { key: "content", name: "Content", how: "Movies whose genres, tags and titles resemble what you liked." },
  { key: "collaborative", name: "People like you", how: "Movies loved by people who liked the same movies you did." },
  { key: "hybrid", name: "Hybrid", how: "A weighted blend of all three. This is what Kinema uses." },
];

const REGIME: Record<string, string> = {
  cold: "cold-start weights",
  thin: "few-likes weights",
  blend: "blended weights",
  warm: "warm-user weights",
};

type Loaded = { key: string; data?: CompareResponse; error?: string };

function Mini({ card, shared, active, onHover, onOpen }: { card: MovieCardData; shared: number; active: boolean; onHover: (id: number | null) => void; onOpen: () => void }) {
  const { posters } = useWorkspace();
  return (
    <button
      type="button"
      onClick={onOpen}
      onPointerEnter={() => onHover(card.movie_id)}
      onPointerLeave={() => onHover(null)}
      onFocus={() => onHover(card.movie_id)}
      onBlur={() => onHover(null)}
      aria-label={`${card.title}${card.year ? `, ${card.year}` : ""}${shared > 1 ? `, also in ${shared - 1} other list${shared > 2 ? "s" : ""}` : ""}. Open details`}
      className={cn(
        "press flex w-full items-center gap-3 rounded-2xl border p-2 text-left transition-colors",
        active ? "border-white/70 bg-white/[0.12]" : "border-transparent hover:border-white/20 hover:bg-white/[0.06]",
      )}
    >
      <span className="relative block h-[66px] w-[44px] shrink-0 overflow-hidden rounded-lg border border-white/10 [container-type:inline-size]">
        <Poster title={card.title} year={card.year} src={posters[card.movie_id]} compact />
      </span>
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 block font-display text-[1.1rem] leading-[1.1]">{card.title}</span>
        <span className="mt-0.5 block font-mono text-[10.5px] text-white/45">
          {card.year ?? "—"}
          {card.mean_rating !== null && ` · ${card.mean_rating.toFixed(1)}★`}
        </span>
      </span>
      {shared > 1 && (
        <span
          title={`Also ranked by ${shared - 1} other strateg${shared > 2 ? "ies" : "y"}`}
          className="grid h-6 min-w-6 shrink-0 place-items-center rounded-full bg-white px-1.5 font-mono text-[10px] font-semibold text-black"
        >
          ×{shared}
        </span>
      )}
    </button>
  );
}

export function CompareSheet() {
  const { compareOpen, setCompareOpen, compare, prefetchPosters, profile, openWhy } = useWorkspace();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  // re-run whenever the panel opens or the taste profile changes while it is open
  const key = compareOpen
    ? `${attempt}|${profile ? JSON.stringify([profile.liked_ids, profile.disliked_ids, profile.genres, profile.excluded_genres, profile.min_rating, profile.year_min, profile.year_max, profile.novelty]) : ""}`
    : "";

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    compare()
      .then((data) => !cancelled && setLoaded({ key, data }))
      .catch((e) => !cancelled && setLoaded({ key, error: e instanceof ApiError ? e.message : "Couldn't compare the strategies." }));
    return () => {
      cancelled = true;
    };
  }, [key, compare]);

  const loading = !!key && loaded?.key !== key;
  const shownIds = loaded?.data ? Object.values(loaded.data.columns).flatMap((c) => c.movies.map((m) => m.movie_id)) : null;
  useEffect(() => {
    if (shownIds?.length) prefetchPosters(shownIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded?.data, prefetchPosters]);
  const data = loaded?.key === key ? loaded.data : undefined;
  const error = loaded?.key === key ? loaded.error : undefined;

  const counts = useMemo(() => {
    const c = new Map<number, number>();
    if (data) COLUMNS.forEach(({ key: k }) => data.columns[k].movies.forEach((m) => c.set(m.movie_id, (c.get(m.movie_id) ?? 0) + 1)));
    return c;
  }, [data]);

  const summary = useMemo(() => {
    if (!data) return null;
    const hybrid = new Set(data.columns.hybrid.movies.map((m) => m.movie_id));
    const total = data.columns.hybrid.movies.length;
    const shareWith = (k: CompareStrategy) => data.columns[k].movies.filter((m) => hybrid.has(m.movie_id)).length;
    return `Hybrid shares ${shareWith("collaborative")} of ${total} picks with People like you, ${shareWith("content")} with Content and ${shareWith("popular")} with Popular.`;
  }, [data]);

  const signalText = data
    ? data.signals.liked === 0 && data.signals.genres.length === 0
      ? "No taste signal yet: Content and People like you have nothing to work from, so they fall back to Popular."
      : [
          data.signals.liked ? `${data.signals.liked} liked movie${data.signals.liked > 1 ? "s" : ""}` : null,
          data.signals.genres.length ? `genres: ${data.signals.genres.join(", ")}` : null,
          data.signals.excluded_genres.length ? `excluding ${data.signals.excluded_genres.join(", ")}` : null,
          data.signals.disliked ? `${data.signals.disliked} disliked` : null,
        ]
          .filter(Boolean)
          .join(" · ")
    : "";

  return (
    <Dialog.Root open={compareOpen} onOpenChange={setCompareOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-[fade-in_0.3s_ease-out]" />
        <Dialog.Content
          aria-describedby="compare-desc"
          className="glass glass-strong thin-scrollbar fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[min(96vw,1180px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-[34px] p-5 outline-none sm:p-8 data-[state=open]:animate-[sheet-in_0.45s_var(--ease-out)]"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="font-display text-[2.3rem] leading-none sm:text-[2.8rem]">
                Same you, <em className="text-white/60">four algorithms</em>
              </Dialog.Title>
              <p id="compare-desc" className="mt-3 max-w-2xl text-[13.5px] leading-relaxed text-white/55">
                Every list below ranks the same movies for the same taste profile. A number badge means the movie also appears in other lists.
              </p>
            </div>
            <Dialog.Close className="glass-pill press grid h-9 w-9 shrink-0 place-items-center rounded-full" aria-label="Close comparison">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          {data && (
            <div className="mt-5 space-y-1.5 text-[13px]">
              <p className="text-white/80">{summary}</p>
              <p className="flex items-start gap-2 text-white/45">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /> {signalText}
              </p>
            </div>
          )}

          {error && (
            <div className="mt-8 rounded-3xl border border-white/15 bg-black/30 p-8 text-center" role="alert">
              <p className="text-[15px] text-white/80">{error}</p>
              <button type="button" onClick={() => setAttempt((n) => n + 1)} className="press mx-auto mt-5 flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-[13px] font-medium text-black">
                <RefreshCw className="h-4 w-4" /> Try again
              </button>
            </div>
          )}

          {!error && (
            <div className="thin-scrollbar -mx-5 mt-6 grid snap-x snap-mandatory auto-cols-[82%] grid-flow-col gap-4 overflow-x-auto px-5 pb-2 sm:-mx-8 sm:px-8 md:mx-0 md:auto-cols-fr md:overflow-visible md:px-0">
              {COLUMNS.map((col, ci) => {
                const column = data?.columns[col.key];
                const fellBack = column && column.strategy_used !== col.key;
                const ndcg = data?.offline_ndcg?.[col.key];
                return (
                  <section
                    key={col.key}
                    aria-labelledby={`cmp-${col.key}`}
                    className={cn(
                      "snap-start rounded-3xl border p-4",
                      col.key === "hybrid" ? "border-white/35 bg-white/[0.08]" : "border-white/12 bg-white/[0.035]",
                    )}
                  >
                    <h3 id={`cmp-${col.key}`} className="font-display text-[1.6rem] leading-none">
                      {col.name}
                    </h3>
                    <p className="mt-2 min-h-[3.2em] text-[12px] leading-snug text-white/50">{col.how}</p>
                    <p className="mt-2 font-mono text-[10.5px] text-white/40">
                      {ndcg !== undefined ? `offline NDCG@10 ${ndcg.toFixed(3)}` : " "}
                      {col.key === "hybrid" && column?.regime && ` · ${REGIME[column.regime]}`}
                    </p>
                    {fellBack && <p className="mt-2 rounded-xl bg-white/[0.07] px-2.5 py-1.5 text-[11.5px] leading-snug text-white/65">Not enough taste signal, so this shows Popular.</p>}

                    <ul className="mt-3 space-y-1" aria-label={`${col.name} picks`}>
                      {loading &&
                        [0, 1, 2, 3, 4].map((i) => (
                          <li key={i} aria-hidden>
                            <div className="skeleton h-[82px] rounded-2xl" />
                          </li>
                        ))}
                      {!loading && column && column.movies.length === 0 && <li className="px-2 py-4 text-[12.5px] text-white/45">Nothing matches your filters.</li>}
                      {!loading &&
                        column?.movies.map((m, i) => (
                          <motion.li key={m.movie_id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: ci * 0.05 + i * 0.05, ease: [0.22, 1, 0.36, 1] }}>
                            <Mini card={m} shared={counts.get(m.movie_id) ?? 1} active={hover === m.movie_id} onHover={setHover} onOpen={() => openWhy(m)} />
                          </motion.li>
                        ))}
                    </ul>
                  </section>
                );
              })}
            </div>
          )}

          <p className="mt-5 text-[11.5px] leading-relaxed text-white/35">
            Offline scores are real measurements from the evaluation run (higher is better). They compare the methods on past data, not on this one list.
          </p>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
