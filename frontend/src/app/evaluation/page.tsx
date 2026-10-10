"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, FileWarning, Info, RefreshCw } from "lucide-react";
import { AppDock } from "@/components/AppDock";
import { Backdrop } from "@/components/Backdrop";
import CountUp from "@/components/bits/CountUp";
import { Logo } from "@/components/Nav";
import { ProjectDialog } from "@/components/ProjectDialog";
import { openProject } from "@/lib/project";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { EvaluationReport } from "@/lib/types";

type MethodKey = keyof EvaluationReport["metrics"];

const LABEL: Record<string, string> = {
  random: "Random",
  popular: "Popularity",
  content: "Content-based",
  collaborative: "Collaborative",
  hybrid: "Hybrid",
};
const BLURB: Record<string, string> = {
  random: "Sanity floor: random unseen movies.",
  popular: "Bayesian-weighted rating. Same list for everyone.",
  content: "TF-IDF + cosine over genres, tags and title words.",
  collaborative: "Item-item collaborative filtering on likes.",
  hybrid: "Weighted blend of the three, weights tuned on validation data.",
};

const Panel = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <section className={cn("glass spec rounded-[32px] p-6 sm:p-8", className)}>{children}</section>
);

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="glass rounded-3xl p-5">
      <p className="text-[11px] uppercase tracking-[0.18em] text-white/45">{label}</p>
      <p className="mt-2 font-display text-[2.4rem] leading-none">
        <CountUp to={value} separator="," duration={1.8} />
      </p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-6" aria-hidden>
      <div className="grid gap-4 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-28 rounded-3xl" />)}</div>
      <div className="skeleton h-80 rounded-[32px]" />
      <div className="skeleton h-64 rounded-[32px]" />
    </div>
  );
}

function Report({ r }: { r: EvaluationReport }) {
  const order = (Object.keys(r.metrics) as MethodKey[]).sort((a, b) => r.metrics[b].ndcg - r.metrics[a].ndcg);
  const top = Math.max(...order.map((k) => r.metrics[k].ndcg));
  const k = r.protocol.k;
  const cmp = r.paired_comparisons ?? {};

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Users evaluated" value={r.n_users_evaluated} />
        <Stat label="Relevant held-out" value={r.n_relevant_test_interactions} />
        <Stat label="Training ratings" value={r.n_train_interactions} />
        <Stat label="Candidate movies" value={r.n_candidate_items} />
      </div>

      <Panel>
        <h2 className="font-display text-[2rem] leading-none">NDCG@{k} by method</h2>
        <p className="mt-2 text-[13px] text-white/50">Higher is better. Rewards putting movies the user later rated ≥ 4 near the top of the list.</p>
        <ul className="mt-7 space-y-5">
          {order.map((m, i) => (
            <li key={m}>
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <span className="text-[15px]">{LABEL[m]}</span>
                  <span className="ml-3 hidden text-[12px] text-white/35 sm:inline">{BLURB[m]}</span>
                </div>
                <span className="font-mono text-[14px]">{r.metrics[m].ndcg.toFixed(4)}</span>
              </div>
              <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-white/10" role="img" aria-label={`${LABEL[m]} NDCG ${r.metrics[m].ndcg.toFixed(4)}`}>
                <motion.div
                  className={cn("h-full rounded-full", i === 0 ? "bg-white" : "bg-white/55")}
                  initial={{ width: 0 }}
                  animate={{ width: `${(r.metrics[m].ndcg / top) * 100}%` }}
                  transition={{ duration: 1.1, delay: 0.1 + i * 0.1, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel className="overflow-x-auto">
        <h2 className="font-display text-[2rem] leading-none">All metrics @{k}</h2>
        <table className="mt-5 w-full min-w-[560px] text-left text-[14px]">
          <caption className="sr-only">Ranking metrics per method</caption>
          <thead className="text-[11px] uppercase tracking-[0.14em] text-white/45">
            <tr>{["Method", `Precision`, `Recall`, `NDCG`, `Hit rate`, "Coverage"].map((h) => <th key={h} scope="col" className="pb-3 pr-4 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody className="font-mono text-[13px]">
            {order.map((m) => (
              <tr key={m} className="border-t border-white/10">
                <th scope="row" className="py-3 pr-4 font-sans text-[14px] font-normal">{LABEL[m]}</th>
                <td className="pr-4">{r.metrics[m].precision.toFixed(4)}</td>
                <td className="pr-4">{r.metrics[m].recall.toFixed(4)}</td>
                <td className="pr-4">{r.metrics[m].ndcg.toFixed(4)}</td>
                <td className="pr-4">{r.metrics[m].hit_rate.toFixed(3)}</td>
                <td>{(r.metrics[m].catalogue_coverage * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {Object.keys(cmp).length > 0 && (
        <Panel className="overflow-x-auto">
          <h2 className="font-display text-[2rem] leading-none">Are the gaps real?</h2>
          <p className="mt-2 text-[13px] text-white/50">Paired per-user NDCG differences with a 95% confidence interval. If the interval crosses zero, we can&apos;t claim a difference.</p>
          <table className="mt-5 w-full min-w-[520px] text-left text-[14px]">
            <thead className="text-[11px] uppercase tracking-[0.14em] text-white/45">
              <tr>{["Comparison", "Mean difference", "95% CI", "Significant"].map((h) => <th key={h} scope="col" className="pb-3 pr-4 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody className="font-mono text-[13px]">
              {Object.entries(cmp).map(([name, v]) => (
                <tr key={name} className="border-t border-white/10">
                  <th scope="row" className="py-3 pr-4 font-sans text-[14px] font-normal capitalize">{name.replace("_minus_", " − ").replace(/_/g, " ")}</th>
                  <td className="pr-4">{v.mean_ndcg_difference >= 0 ? "+" : ""}{v.mean_ndcg_difference.toFixed(4)}</td>
                  <td className="pr-4">[{v.ci95_low.toFixed(4)}, {v.ci95_high.toFixed(4)}]</td>
                  <td className={v.significant_at_95 ? "text-white" : "text-white/40"}>{v.significant_at_95 ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel>
          <h2 className="font-display text-[1.8rem] leading-none">Protocol</h2>
          <dl className="mt-5 space-y-3 text-[13.5px]">
            {[
              ["Dataset", r.dataset],
              ["Split", String(r.protocol.split)],
              ["Relevant item", String(r.protocol.relevance)],
              ["Candidate rule", `movies with ≥ ${r.protocol.min_train_ratings_per_item} training ratings the user hasn't rated`],
              ["Tuning", "CF settings and hybrid weights chosen on a validation slice of the training data, never on test"],
            ].map(([dt, dd]) => (
              <div key={dt} className="grid grid-cols-[110px_1fr] gap-3"><dt className="text-white/40">{dt}</dt><dd className="text-white/85">{dd}</dd></div>
            ))}
          </dl>
          <p className="mt-5 font-mono text-[11px] leading-relaxed text-white/35">
            similarity={String(r.chosen_config.knn.similarity)} · k={String(r.chosen_config.knn.k)} · shrinkage={String(r.chosen_config.knn.shrinkage)}
            {r.chosen_config.hybrid_weights && <> · weights {Object.entries(r.chosen_config.hybrid_weights).map(([a, b]) => `${a} ${b}`).join(", ")}</>}
          </p>
        </Panel>
        <Panel>
          <h2 className="font-display text-[1.8rem] leading-none">Limitations</h2>
          <ul className="mt-5 list-disc space-y-2.5 pl-5 text-[13.5px] leading-relaxed text-white/70 marker:text-white/30">
            <li>Small dataset (610 users): intervals are wide, so small gaps may not be meaningful.</li>
            <li>A held-out rating ≥ 4 is a proxy; movies a user would have loved but never rated count as misses.</li>
            <li>Popularity is unusually strong on MovieLens because people mostly rate already-popular films.</li>
            <li>Dislikes and cold-start users are not measured offline; both are covered by functional tests instead.</li>
            <li>Content features are only genres, tags and titles, so content-based alone is weak here.</li>
          </ul>
        </Panel>
      </div>
      <p className="px-2 text-center font-mono text-[11px] text-white/30">
        generated {new Date(r.generated_at).toLocaleString()}{r.runtime_seconds ? ` · ran in ${r.runtime_seconds}s` : ""} · reproduce with python -m scripts.run_evaluation
      </p>
    </div>
  );
}

export default function EvaluationPage() {
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .evaluation()
      .then((r) => !cancelled && setReport(r))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? { status: e.status, message: e.message } : { status: 0, message: "Unexpected error." }))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = () => {
    setLoading(true);
    setError(null);
    setAttempt((n) => n + 1);
  };

  return (
    <>
      <Backdrop />
      <AppDock current="evaluation" />
      <ProjectDialog />
      <main className="mx-auto max-w-5xl px-4 pb-24 pt-6 sm:px-6 sm:pt-8">
        <header className="flex items-center justify-between">
          <Link href="/" className="glass-pill press flex items-center gap-2 rounded-full px-4 py-2.5 text-[13px]"><ArrowLeft className="h-4 w-4" /> Back to chat</Link>
          <div className="flex items-center gap-4">
            <Logo />
            <button type="button" onClick={() => openProject("about")} className="glass-pill press flex h-9 items-center gap-2 rounded-full px-3.5 text-[12.5px] text-white/85 hover:text-white">
              <Info className="h-[17px] w-[17px]" aria-hidden /> Project
            </button>
          </div>
        </header>
        <div className="mt-14 mb-10">
          <p className="text-[11px] uppercase tracking-[0.2em] text-white/45">Offline evaluation</p>
          <h1 className="mt-3 font-display text-[clamp(2.6rem,7vw,4.6rem)] leading-[0.96] tracking-[-0.02em]">Does it actually <em className="text-white/60">work?</em></h1>
          <p className="mt-4 max-w-2xl text-[16px] leading-relaxed text-white/55">Every number on this page is read live from the evaluation run on MovieLens. Nothing is hard-coded.</p>
        </div>

        {loading && <Skeleton />}
        {!loading && error && (
          <div className="glass glass-strong mx-auto max-w-xl rounded-[32px] p-8 text-center" role="alert">
            <FileWarning className="mx-auto h-8 w-8 text-white/70" aria-hidden />
            <h2 className="mt-4 font-display text-[1.9rem] leading-none">{error.status === 404 ? "No evaluation yet" : error.status === 401 ? "Open the home page first" : "Couldn't load results"}</h2>
            <p className="mt-3 text-[14px] text-white/55">{error.status === 401 ? "This site is private. Enter the access code on the home page, then come back here." : error.message}</p>
            {error.status === 404 && <p className="mt-4 rounded-2xl bg-black/40 p-3 font-mono text-[12px] text-white/70">cd backend && .venv/bin/python -m scripts.run_evaluation</p>}
            <button type="button" onClick={retry} className="press mx-auto mt-6 flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-[13px] font-medium text-black"><RefreshCw className="h-4 w-4" /> Retry</button>
          </div>
        )}
        {!loading && report && <Report r={report} />}
      </main>
    </>
  );
}
