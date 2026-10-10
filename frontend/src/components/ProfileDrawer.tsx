"use client";

import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Check, Minus, RefreshCw, ThumbsDown, ThumbsUp, X } from "lucide-react";
import RubberSegment from "./bits/RubberSegment";
import { useWorkspace } from "./WorkspaceProvider";
import { cn } from "@/lib/utils";
import type { Strategy } from "@/lib/types";

const STRATEGIES: { value: Strategy; label: string; short: string; blurb: string }[] = [
  { value: "hybrid", label: "Hybrid", short: "Hybrid", blurb: "Blends similar content, people with similar taste, and quality. Best overall." },
  { value: "collaborative", label: "People like you", short: "People", blurb: "Item-item collaborative filtering: what fans of your liked movies also loved." },
  { value: "content", label: "Similar content", short: "Content", blurb: "TF-IDF similarity over genres, tags and title words." },
  { value: "popular", label: "Popular", short: "Popular", blurb: "Bayesian-weighted ratings. The cold-start baseline." },
];

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-white/10 py-6 first:border-t-0 first:pt-0">
      <h3 className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/45">{title}</h3>
      {hint && <p className="mt-1 text-[12px] text-white/35">{hint}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Slider({
  id, label, value, min, max, step, format, onCommit, left, right,
}: {
  id: string; label: string; value: number; min: number; max: number; step: number;
  format: (v: number) => string; onCommit: (v: number) => void; left: string; right: string;
}) {
  const [draft, setDraft] = useState(value);
  const [seen, setSeen] = useState(value);
  if (seen !== value) {
    // external value changed (e.g. profile reset): adopt it during render instead of in an effect
    setSeen(value);
    setDraft(value);
  }
  const fill = `${((draft - min) / (max - min)) * 100}%`;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-[14px] text-white">{label}</label>
        <span className="font-mono text-[12px] text-white/60">{format(draft)}</span>
      </div>
      <input
        id={id}
        type="range"
        className="kinema-range mt-1"
        min={min} max={max} step={step} value={draft}
        style={{ "--fill": fill } as React.CSSProperties}
        onChange={(e) => setDraft(Number(e.target.value))}
        onPointerUp={() => onCommit(draft)}
        onKeyUp={() => onCommit(draft)}
        onBlur={() => draft !== value && onCommit(draft)}
      />
      <div className="flex justify-between text-[11px] text-white/35"><span>{left}</span><span>{right}</span></div>
    </div>
  );
}

export function ProfileDrawer() {
  const { profileOpen, setProfileOpen, profile, meta, updateProfile, titleOf, refresh, newChat, busy } = useWorkspace();
  const [years, setYears] = useState({ min: "", max: "" });
  const yearsKey = `${profile?.year_min ?? ""}|${profile?.year_max ?? ""}|${profileOpen}`;
  const [seenYears, setSeenYears] = useState("");
  if (seenYears !== yearsKey) {
    setSeenYears(yearsKey);
    setYears({ min: profile?.year_min?.toString() ?? "", max: profile?.year_max?.toString() ?? "" });
  }

  if (!profile) return null;
  const genres = meta?.genres ?? [];

  // tri-state genre chip: neutral -> wanted -> excluded -> neutral
  const cycleGenre = (g: string) => {
    if (profile.genres.includes(g)) {
      void updateProfile({ genres: profile.genres.filter((x) => x !== g), excluded_genres: [...profile.excluded_genres, g] });
    } else if (profile.excluded_genres.includes(g)) {
      void updateProfile({ excluded_genres: profile.excluded_genres.filter((x) => x !== g) });
    } else {
      void updateProfile({ genres: [...profile.genres, g].slice(-6) });
    }
  };

  const commitYears = () => {
    const parse = (s: string) => (s.trim() === "" ? null : Math.min(2100, Math.max(1880, parseInt(s, 10))));
    const a = parse(years.min);
    const b = parse(years.max);
    if ((a !== null && Number.isNaN(a)) || (b !== null && Number.isNaN(b))) return;
    if (a !== profile.year_min || b !== profile.year_max) void updateProfile({ year_min: a, year_max: b });
  };

  return (
    <Dialog.Root open={profileOpen} onOpenChange={setProfileOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm data-[state=open]:animate-[fade-in_0.3s_ease-out]" />
        <Dialog.Content
          aria-describedby="profile-desc"
          className="glass glass-strong thin-scrollbar fixed bottom-0 right-0 top-0 z-50 flex w-full flex-col overflow-y-auto rounded-none border-y-0 border-r-0 p-6 outline-none sm:w-[440px] sm:rounded-l-[34px] sm:p-8 data-[state=open]:animate-[drawer-in_0.5s_var(--ease-out)]"
        >
          <div className="flex items-start justify-between">
            <div>
              <Dialog.Title className="font-display text-[2.2rem] leading-none">Your taste</Dialog.Title>
              <Dialog.Description id="profile-desc" className="mt-2 max-w-[300px] text-[13px] leading-relaxed text-white/50">
                This is exactly what the recommender uses. Edit anything; it applies to your next picks.
              </Dialog.Description>
            </div>
            <Dialog.Close className="glass-pill press grid h-9 w-9 place-items-center rounded-full" aria-label="Close profile"><X className="h-4 w-4" /></Dialog.Close>
          </div>

          <div className="mt-8 flex-1">
            <Section title="Strategy">
              <RubberSegment
                aria-label="Recommendation strategy"
                items={STRATEGIES.map((x) => ({ value: x.value, label: x.short }))}
                value={profile.strategy}
                onChange={(v) => void updateProfile({ strategy: v as Strategy })}
                trackColor="rgba(255,255,255,0.09)"
                thumbColor="#ffffff"
                textColor="rgba(245,245,247,0.72)"
                activeTextColor="#050506"
                size="md"
                equalSlots
                className="w-full"
              />
              <p className="mt-3 text-[12.5px] leading-relaxed text-white/50">{STRATEGIES.find((s) => s.value === profile.strategy)?.blurb}</p>
            </Section>

            <Section title="Discovery">
              <Slider id="novelty" label="Familiar ↔ Hidden gems" value={profile.novelty} min={0} max={1} step={0.05}
                format={(v) => (v < 0.34 ? "Familiar" : v < 0.67 ? "Balanced" : "Discovery")} left="Blockbusters" right="Lesser-known"
                onCommit={(v) => v !== profile.novelty && updateProfile({ novelty: v })} />
              <div className="mt-5">
                <Slider id="min-rating" label="Minimum MovieLens rating" value={profile.min_rating ?? 0} min={0} max={4.5} step={0.5}
                  format={(v) => (v === 0 ? "Any" : `${v.toFixed(1)}★ +`)} left="Any" right="4.5★"
                  onCommit={(v) => (v || null) !== profile.min_rating && updateProfile({ min_rating: v === 0 ? null : v })} />
              </div>
              <div className="mt-5">
                <p className="text-[14px]">Release years</p>
                <div className="mt-2 flex items-center gap-3">
                  {(["min", "max"] as const).map((k) => (
                    <label key={k} className="flex-1">
                      <span className="sr-only">{k === "min" ? "From year" : "To year"}</span>
                      <input
                        inputMode="numeric" maxLength={4} placeholder={k === "min" ? "From" : "To"} value={years[k]}
                        onChange={(e) => setYears((y) => ({ ...y, [k]: e.target.value.replace(/\D/g, "") }))}
                        onBlur={commitYears} onKeyDown={(e) => e.key === "Enter" && commitYears()}
                        className="glass-pill w-full rounded-2xl px-4 py-2.5 font-mono text-[13px] text-white placeholder:text-white/30 focus:border-white/50 focus:outline-none"
                      />
                    </label>
                  ))}
                </div>
              </div>
            </Section>

            <Section title="Genres" hint="Tap once to want it, twice to exclude it, again to clear.">
              <div className="flex flex-wrap gap-2">
                {genres.map((g) => {
                  const state = profile.genres.includes(g) ? "want" : profile.excluded_genres.includes(g) ? "exclude" : "none";
                  return (
                    <button
                      key={g}
                      type="button"
                      onClick={() => cycleGenre(g)}
                      aria-label={`${g}: ${state === "want" ? "wanted" : state === "exclude" ? "excluded" : "neutral"}`}
                      className={cn(
                        "press flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px]",
                        state === "want" && "border-white bg-white text-black",
                        state === "exclude" && "border-white/30 bg-transparent text-white/50 line-through decoration-white/60",
                        state === "none" && "border-white/15 bg-white/[0.06] text-white/80 hover:border-white/40",
                      )}
                    >
                      {state === "want" && <Check className="h-3.5 w-3.5" />}
                      {state === "exclude" && <Minus className="h-3.5 w-3.5" />}
                      {g}
                    </button>
                  );
                })}
              </div>
            </Section>

            {([["Liked", profile.liked_ids, ThumbsUp, "like"], ["Disliked", profile.disliked_ids, ThumbsDown, "dislike"]] as const).map(([title, ids, Icon]) => (
              <Section key={title} title={`${title} movies`}>
                {ids.length === 0 ? (
                  <p className="text-[13px] text-white/35">Nothing yet. Use the thumbs on any card, or tell me in chat.</p>
                ) : (
                  <ul className="flex flex-wrap gap-2">
                    {ids.map((id) => (
                      <li key={id} className="glass-pill flex items-center gap-2 rounded-full py-1.5 pl-3 pr-1.5 text-[13px]">
                        <Icon className="h-3.5 w-3.5 text-white/60" aria-hidden />
                        <span className="max-w-[180px] truncate">{titleOf(id)}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${titleOf(id)}`}
                          onClick={() => updateProfile(title === "Liked" ? { liked_ids: ids.filter((x) => x !== id) } : { disliked_ids: ids.filter((x) => x !== id) })}
                          className="press grid h-6 w-6 place-items-center rounded-full bg-white/10 hover:bg-white/25"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
            ))}
          </div>

          <div className="sticky bottom-0 -mx-6 mt-4 flex gap-2 border-t border-white/10 bg-black/30 px-6 py-4 backdrop-blur-xl sm:-mx-8 sm:px-8">
            <button
              type="button"
              disabled={busy}
              onClick={() => { setProfileOpen(false); void refresh(); }}
              className="press flex flex-1 items-center justify-center gap-2 rounded-full bg-white py-3 text-[14px] font-medium text-black disabled:opacity-50"
            >
              <RefreshCw className="h-4 w-4" /> Apply & refresh picks
            </button>
            <button
              type="button"
              onClick={() => { void newChat(false); setProfileOpen(false); }}
              className="press rounded-full border border-white/20 px-4 py-3 text-[13px] text-white/75 hover:border-white/50"
            >
              Reset all
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
