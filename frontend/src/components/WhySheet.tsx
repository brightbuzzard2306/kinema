"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { motion } from "motion/react";
import { Layers, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { ConfidenceDots } from "./MovieCard";
import { Poster } from "./PosterArt";
import { useWorkspace } from "./WorkspaceProvider";
import { cn } from "@/lib/utils";
import type { ComponentName } from "@/lib/types";

const COMPONENTS: { key: ComponentName; label: string; hint: string }[] = [
  { key: "collaborative", label: "People like you", hint: "Item-item collaborative filtering on MovieLens ratings" },
  { key: "content", label: "Similar content", hint: "TF-IDF cosine similarity over genres, tags and title words" },
  { key: "popularity", label: "Quality & popularity", hint: "Bayesian-average rating blended with rating volume" },
  { key: "preference", label: "Your stated genres", hint: "Share of your requested genres this movie matches" },
];

const KIND_LABEL: Record<string, string> = {
  genre: "Genre match",
  content: "Content",
  collaborative: "Rating patterns",
  popularity: "Quality",
  discovery: "Discovery",
};

export function WhySheet() {
  const { why, openWhy, posters, feedbackFor, giveFeedback, moreLike, busy } = useWorkspace();
  const feedback = why ? feedbackFor(why.movie_id) : null;

  return (
    <Dialog.Root open={!!why} onOpenChange={(o) => !o && openWhy(null)}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-[fade-in_0.3s_ease-out]" />
        <Dialog.Content
          aria-describedby="why-desc"
          className="glass glass-strong fixed left-1/2 top-1/2 z-50 max-h-[88dvh] w-[min(94vw,760px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-[34px] p-0 outline-none thin-scrollbar data-[state=open]:animate-[sheet-in_0.45s_var(--ease-out)]"
        >
          {why && (
            <div className="grid gap-0 sm:grid-cols-[240px_1fr]">
              <div className="relative hidden min-h-[360px] sm:block [container-type:inline-size]">
                <Poster title={why.title} year={why.year} src={posters[why.movie_id]} eager />
                <div className="absolute inset-0 bg-gradient-to-r from-transparent to-black/60" aria-hidden />
              </div>
              <div className="p-6 sm:p-8">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <Dialog.Title className="font-display text-[2.4rem] leading-none tracking-tight">{why.title}</Dialog.Title>
                    <p id="why-desc" className="mt-2 text-[13px] text-white/55">
                      {why.year ?? "—"} · {why.genres.join(", ") || "No genres listed"}
                    </p>
                  </div>
                  <Dialog.Close className="glass-pill press grid h-9 w-9 shrink-0 place-items-center rounded-full" aria-label="Close">
                    <X className="h-4 w-4" />
                  </Dialog.Close>
                </div>

                <div className="mt-5 flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="glass-pill flex items-center gap-2 rounded-full px-3 py-1.5">
                    <ConfidenceDots level={why.confidence} /> <span className="capitalize">{why.confidence} confidence</span>
                  </span>
                  {why.mean_rating !== null && (
                    <span className="glass-pill rounded-full px-3 py-1.5 font-mono">
                      {why.mean_rating.toFixed(2)} / 5 · {why.n_ratings} MovieLens ratings
                    </span>
                  )}
                </div>
                <p className="mt-2 text-[12px] text-white/40">{why.confidence_basis}. The rating is the MovieLens community average, not IMDb or TMDB.</p>

                <h4 className="mt-7 text-[11px] font-medium uppercase tracking-[0.18em] text-white/45">Why it was picked</h4>
                <ul className="mt-3 space-y-2.5">
                  {why.reasons.length === 0 && <li className="text-[14px] text-white/60">Ranked by overall quality and popularity.</li>}
                  {why.reasons.map((r, i) => (
                    <li key={i} className="flex gap-3 text-[14.5px] leading-snug text-white/90">
                      <span className="mt-0.5 shrink-0 rounded-full border border-white/20 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-white/55">
                        {KIND_LABEL[r.kind] ?? r.kind}
                      </span>
                      <span>{r.text}</span>
                    </li>
                  ))}
                </ul>

                <h4 className="mt-7 text-[11px] font-medium uppercase tracking-[0.18em] text-white/45">How the score was built</h4>
                <p className="mt-1 text-[12px] text-white/40">
                  Each signal is normalised to 0–1 among candidates, then blended by weight. Unavailable signals are skipped and their weight is redistributed.
                </p>
                <div className="mt-4 space-y-3.5">
                  {COMPONENTS.map(({ key, label, hint }) => {
                    const value = why.components[key];
                    const weight = why.weights_used[key];
                    const active = value !== null && value !== undefined && weight !== undefined;
                    return (
                      <div key={key} title={hint} className={cn(!active && "opacity-40")}>
                        <div className="flex items-baseline justify-between text-[13px]">
                          <span>{label}</span>
                          <span className="font-mono text-[11px] text-white/55">
                            {active ? `${value!.toFixed(2)} × ${Math.round(weight! * 100)}%` : "not used"}
                          </span>
                        </div>
                        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10">
                          <motion.div
                            className="h-full rounded-full bg-white"
                            initial={{ width: 0 }}
                            animate={{ width: active ? `${value! * 100}%` : 0 }}
                            transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
                <p className="mt-4 font-mono text-[11px] text-white/40">final score {why.score.toFixed(3)}</p>

                <div className="mt-7 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => giveFeedback(why.movie_id, feedback === "like" ? "clear" : "like")}
                    aria-pressed={feedback === "like"}
                    className={cn("press flex items-center gap-2 rounded-full border px-4 py-2.5 text-[13px]", feedback === "like" ? "border-white bg-white text-black" : "border-white/20 bg-white/10")}
                  >
                    <ThumbsUp className="h-4 w-4" /> {feedback === "like" ? "Liked" : "Like"}
                  </button>
                  <button
                    type="button"
                    onClick={() => giveFeedback(why.movie_id, feedback === "dislike" ? "clear" : "dislike")}
                    aria-pressed={feedback === "dislike"}
                    className={cn("press flex items-center gap-2 rounded-full border px-4 py-2.5 text-[13px]", feedback === "dislike" ? "border-white bg-white text-black" : "border-white/20 bg-white/10")}
                  >
                    <ThumbsDown className="h-4 w-4" /> {feedback === "dislike" ? "Disliked" : "Dislike"}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      const target = why;
                      openWhy(null);
                      void moreLike(target);
                    }}
                    className="press flex items-center gap-2 rounded-full bg-white px-4 py-2.5 text-[13px] font-medium text-black disabled:opacity-40"
                  >
                    <Layers className="h-4 w-4" /> More like this
                  </button>
                </div>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
