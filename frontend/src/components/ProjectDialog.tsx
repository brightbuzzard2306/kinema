"use client";

import Link from "next/link";
import * as Dialog from "@radix-ui/react-dialog";
import { motion, useReducedMotion } from "motion/react";
import { ArrowUpRight, Compass, GraduationCap, Users, X } from "lucide-react";
import BlurText from "./bits/BlurText";
import { MorphText } from "./MorphText";
import ShinyText from "./bits/ShinyText";
import SpotlightCard from "./bits/SpotlightCard";
import { useWorkspaceOptional } from "./WorkspaceProvider";
import { closeProject, setProjectTab, useProject, type ProjectTab } from "@/lib/project";
import { initials, PROJECT_INFO, TEAM, TEAM_IS_PLACEHOLDER, type TeamMember } from "@/lib/team";
import { restartTour } from "@/lib/tour";
import { cn } from "@/lib/utils";

const TABS: { key: ProjectTab; label: string }[] = [
  { key: "about", label: "About" },
  { key: "team", label: "Team" },
];

const ALGORITHMS = [
  ["Popular", "Bayesian-average rating. The same list for everyone: the cold-start baseline."],
  ["Content", "TF-IDF over genres, tags and titles finds look-alikes of what you liked."],
  ["People like you", "Item-item collaborative filtering: movies liked by the same people are similar."],
  ["Hybrid", "A weighted blend of all three, with weights tuned on held-out data."],
] as const;

/** Soft glass surface for the spotlight cards (the component's own default is a solid near-black). */
const CARD_SURFACE = { "--spotlight-card-surface": "rgba(255,255,255,0.035)", "--spotlight-card-shadow": "none" } as React.CSSProperties;

const pillBtn = "press glass-pill flex items-center gap-1.5 rounded-full px-4 py-2 text-[12.5px] text-white";

function AboutPanel() {
  const ws = useWorkspaceOptional();
  const d = ws?.health?.dataset;
  const stats = d && d.movies ? [`${d.movies.toLocaleString()} movies`, `${d.ratings.toLocaleString()} ratings`, d.users ? `${d.users.toLocaleString()} users` : null].filter(Boolean).join(" · ") : null;

  return (
    <div>
      <h2 className="font-display text-[2.2rem] leading-[1.02] sm:text-[2.7rem]">
        A conversational <em className="text-white/60">movie recommender</em>
      </h2>
      <p className="mt-4 max-w-2xl text-[14px] leading-relaxed text-white/60">
        Choosing a film is slow: search needs a title, and a chatbot alone can invent movies. Kinema ranks real MovieLens data with four recommendation
        algorithms; Claude only understands your sentence and words the reply.
      </p>

      <ul className="mt-6 grid gap-2.5 sm:grid-cols-2">
        {ALGORITHMS.map(([name, text]) => (
          <li key={name} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <p className="font-display text-[1.35rem] leading-none">{name}</p>
            <p className="mt-2 text-[12.5px] leading-snug text-white/55">{text}</p>
          </li>
        ))}
      </ul>

      {stats && <p className="mt-5 font-mono text-[11px] leading-relaxed text-white/45">MovieLens ml-latest-small · {stats}</p>}
      <p className="mt-2 max-w-2xl text-[11.5px] leading-relaxed text-white/40">
        Privacy: no accounts. Chats are kept on the server against a random ID stored in this browser, and when Claude is on your messages are sent to
        Anthropic&apos;s API to be understood.
      </p>

      <div className="mt-6 flex flex-wrap gap-2">
        <Link href="/evaluation" onClick={closeProject} className={pillBtn}>
          See the evaluation <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
        {ws && (
          <button
            type="button"
            onClick={() => {
              closeProject();
              restartTour();
            }}
            className={pillBtn}
          >
            <Compass className="h-3.5 w-3.5" aria-hidden /> Take the tour
          </button>
        )}
        <button type="button" onClick={() => setProjectTab("team")} className={pillBtn}>
          <Users className="h-3.5 w-3.5" aria-hidden /> Meet the team
        </button>
      </div>
    </div>
  );
}

function Avatar({ member }: { member: TeamMember }) {
  return (
    <span className="relative grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-full border border-white/25 bg-gradient-to-b from-white/20 to-white/[0.04] shadow-[inset_0_1px_0_rgba(255,255,255,0.25)]">
      {member.photo ? (
        // eslint-disable-next-line @next/next/no-img-element -- team photos are tiny static files; optimisation adds nothing here
        <img src={member.photo} alt={`Photo of ${member.name}`} className="h-full w-full object-cover grayscale" loading="lazy" />
      ) : (
        <span className="font-display text-[1.45rem] leading-none text-white/90" aria-hidden>
          {initials(member.name)}
        </span>
      )}
    </span>
  );
}

function MemberCard({ member }: { member: TeamMember }) {
  return (
    <SpotlightCard theme="dark" intensity={0.2} spotlightSize={280} borderGlow={0.7} className="!rounded-[26px] !p-5" style={CARD_SURFACE}>
      <div className="flex items-start gap-4">
        <Avatar member={member} />
        <div className="min-w-0">
          <p className="font-display text-[1.6rem] leading-[1.05]">{member.name}</p>
          <p className="mt-1 text-[13px] leading-snug text-white/60">{member.role}</p>
          {member.detail && <p className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.16em] text-white/40">{member.detail}</p>}
        </div>
      </div>
      {!!member.links?.length && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {member.links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              target="_blank"
              rel="noopener noreferrer"
              className="press inline-flex items-center gap-1 rounded-full border border-white/15 px-3 py-1 text-[11.5px] text-white/70 hover:border-white/40 hover:text-white"
            >
              {l.label} <ArrowUpRight className="h-3 w-3" aria-hidden />
            </a>
          ))}
        </div>
      )}
    </SpotlightCard>
  );
}

function TeamPanel() {
  const reduce = useReducedMotion();
  const rise = (i: number) => ({
    initial: reduce ? false : { opacity: 0, y: 18, filter: "blur(8px)" },
    animate: { opacity: 1, y: 0, filter: "blur(0px)" },
    transition: { duration: 0.6, delay: 0.12 + i * 0.08, ease: [0.22, 1, 0.36, 1] as const },
  });

  return (
    <div>
      <p className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-white/45">The people behind it</p>
      <h2 className="mt-2 font-display text-[2.4rem] leading-[1.02] sm:text-[3rem]">
        <BlurText text="Meet the team" delay={110} animateBy="words" direction="top" />
      </h2>
      <p className="mt-3 text-[13.5px] leading-relaxed text-white/55">
        {PROJECT_INFO.course} · {PROJECT_INFO.college}
        {PROJECT_INFO.session ? ` · ${PROJECT_INFO.session}` : ""}
      </p>

      <ul className={cn("mt-6 grid gap-3", TEAM.length > 1 && "sm:grid-cols-2")}>
        {TEAM.map((m, i) => (
          <motion.li key={`${m.name}-${i}`} {...rise(i)}>
            <MemberCard member={m} />
          </motion.li>
        ))}
      </ul>

      <motion.div {...rise(TEAM.length)} className="mt-3">
        <SpotlightCard theme="dark" intensity={0.16} spotlightSize={320} borderGlow={0.6} className="!rounded-[26px] !p-5" style={CARD_SURFACE}>
          <div className="flex items-center gap-4">
            {PROJECT_INFO.guidePhoto ? (
              <Avatar member={{ name: PROJECT_INFO.guide, role: "", photo: PROJECT_INFO.guidePhoto }} />
            ) : (
              <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full border border-white/20 bg-white/[0.06]">
                <GraduationCap className="h-5 w-5 text-white/80" aria-hidden />
              </span>
            )}
            <div className="min-w-0">
              <p className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-white/45">Project guide</p>
              <p className="mt-1 font-display text-[1.6rem] leading-[1.05]">
                <ShinyText text={PROJECT_INFO.guide} color="rgba(245,245,247,0.78)" shineColor="#ffffff" speed={4} delay={1} />
              </p>
            </div>
          </div>
        </SpotlightCard>
      </motion.div>

      {process.env.NODE_ENV !== "production" && TEAM_IS_PLACEHOLDER && (
        <p className="mt-4 rounded-2xl border border-dashed border-white/20 p-3 font-mono text-[11px] leading-relaxed text-white/45">
          Placeholder details (this note shows in development only). Fill them in at frontend/src/lib/team.ts: the file header explains both ways.
        </p>
      )}
    </div>
  );
}

/** One dialog for everything "about the project": an About tab and a Team tab. Open it with `openProject("about" | "team")`. */
export function ProjectDialog() {
  const { open, tab } = useProject();
  const reduce = useReducedMotion();

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    setProjectTab(tab === "about" ? "team" : "about");
  };

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && closeProject()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/65 backdrop-blur-md data-[state=open]:animate-[fade-in_0.3s_ease-out]" />
        <Dialog.Content
          aria-describedby="project-desc"
          className="glass glass-strong thin-scrollbar fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[min(94vw,860px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto overscroll-contain rounded-[34px] p-5 outline-none sm:p-8 data-[state=open]:animate-[sheet-in_0.45s_var(--ease-out)]"
        >
          <Dialog.Title className="sr-only">{tab === "about" ? "About this project" : "Meet the team"}</Dialog.Title>
          <Dialog.Description id="project-desc" className="sr-only">
            Details about the Kinema recommendation system mini project and the team that built it.
          </Dialog.Description>

          <div className="flex items-center justify-between gap-4">
            <p className="flex items-center gap-2.5" aria-hidden>
              <span className="relative grid h-2 w-2 place-items-center">
                <span className="absolute inset-0 rounded-full bg-white" />
                {!reduce && <span className="absolute inset-0 rounded-full bg-white" style={{ animation: "pulse-ring 2.6s ease-out infinite" }} />}
              </span>
              <MorphText text="RS MINI PROJECT" width={15} intro className="text-[11px]" />
            </p>
            <Dialog.Close className="glass-pill press grid h-9 w-9 shrink-0 place-items-center rounded-full" aria-label="Close">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          <div role="tablist" aria-label="Project sections" onKeyDown={onKeyDown} className="glass-pill relative mt-5 flex w-fit gap-1 rounded-full p-1">
            {TABS.map((t) => {
              const active = tab === t.key;
              return (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  id={`project-tab-${t.key}`}
                  aria-selected={active}
                  aria-controls={`project-panel-${t.key}`}
                  tabIndex={active ? 0 : -1}
                  onClick={() => setProjectTab(t.key)}
                  className={cn("relative rounded-full px-5 py-1.5 text-[13px] transition-colors", active ? "text-black" : "text-white/70 hover:text-white")}
                >
                  {active && (
                    <motion.span layoutId="project-tab-pill" className="absolute inset-0 rounded-full bg-white" transition={{ type: "spring", stiffness: 420, damping: 34 }} />
                  )}
                  <span className="relative">{t.label}</span>
                </button>
              );
            })}
          </div>

          <motion.div
            key={tab}
            role="tabpanel"
            id={`project-panel-${tab}`}
            aria-labelledby={`project-tab-${tab}`}
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="mt-7"
          >
            {tab === "about" ? <AboutPanel /> : <TeamPanel />}
          </motion.div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
