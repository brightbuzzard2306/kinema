"use client";

import Link from "next/link";
import * as Popover from "@radix-ui/react-popover";
import { BarChart3, Columns3, Info, Plus, SlidersHorizontal } from "lucide-react";
import { Logo } from "./Logo";
import { useWorkspace } from "./WorkspaceProvider";
import { BRAND } from "@/lib/brand";
import { openProject, useProject } from "@/lib/project";
import { cn } from "@/lib/utils";

function ModeBadge() {
  const { llm, health } = useWorkspace();
  const claude = llm.mode === "claude";
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={`Language mode: ${claude ? "Claude" : "offline parser"}. Open details`}
          className="glass-pill press flex h-9 items-center gap-2 rounded-full px-3 text-[12.5px] text-white/85"
        >
          <span className="relative grid h-2 w-2 place-items-center">
            <span className={cn("absolute inset-0 rounded-full", claude ? "bg-white" : "border border-white/70")} />
            {claude && llm.verified && <span className="absolute inset-0 rounded-full bg-white" style={{ animation: "pulse-ring 2.4s ease-out infinite" }} />}
          </span>
          <span className="hidden sm:inline">{claude ? (llm.verified ? "Claude" : "Checking Claude…") : "Offline mode"}</span>
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          sideOffset={10}
          align="end"
          className="glass glass-strong z-50 w-[280px] rounded-3xl p-4 text-[13px] leading-relaxed text-white/80 data-[state=open]:animate-[pop-in_0.25s_var(--ease-out)]"
        >
          <p className="font-medium text-white">{claude ? "Claude is interpreting your messages" : "Running without Claude"}</p>
          <p className="mt-1.5 text-white/60">
            {claude
              ? llm.verified
                ? "Claude reads your request and words the reply. The movies themselves always come from the MovieLens recommender."
                : "A key is configured. Sending one test message to confirm Claude responds."
              : (llm.reason ?? "Claude is unavailable.") + " A rule-based parser handles your requests instead, and recommendations work exactly the same."}
          </p>
          <p className="mt-3 font-mono text-[11px] text-white/40">
            {health?.llm.model ? `model: ${health.llm.model}` : "set ANTHROPIC_API_KEY in .env to enable Claude"}
          </p>
          <Popover.Arrow className="fill-white/20" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export { Logo };

/** One navbar action: icon always, label from `lg` up, a highlighted state while its panel is open. */
function NavAction({
  icon: Icon,
  label,
  onClick,
  href,
  active,
  badge,
  className,
}: {
  icon: typeof Plus;
  label: string;
  onClick?: () => void;
  href?: string;
  active?: boolean;
  badge?: number;
  className?: string;
}) {
  const cls = cn(
    "glass-pill press relative flex h-9 items-center gap-2 rounded-full px-3 text-[12.5px] text-white/85 transition-colors hover:text-white",
    active && "border-white/50 bg-white/[0.16] text-white",
    className,
  );
  const inner = (
    <>
      <Icon className="h-[17px] w-[17px] shrink-0" strokeWidth={1.9} aria-hidden />
      <span className="hidden lg:inline">{label}</span>
      {!!badge && badge > 0 && (
        <span className="grid h-[18px] min-w-[18px] place-items-center rounded-full bg-white px-1 font-mono text-[10px] font-semibold text-black">{badge}</span>
      )}
    </>
  );
  return href ? (
    <Link href={href} aria-label={label} title={label} className={cls}>
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={onClick} aria-label={label} title={label} aria-pressed={active ?? undefined} className={cls}>
      {inner}
    </button>
  );
}

export function Nav({ compact = false }: { compact?: boolean }) {
  const { profile, setProfileOpen, profileOpen, setCompareOpen, compareOpen, newChat, messages, busy } = useWorkspace();
  const project = useProject();
  const prefs = profile ? profile.genres.length + profile.excluded_genres.length + profile.liked_ids.length + profile.disliked_ids.length : 0;

  return (
    <header className="pointer-events-none fixed inset-x-0 top-0 z-40 flex justify-center px-3 pt-3 sm:px-6 sm:pt-5">
      <nav aria-label="Primary" className="glass pointer-events-auto flex w-full max-w-6xl items-center justify-between gap-3 rounded-full py-2 pl-5 pr-2">
        <div className="flex min-w-0 items-center">
          <Link href="/" aria-label={`${BRAND.name} home`} className="shrink-0 rounded-full">
            <Logo />
          </Link>
        </div>
        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          {!compact && <NavAction icon={Columns3} label="Compare" active={compareOpen} onClick={() => setCompareOpen(true)} className="hidden sm:flex" />}
          {!compact && <NavAction icon={SlidersHorizontal} label="Taste" active={profileOpen} badge={prefs} onClick={() => setProfileOpen(true)} />}
          <NavAction icon={BarChart3} label="Evaluation" href="/evaluation" className="hidden sm:flex" />
          <NavAction icon={Info} label="Project" active={project.open} onClick={() => openProject("about")} />
          {!compact && <ModeBadge />}
          {!compact && messages.length > 0 && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void newChat(true)}
              aria-label="Start a new conversation"
              title="New chat"
              className="press grid h-9 w-9 place-items-center rounded-full bg-white text-black disabled:opacity-40"
            >
              <Plus className="h-[18px] w-[18px]" strokeWidth={2.4} />
            </button>
          )}
        </div>
      </nav>
    </header>
  );
}
