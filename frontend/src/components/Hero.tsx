"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight, Check, Search, Users, X } from "lucide-react";
import BlurText from "./bits/BlurText";
import LogoLoop from "./bits/LogoLoop";
import Magnet from "./bits/Magnet";
import ShinyText from "./bits/ShinyText";
import { HeroRays } from "./HeroRays";
import { SkeletonCard } from "./MovieCard";
import { Poster } from "./PosterArt";
import { PromptBar } from "./PromptBar";
import { useWorkspace } from "./WorkspaceProvider";
import { api } from "@/lib/api";
import { BRAND } from "@/lib/brand";
import { creditLine } from "@/lib/credit";
import { openProject } from "@/lib/project";
import { ProjectEyebrow } from "./ProjectEyebrow";
import { cn } from "@/lib/utils";
import type { MovieSummary } from "@/lib/types";

const EXAMPLES = [
  "A lighthearted comedy for tonight",
  "Underrated science-fiction movies",
  "I loved Inception and The Prestige",
  "Highly rated thriller, nothing too violent",
  "Something like Interstellar",
  "Feel-good romance from the 90s",
];

function TasteStarter() {
  const { meta, updateProfile, refresh, busy, profile } = useWorkspace();
  const [genres, setGenres] = useState<string[]>([]);
  const [picked, setPicked] = useState<MovieSummary[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MovieSummary[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) return;
    const t = setTimeout(async () => {
      setSearching(true);
      try {
        setResults((await api.searchMovies(q, 6)).filter((m) => !picked.some((p) => p.movie_id === m.movie_id)));
        setError(null);
      } catch {
        setError("Search is unavailable right now.");
      } finally {
        setSearching(false);
      }
    }, 220);
    return () => clearTimeout(t);
  }, [query, picked]);

  const canGo = genres.length > 0 || picked.length > 0;
  const go = async () => {
    await updateProfile({
      genres,
      liked_ids: [...new Set([...(profile?.liked_ids ?? []), ...picked.map((m) => m.movie_id)])],
    });
    const parts = [genres.length ? genres.join(", ") : null, picked.length ? `I like ${picked.map((m) => m.title).join(", ")}` : null].filter(Boolean);
    await refresh(`Start from my taste: ${parts.join(" · ")}`);
  };

  return (
    <section aria-labelledby="taste-title" className="glass spec relative mx-auto w-full max-w-3xl rounded-[34px] p-6 sm:p-8">
      <h2 id="taste-title" className="font-display text-[2rem] leading-none">
        Prefer to <em>show</em> me your taste?
      </h2>
      <p className="mt-2 text-[13.5px] text-white/50">Pick a few genres and films you love. No account needed, and you can change it anytime.</p>

      <fieldset className="mt-6">
        <legend className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/45">Favourite genres</legend>
        <div className="mt-3 flex flex-wrap gap-2">
          {(meta?.genres ?? []).map((g) => {
            const on = genres.includes(g);
            return (
              <button
                key={g}
                type="button"
                aria-pressed={on}
                onClick={() => setGenres((s) => (on ? s.filter((x) => x !== g) : [...s, g].slice(-4)))}
                className={cn("press flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[13px]", on ? "border-white bg-white text-black" : "border-white/15 bg-white/[0.06] text-white/80 hover:border-white/40")}
              >
                {on && <Check className="h-3.5 w-3.5" />}
                {g}
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-[11.5px] text-white/30">Up to four.</p>
      </fieldset>

      <div className="mt-6">
        <label htmlFor="movie-search" className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/45">Movies you&apos;ve loved</label>
        <div className="relative mt-3">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-white/40" aria-hidden />
          <input
            id="movie-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search MovieLens titles…"
            autoComplete="off"
            className="glass-pill w-full rounded-full py-3 pl-11 pr-4 text-[15px] text-white placeholder:text-white/35 focus:border-white/50 focus:outline-none"
          />
          {(results.length > 0 || searching) && query.trim().length >= 2 && (
            <ul className="glass glass-strong absolute inset-x-0 top-[calc(100%+8px)] z-20 overflow-hidden rounded-3xl py-1.5" role="listbox" aria-label="Matching movies">
              {searching && results.length === 0 && <li className="px-4 py-3 text-[13px] text-white/40">Searching…</li>}
              {results.map((m) => (
                <li key={m.movie_id} role="option" aria-selected={false}>
                  <button
                    type="button"
                    onClick={() => { setPicked((p) => [...p, m].slice(-8)); setQuery(""); setResults([]); }}
                    className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-[14px] hover:bg-white/10 focus-visible:bg-white/10"
                  >
                    <span className="truncate">{m.title} <span className="text-white/40">{m.year}</span></span>
                    <span className="shrink-0 font-mono text-[11px] text-white/35">{m.genres.slice(0, 2).join(" · ")}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {error && <p className="mt-2 text-[12px] text-white/50" role="alert">{error}</p>}
        {picked.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-2">
            {picked.map((m) => (
              <li key={m.movie_id} className="glass-pill flex items-center gap-2 rounded-full py-1.5 pl-3.5 pr-1.5 text-[13px]">
                {m.title}
                <button type="button" aria-label={`Remove ${m.title}`} onClick={() => setPicked((p) => p.filter((x) => x.movie_id !== m.movie_id))} className="press grid h-6 w-6 place-items-center rounded-full bg-white/10 hover:bg-white/25">
                  <X className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Magnet padding={60} magnetStrength={5} disabled={!canGo || busy} wrapperClassName="mt-7 block sm:inline-block">
        <button
          type="button"
          disabled={!canGo || busy}
          onClick={() => void go()}
          className="press flex w-full items-center justify-center gap-2 rounded-full bg-white py-3.5 text-[15px] font-medium text-black disabled:bg-white/15 disabled:text-white/40 sm:w-auto sm:px-8"
        >
          Show me my first picks <ArrowRight className="h-4 w-4" />
        </button>
      </Magnet>
    </section>
  );
}

/** The loop renders aria-hidden duplicates so it can scroll seamlessly; keep them clickable but out of the keyboard tab order. */
function useSkipHiddenCopies(ref: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const apply = () => el.querySelectorAll('[aria-hidden="true"] button').forEach((b) => b.setAttribute("tabindex", "-1"));
    apply();
    const mo = new MutationObserver(apply);
    mo.observe(el, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, [ref]);
}

function PosterTicker() {
  const { trending, ready, posters, moreLike, setSpotlight, busy } = useWorkspace();
  const tickerRef = useRef<HTMLDivElement>(null);
  useSkipHiddenCopies(tickerRef);
  const [onScreen, setOnScreen] = useState(true);
  useEffect(() => {
    const el = tickerRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([entry]) => setOnScreen(entry.isIntersecting), { rootMargin: "120px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // each poster is a real MovieLens title; the loop (React Bits "LogoLoop") scrolls continuously and pauses on hover
  const logos = useMemo(
    () =>
      trending.map((m) => ({
        ariaLabel: `Find movies like ${m.title}`,
        title: m.title,
        node: (
          <button
            type="button"
            disabled={busy}
            onClick={() => void moreLike(m)}
            onPointerEnter={() => setSpotlight({ movieId: m.movie_id, title: m.title, year: m.year })}
            onPointerLeave={() => setSpotlight(null)}
            onFocus={() => setSpotlight({ movieId: m.movie_id, title: m.title, year: m.year })}
            onBlur={() => setSpotlight(null)}
            aria-label={`Find movies like ${m.title}`}
            className="glass glass-flat group relative block h-[250px] w-[168px] overflow-hidden rounded-3xl text-left [container-type:inline-size] [&_img]:grayscale [&_img]:transition-[filter] [&_img]:duration-700 hover:[&_img]:grayscale-0 focus-visible:[&_img]:grayscale-0"
          >
            <Poster title={m.title} year={m.year} src={posters[m.movie_id]} />
            <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/10 to-transparent" aria-hidden />
            <div className="absolute inset-x-0 bottom-0 p-3">
              <p className="font-display text-[1.3rem] leading-[1.05]">{m.title}</p>
              <p className="mt-0.5 font-mono text-[10.5px] text-white/55">
                {m.year} · {m.mean_rating?.toFixed(1)}★
              </p>
            </div>
          </button>
        ),
      })),
    [trending, posters, busy, moreLike, setSpotlight],
  );

  return (
    <section aria-labelledby="trending-title" className="mx-auto w-full max-w-5xl">
      <div className="flex items-end justify-between px-1">
        <h2 id="trending-title" className="font-display text-[1.9rem] leading-none">
          Most rated on <em>MovieLens</em>
        </h2>
        <span className="hidden text-[12px] text-white/40 sm:block">Tap one to find more like it</span>
      </div>
      <div ref={tickerRef} className="mt-5 -mx-4 sm:-mx-6">
        {!ready || trending.length === 0 ? (
          <div className="flex gap-5 overflow-hidden px-4 sm:px-6" aria-hidden>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <SkeletonCard key={i} compact />
            ))}
          </div>
        ) : (
          <LogoLoop
            logos={logos}
            speed={onScreen ? 38 : 0}
            direction="left"
            logoHeight={250}
            gap={20}
            hoverSpeed={0}
            fadeOut
            fadeOutColor="#050506"
            scaleOnHover
            ariaLabel="Most-rated movies on MovieLens"
          />
        )}
      </div>
    </section>
  );
}

export function Hero() {
  const { send, busy, postersEnabled } = useWorkspace();
  const reduce = useReducedMotion();

  const rise = (delay: number) => ({
    initial: reduce ? false : { opacity: 0, y: 26, filter: "blur(12px)" },
    animate: { opacity: 1, y: 0, filter: "blur(0px)" },
    transition: { duration: 0.9, delay, ease: [0.22, 1, 0.36, 1] as const },
  });

  return (
    <div className="relative">
      <HeroRays />
      <div className="relative mx-auto flex w-full flex-col items-center gap-16 px-4 pb-24 pt-32 sm:px-6 sm:pt-40">
        <div className="flex w-full max-w-3xl flex-col items-center text-center">
          <motion.div {...rise(0.05)}>
            <ProjectEyebrow />
          </motion.div>

          <h1 className="sr-only">What are we watching tonight?</h1>
          <div aria-hidden className="mt-7 font-display text-[clamp(3.2rem,9vw,6.4rem)] leading-[0.94] tracking-[-0.02em]">
            <BlurText text="What are we watching" delay={120} animateBy="words" direction="top" className="justify-center" />
            <motion.span
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.9, duration: 1 }}
              className="block italic"
            >
              <ShinyText text="tonight?" color="rgba(245,245,247,0.42)" shineColor="#ffffff" speed={3.4} delay={0.6} shineWidth={0.35} />
            </motion.span>
          </div>

          <motion.p {...rise(0.3)} className="mt-6 max-w-xl text-[17px] leading-relaxed text-white/55">
            Describe a mood, a genre, or a film you loved. {BRAND.name} finds matches from real viewer ratings, and tells you exactly why.
          </motion.p>
          <motion.div {...rise(0.45)} className="mt-10 w-full">
            <PromptBar large autoFocus />
          </motion.div>
          <motion.ul {...rise(0.6)} className="mt-6 flex flex-wrap justify-center gap-2" aria-label="Example prompts">
            {EXAMPLES.map((e) => (
              <li key={e}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void send(e)}
                  className="glass-pill press rounded-full px-4 py-2 text-[13.5px] text-white/80 hover:border-white/40 hover:text-white disabled:opacity-40"
                >
                  {e}
                </button>
              </li>
            ))}
          </motion.ul>
        </div>

        <motion.div {...rise(0.75)} className="w-full">
          <PosterTicker />
        </motion.div>
        <motion.div {...rise(0.9)} className="w-full">
          <TasteStarter />
        </motion.div>
        <div className="-mt-6 flex flex-col items-center gap-4">
          <button type="button" onClick={() => openProject("team")} className="glass-pill press flex items-center gap-2 rounded-full px-4 py-2 text-[12.5px] text-white/75 hover:border-white/40 hover:text-white">
            <Users className="h-3.5 w-3.5" aria-hidden /> Meet the team
          </button>
          <p className="max-w-xl text-center text-[11.5px] leading-relaxed text-white/30">
            {creditLine ? `${creditLine}. ` : "RS Mini Project: a Recommendation Systems course project. "}
            Ratings and tags: MovieLens (GroupLens Research).
            {postersEnabled && " Posters: TMDB. This product uses the TMDB API but is not endorsed or certified by TMDB."}
          </p>
        </div>
      </div>
    </div>
  );
}
