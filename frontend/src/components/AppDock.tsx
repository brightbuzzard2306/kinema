"use client";

import { useRouter } from "next/navigation";
import { BarChart3, Columns3, MessageSquare, Plus, SlidersHorizontal } from "lucide-react";
import Dock, { type DockItemData } from "./bits/Dock";
import { useWorkspaceOptional } from "./WorkspaceProvider";

/** Monochrome override of the dock's default (purple-tinted) theme tokens. */
const MONO_TOKENS = {
  "--dock-panel": "rgba(255, 255, 255, 0.06)",
  "--dock-panel-edge": "rgba(255, 255, 255, 0.16)",
  "--dock-panel-highlight": "rgba(255, 255, 255, 0.2)",
  "--dock-tile": "linear-gradient(180deg, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0.06) 100%)",
  "--dock-tile-edge": "rgba(255, 255, 255, 0.2)",
  "--dock-tile-highlight": "rgba(255, 255, 255, 0.28)",
  "--dock-ink": "#f5f5f7",
  "--dock-label": "rgba(18, 18, 20, 0.92)",
  "--dock-label-ink": "#f5f5f7",
  "--dock-dot": "#ffffff",
  "--dock-separator": "rgba(255, 255, 255, 0.16)",
} as React.CSSProperties;

const icon = (Icon: typeof Plus) => <Icon className="h-[22px] w-[22px]" strokeWidth={1.75} aria-hidden />;

/**
 * macOS-style magnifying dock (React Bits "Dock") for wide screens. On narrower screens the top bar carries the same actions.
 * It is positioned inside a fixed, click-through layer so only the dock itself receives pointer events.
 */
export function AppDock({ current }: { current: "chat" | "evaluation" }) {
  const router = useRouter();
  const ws = useWorkspaceOptional();

  const items: DockItemData[] = [
    ws && current === "chat"
      ? {
          label: "New chat",
          icon: icon(Plus),
          onClick: () => {
            void ws.newChat(true);
            window.scrollTo({ top: 0, behavior: "smooth" });
          },
        }
      : { label: "Chat", icon: icon(MessageSquare), active: current === "chat", onClick: () => router.push("/") },
    ...(ws ? [{ label: "Taste profile", icon: icon(SlidersHorizontal), onClick: () => ws.setProfileOpen(true) }] : []),
    ...(ws ? [{ label: "Compare strategies", icon: icon(Columns3), onClick: () => ws.setCompareOpen(true) }] : []),
    { separator: true },
    { label: "Evaluation", icon: icon(BarChart3), active: current === "evaluation", onClick: () => router.push("/evaluation") },
  ];

  return (
    <div className="pointer-events-none fixed inset-0 z-30 hidden min-[1200px]:block">
      <Dock
        items={items}
        position="left"
        theme="dark"
        baseItemSize={46}
        magnification={64}
        panelHeight={58}
        distance={150}
        gap={10}
        showBadges={false}
        accentColor="#ffffff"
        className="pointer-events-auto"
        style={MONO_TOKENS}
      />
    </div>
  );
}
