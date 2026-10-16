"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, FlaskConical, Loader2, Search } from "lucide-react";
import { Backdrop } from "@/components/Backdrop";
import { Logo } from "@/components/Nav";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { NlpReport, SpellResult } from "@/lib/types";

const EXAMPLES = ["inceptoin", "the godfahter", "shawshenk redemtion", "pulp ficton", "forest gump", "the dark nigth"];

const Panel = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <section className={cn("glass spec rounded-[32px] p-6 sm:p-8", className)}>{children}</section>
);

const SYSTEMS: [string, string][] = [
  ["none", "No correction"],
  ["difflib", "difflib (library baseline)"],
  ["edit", "Edit distance only (from scratch)"],
  ["unigram", "Noisy channel + unigram"],
  ["bigram", "Noisy channel + bigram + Viterbi"],
];

function Lab() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<SpellResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (q: string) => {
    if (!q.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.nlpSpell(q.trim()));
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? "This site is private. Open the home page and enter the access code first." : e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel>
      <p className="text-[11px] uppercase tracking-[0.2em] text-white/45">Try it</p>
      <h2 className="mt-2 font-display text-[2rem] leading-none">Type a movie title, mistakes included</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(text);
        }}
        className="glass mt-5 flex items-center gap-2 rounded-full p-1.5 pl-5 focus-within:border-white/50"
      >
        <Search className="h-4 w-4 shrink-0 text-white/45" aria-hidden />
        <label htmlFor="nlp-q" className="sr-only">Movie title with typos</label>
        <input
          id="nlp-q"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={120}
          placeholder="e.g. the godfahter"
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent py-2.5 text-[16px] text-white placeholder:text-white/35 focus:outline-none"
        />
        <button type="submit" disabled={!text.trim() || busy} className="press flex h-11 items-center gap-2 rounded-full bg-white px-5 text-[14px] font-medium text-black disabled:bg-white/15 disabled:text-white/40">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Correct"}
        </button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => {
              setText(ex);
              void run(ex);
            }}
            className="glass-pill press rounded-full px-3.5 py-1.5 text-[12.5px] text-white/75 hover:text-white"
          >
            {ex}
          </button>
        ))}
      </div>

      {error && <p className="mt-5 text-[13.5px] text-white/70" role="alert">{error}</p>}

      {result && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="mt-7">
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-white/45">Corrected</p>
          <p className="mt-1.5 font-display text-[2.4rem] leading-none sm:text-[3rem]">{result.corrected || "(nothing to correct)"}</p>
          <p className="mt-2 text-[13px] text-white/55">{result.changed ? "Changed from what you typed." : "Nothing needed fixing: every word is already a known word."}</p>
          {result.matches.length > 0 && (
            <p className="mt-3 text-[14px] text-white/80">
              Did you mean:{" "}
              {result.matches.map((m, i) => (
                <span key={m.movie_id}>
                  {i > 0 && ", "}
                  <strong className="font-semibold text-white">{m.title}</strong>
                  {m.year ? ` (${m.year})` : ""}
                </span>
              ))}
              ?
            </p>
          )}

          <h3 className="mt-7 font-display text-[1.5rem] leading-none">The candidate lattice</h3>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-white/50">
            Each typed word gets candidate words within 2 edits. The score is the channel log-probability (<span className="font-mono">distance × log 0.02</span>) plus the bigram log-probability of the
            word after the previous one; Viterbi keeps the best path. The path through the highlighted words is the answer.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {result.tokens.map((t, i) => (
              <div key={i} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p className="font-mono text-[11px] text-white/45">
                  typed: <span className="text-white/80">{t.input}</span> {t.known && <span className="text-white/35">(known word)</span>}
                </p>
                <ul className="mt-2 space-y-1">
                  {t.candidates.map((c) => (
                    <li key={c.word} className={cn("flex items-baseline justify-between gap-3 rounded-lg px-2 py-1 font-mono text-[12px]", c.on_best_path ? "bg-white text-black" : "text-white/60")}>
                      <span>{c.word}</span>
                      <span className={c.on_best_path ? "text-black/60" : "text-white/35"}>
                        d={c.distance} · {c.best_path_score.toFixed(1)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </Panel>
  );
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

function Report({ r }: { r: NlpReport }) {
  const p = r.perplexity;
  return (
    <div className="space-y-6">
      <Panel>
        <p className="text-[11px] uppercase tracking-[0.2em] text-white/45">Evaluation · language model</p>
        <h2 className="mt-2 font-display text-[2rem] leading-none">Why smoothing matters (perplexity)</h2>
        <p className="mt-3 max-w-2xl text-[13.5px] leading-relaxed text-white/55">
          {p.n_train.toLocaleString()} train / {p.n_valid.toLocaleString()} validation / {p.n_test.toLocaleString()} test titles. Lower perplexity is better. k was chosen on the validation titles only.
        </p>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[420px] text-left text-[13px]">
            <thead className="font-mono text-[11px] uppercase tracking-wider text-white/45">
              <tr><th className="py-2 pr-4">Model</th><th className="py-2 pr-4 text-right">Validation</th><th className="py-2 text-right">Test</th></tr>
            </thead>
            <tbody>
              {p.rows.map((row) => (
                <tr key={row.model} className={cn("border-t border-white/10", row.k === p.chosen_k && row.model.includes("add-k") && "bg-white/[0.06]")}>
                  <td className="py-2 pr-4">{row.model}</td>
                  <td className="py-2 pr-4 text-right font-mono">{row.valid === null ? "∞" : row.valid.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                  <td className="py-2 text-right font-mono">{row.test === null ? "∞" : row.test.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-[12.5px] leading-relaxed text-white/45">
          Without smoothing a single unseen word pair makes the perplexity infinite. The bigram model is not better than the unigram here: title word pairs are sparse, so most of its probability mass goes to smoothing.
        </p>
      </Panel>

      {r.correction.map((c) => (
        <Panel key={c.protocol}>
          <p className="text-[11px] uppercase tracking-[0.2em] text-white/45">Evaluation · correction accuracy</p>
          <h2 className="mt-2 font-display text-[2rem] leading-none">
            {c.protocol === "seen" ? "Titles that exist in the catalogue" : "Held-out titles the model has never seen"}
          </h2>
          <p className="mt-3 max-w-2xl text-[13.5px] leading-relaxed text-white/55">
            {c.protocol === "seen"
              ? "The app's real use: you type a title that is in MovieLens. Synthetic typos of 1 or 2 edits are injected into one word."
              : "Harder: the title's word pairs were removed from training, so the language model cannot have memorised them."}{" "}
            {c.results["1_edit"].items} test items per column.
          </p>
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-[13px]">
              <thead className="font-mono text-[11px] uppercase tracking-wider text-white/45">
                <tr><th className="py-2 pr-4">System</th><th className="py-2 pr-3 text-right">1 edit</th><th className="py-2 text-right">2 edits</th></tr>
              </thead>
              <tbody>
                {SYSTEMS.map(([key, label]) => {
                  const a = c.results["1_edit"][key] as { token_accuracy: number; title_accuracy: number };
                  const b = c.results["2_edit"][key] as { token_accuracy: number; title_accuracy: number };
                  const best = key === "bigram";
                  return (
                    <tr key={key} className={cn("border-t border-white/10", best && "bg-white/[0.06]")}>
                      <td className="py-2 pr-4">{label}</td>
                      <td className="py-2 pr-3 text-right font-mono">{pct(a.token_accuracy)}</td>
                      <td className="py-2 text-right font-mono">{pct(b.token_accuracy)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[12px] text-white/40">Token accuracy: the mistyped word is restored.</p>
          {c.false_correction_rate && (
            <p className="mt-3 text-[12.5px] leading-relaxed text-white/50">
              Cost of over-correcting: on {c.false_correction_rate.n_clean_titles} clean held-out titles, difflib wrongly changed {pct(c.false_correction_rate.difflib)} and the bigram model {pct(c.false_correction_rate.bigram)}, because words
              missing from training look like typos.
            </p>
          )}
        </Panel>
      ))}
      <p className="text-[12px] leading-relaxed text-white/40">
        Typos are synthetic (random edits), only non-word errors are handled, and Good-Turing smoothing was not implemented. Generated {r.generated_at}.
      </p>
    </div>
  );
}

export default function NlpPage() {
  const [report, setReport] = useState<NlpReport | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .nlpReport()
      .then((r) => !cancelled && setReport(r))
      .catch((e) => !cancelled && setNote(e instanceof ApiError && e.status === 401 ? "Enter the access code on the home page to see the evaluation." : "The evaluation report is not available."));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <Backdrop />
      <main className="mx-auto max-w-5xl px-4 pb-24 pt-6 sm:px-6 sm:pt-8">
        <header className="flex items-center justify-between">
          <Link href="/" className="glass-pill press flex items-center gap-2 rounded-full px-4 py-2.5 text-[13px]"><ArrowLeft className="h-4 w-4" /> Back to chat</Link>
          <Logo />
        </header>

        <div className="mb-10 mt-14">
          <p className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-white/45"><FlaskConical className="h-3.5 w-3.5" aria-hidden /> NLP Lab · Natural Language Processing project</p>
          <h1 className="mt-3 font-display text-[clamp(2.6rem,7vw,4.6rem)] leading-[0.96] tracking-[-0.02em]">
            Spelling correction, <em className="text-white/60">from scratch</em>
          </h1>
          <p className="mt-4 max-w-2xl text-[16px] leading-relaxed text-white/55">
            A noisy-channel model with Damerau-Levenshtein edit distance, a BK-tree for candidate search, a smoothed bigram language model and Viterbi decoding. All written from scratch and compared with a library baseline.
          </p>
          <ol className="mt-6 grid gap-2.5 text-[13px] text-white/60 sm:grid-cols-4">
            {[
              ["1 · Tokenize", "Lowercase, strip accents and punctuation."],
              ["2 · Candidates", "BK-tree finds words within 2 edits."],
              ["3 · Score", "log P(typed | word) + log P(word | previous word)."],
              ["4 · Viterbi", "Best word sequence over the whole lattice."],
            ].map(([t, d]) => (
              <li key={t} className="rounded-2xl border border-white/10 bg-white/[0.03] p-3.5">
                <p className="font-medium text-white">{t}</p>
                <p className="mt-1 leading-snug">{d}</p>
              </li>
            ))}
          </ol>
        </div>

        <div className="space-y-6">
          <Lab />
          {report ? <Report r={report} /> : note ? <p className="text-[13.5px] text-white/50">{note}</p> : <div className="skeleton h-64 rounded-[32px]" aria-hidden />}
        </div>
      </main>
    </>
  );
}
