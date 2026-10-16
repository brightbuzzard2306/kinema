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
type Acc = { token_accuracy: number; title_accuracy: number };
type Correction = NlpReport["correction"][number];
const acc = (c: Correction, edits: "1_edit" | "2_edit", key: string) => c.results[edits][key] as Acc;

/** 95% Wilson score interval for a proportion measured on n items (honest even at 0% or 100%). */
function wilson(p: number, n: number): [number, number] {
  const z = 1.96;
  const d = 1 + (z * z) / n;
  const centre = (p + (z * z) / (2 * n)) / d;
  const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, centre - half), Math.min(1, centre + half)];
}

const fmtPpl = (v: number | null) => (v === null ? "∞" : v.toLocaleString(undefined, { maximumFractionDigits: 1 }));

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="glass rounded-3xl p-5">
      <p className="text-[11px] uppercase tracking-[0.18em] text-white/45">{label}</p>
      <p className="mt-2 font-display text-[2.4rem] leading-none">{value}</p>
      <p className="mt-2 text-[12px] leading-snug text-white/50">{sub}</p>
    </div>
  );
}

function AccCell({ p, n, best }: { p: number; n: number; best: boolean }) {
  const [lo, hi] = wilson(p, n);
  return (
    <td className="py-2 pl-3 text-right align-top">
      <span className={cn("font-mono", best ? "font-semibold text-white" : "text-white/80")}>{pct(p)}</span>
      <span className="block font-mono text-[10.5px] text-white/35">{(lo * 100).toFixed(0)}–{(hi * 100).toFixed(0)}%</span>
    </td>
  );
}

function CorrectionTable({ c }: { c: Correction }) {
  const n = c.results["1_edit"].items;
  const seen = c.protocol === "seen"; // only one word is damaged and it is always in the title, so word accuracy = title accuracy
  const real = SYSTEMS.filter(([k]) => k !== "none");
  const best = (edits: "1_edit" | "2_edit", field: keyof Acc) => Math.max(...real.map(([k]) => acc(c, edits, k)[field]));
  const cols: { edits: "1_edit" | "2_edit"; field: keyof Acc; head: string }[] = seen
    ? [{ edits: "1_edit", field: "token_accuracy", head: "1 edit" }, { edits: "2_edit", field: "token_accuracy", head: "2 edits" }]
    : [
        { edits: "1_edit", field: "token_accuracy", head: "1 edit · word" },
        { edits: "1_edit", field: "title_accuracy", head: "1 edit · title" },
        { edits: "2_edit", field: "token_accuracy", head: "2 edits · word" },
        { edits: "2_edit", field: "title_accuracy", head: "2 edits · title" },
      ];
  return (
    <div className="mt-5 overflow-x-auto">
      <table className="w-full min-w-[520px] text-left text-[13px]">
        <thead className="font-mono text-[11px] uppercase tracking-wider text-white/45">
          <tr>
            <th className="py-2 pr-4">System</th>
            {cols.map((col) => <th key={col.head} className="py-2 pl-3 text-right">{col.head}</th>)}
          </tr>
        </thead>
        <tbody>
          {SYSTEMS.map(([key, label]) => (
            <tr key={key} className={cn("border-t border-white/10", key === "bigram" && "bg-white/[0.06]")}>
              <td className="py-2 pr-4 align-top">{label}</td>
              {cols.map((col) => {
                const v = acc(c, col.edits, key)[col.field];
                return <AccCell key={col.head} p={v} n={n} best={key !== "none" && v === best(col.edits, col.field)} />;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-[12px] leading-relaxed text-white/40">
        {n} test items per column. Bold = best real method. Small grey range = 95% confidence interval (Wilson), i.e. how much the number could move with different test typos.
      </p>
    </div>
  );
}

function Report({ r }: { r: NlpReport }) {
  const p = r.perplexity;
  const seen = r.correction.find((c) => c.protocol === "seen");
  const held = r.correction.find((c) => c.protocol === "held-out");
  const fc = held?.false_correction_rate;
  return (
    <div className="space-y-6">
      {seen && (
        <div>
          <p className="mb-3 text-[11px] uppercase tracking-[0.2em] text-white/45">The metrics at a glance</p>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Perplexity (test)" value={fmtPpl(p.test_at_chosen_k)} sub={`bigram, add-k smoothing (k = ${p.chosen_k}). Without smoothing: ∞. Lower is better.`} />
            <Stat label="1-edit typos fixed" value={pct(acc(seen, "1_edit", "bigram").token_accuracy)} sub={`bigram + Viterbi, titles in the catalogue. Library baseline difflib: ${pct(acc(seen, "1_edit", "difflib").token_accuracy)}.`} />
            <Stat label="2-edit typos fixed" value={pct(acc(seen, "2_edit", "bigram").token_accuracy)} sub={`same setting. difflib: ${pct(acc(seen, "2_edit", "difflib").token_accuracy)}.`} />
            {fc && <Stat label="Clean titles wrongly changed" value={pct(fc.bigram)} sub={`held-out titles, bigram + Viterbi. difflib: ${pct(fc.difflib)}. Lower is better.`} />}
          </div>
        </div>
      )}

      <Panel>
        <p className="text-[11px] uppercase tracking-[0.2em] text-white/45">What each metric means</p>
        <h2 className="mt-2 font-display text-[2rem] leading-none">The four measurements</h2>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2">
          {[
            ["Perplexity", "How surprised the language model is by titles it has never seen: exp(−average log P(word | previous word)). Lower is better. One unseen word pair with probability 0 makes it infinite, which is why smoothing is needed."],
            ["Word accuracy", "Out of the test typos, the share where the mistyped word was restored to the right word. A typo is 1 or 2 random edits (insert, delete, substitute, swap) in one word."],
            ["Title accuracy", "The share where the whole title came out exactly right. Needs every word to be right, so it is never above word accuracy."],
            ["Wrongly changed", "How often a system alters a title that was already correct. Words missing from training look like typos, so every system over-corrects a little. Lower is better."],
          ].map(([t, d]) => (
            <div key={t} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <dt className="font-display text-[1.35rem] leading-none">{t}</dt>
              <dd className="mt-2 text-[12.5px] leading-relaxed text-white/55">{d}</dd>
            </div>
          ))}
        </dl>
      </Panel>

      <Panel>
        <p className="text-[11px] uppercase tracking-[0.2em] text-white/45">Evaluation · language model</p>
        <h2 className="mt-2 font-display text-[2rem] leading-none">Why smoothing matters (perplexity)</h2>
        <p className="mt-3 max-w-2xl text-[13.5px] leading-relaxed text-white/55">
          {p.n_train.toLocaleString()} train / {p.n_valid.toLocaleString()} validation / {p.n_test.toLocaleString()} test titles, vocabulary {p.vocab.toLocaleString()} words. Lower perplexity is better. k was chosen on the validation titles only, never on the test titles.
        </p>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[420px] text-left text-[13px]">
            <thead className="font-mono text-[11px] uppercase tracking-wider text-white/45">
              <tr><th className="py-2 pr-4">Model</th><th className="py-2 pr-4 text-right">Validation</th><th className="py-2 text-right">Test</th></tr>
            </thead>
            <tbody>
              {p.rows.map((row) => (
                <tr key={row.model} className={cn("border-t border-white/10", row.k === p.chosen_k && row.model.includes("add-k") && "bg-white/[0.06]")}>
                  <td className="py-2 pr-4">{row.model}{row.k === p.chosen_k && row.model.includes("add-k") ? <span className="ml-2 font-mono text-[10.5px] text-white/45">chosen</span> : null}</td>
                  <td className="py-2 pr-4 text-right font-mono">{fmtPpl(row.valid)}</td>
                  <td className="py-2 text-right font-mono">{fmtPpl(row.test)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-[12.5px] leading-relaxed text-white/45">
          Without smoothing a single unseen word pair makes the perplexity infinite. The bigram model is not better than the unigram here: title word pairs are sparse, so most of its probability mass goes to smoothing. Interpolating the two would fix that (not implemented).
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
              ? "The app's real use: you type a title that is in MovieLens, with a typo in one word. The language model has seen this title, so word accuracy equals title accuracy."
              : "Harder: the title's word pairs were removed from training, so the language model cannot have memorised them."}
          </p>
          <CorrectionTable c={c} />
          {c.false_correction_rate && (
            <div className="mt-6">
              <h3 className="font-display text-[1.5rem] leading-none">Cost of over-correcting</h3>
              <p className="mt-2 max-w-2xl text-[12.5px] leading-relaxed text-white/50">
                Share of {c.false_correction_rate.n_clean_titles} <em>correct</em> held-out titles that each system wrongly changed (words missing from training look like typos). Lower is better.
              </p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[360px] text-left text-[13px]">
                  <tbody>
                    {SYSTEMS.filter(([k]) => k !== "none").map(([key, label]) => {
                      const v = c.false_correction_rate![key];
                      const lowest = Math.min(...SYSTEMS.filter(([k]) => k !== "none").map(([k]) => c.false_correction_rate![k]));
                      return (
                        <tr key={key} className="border-t border-white/10">
                          <td className="py-2 pr-4">{label}</td>
                          <td className={cn("py-2 text-right font-mono", v === lowest ? "font-semibold text-white" : "text-white/80")}>{pct(v)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Panel>
      ))}

      <Panel>
        <p className="text-[11px] uppercase tracking-[0.2em] text-white/45">Reading the numbers honestly</p>
        <h2 className="mt-2 font-display text-[2rem] leading-none">What these results do and do not show</h2>
        <ul className="mt-4 space-y-2.5 text-[13.5px] leading-relaxed text-white/60">
          <li><span className="text-white">Real gain:</span> on titles that exist in the catalogue the bigram + Viterbi corrector clearly beats the library baseline (the confidence ranges do not overlap).</li>
          <li><span className="text-white">No clear gain on unseen titles:</span> there the bigram and unigram systems are within noise of each other, because the bigram model has not seen those word pairs.</li>
          <li><span className="text-white">Synthetic typos:</span> the mistakes are random edits, not typed by real people (who hit neighbouring keys). Real accuracy could differ.</li>
          <li><span className="text-white">Limits:</span> only non-word errors are handled (a typo that spells another real word, like &ldquo;forest&rdquo; for &ldquo;Forrest&rdquo;, is not detected), and Good-Turing smoothing was not implemented (add-k with k tuned on validation data).</li>
          <li><span className="text-white">Not learned:</span> the typo probability (0.02 per edit) is a chosen setting, not learned from data. The only trained part is the bigram model, estimated by counting word pairs in the {r.corpus.titles.toLocaleString()} titles.</li>
        </ul>
        <p className="mt-4 text-[12px] text-white/35">Generated {r.generated_at} by <span className="font-mono">python -m scripts.run_nlp_eval</span> (fixed random seeds).</p>
      </Panel>
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
