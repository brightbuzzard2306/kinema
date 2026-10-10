"use client";

import { useEffect, useRef, useState } from "react";
import { animate, motion, useAnimationFrame, useMotionValue, useReducedMotion, useTransform, type MotionValue } from "motion/react";
import { useWorkspaceOptional } from "./WorkspaceProvider";
import { BRAND } from "@/lib/brand";
import { cn } from "@/lib/utils";

// Rotation speeds in degrees per second. The iris eases toward whichever applies, so changes feel physical, not switched.
const IDLE = 14;
const HOVER = 150;
const BUSY = 340;

/**
 * The Kinema mark: a camera aperture (light coming in) with a play triangle in its centre (a film coming out).
 * The six iris blades turn: slowly at rest, faster on hover, a shutter-snap spin on click, and fast while the app is
 * working (so the logo doubles as the loading indicator). Everything animates via transform on one SVG group. (Pivots are 50% of each shape's own box: motion uses
 * `transform-box: fill-box`, so absolute `12px` pivots would be measured from the shape's corner and wobble.)
 */
export function LogoMark({
  className,
  title,
  busy = false,
  hovered = false,
  burst = 0,
}: {
  className?: string;
  title?: string;
  busy?: boolean;
  /** pointer is over the logo (mark OR wordmark) */
  hovered?: boolean;
  /** increment to fire a shutter-snap */
  burst?: number;
}) {
  const reduce = useReducedMotion();
  const angle = useMotionValue(0);
  const pulse = useMotionValue(1);
  const glow = useMotionValue(0);
  const physics = useRef({ vel: IDLE, target: IDLE, hovering: false });

  // keep the target speed and halo in sync with hover / busy (refs + motion values: nothing re-renders)
  useEffect(() => {
    const p = physics.current;
    p.hovering = hovered;
    p.target = busy ? BUSY : hovered ? HOVER : IDLE;
    animate(glow, hovered || busy ? 1 : 0, { duration: 0.35 });
  }, [hovered, busy, glow]);

  const lastBurst = useRef(burst);
  useEffect(() => {
    if (burst === lastBurst.current) return;
    lastBurst.current = burst;
    if (reduce) return;
    physics.current.vel += 900; // a burst that decays back to the resting speed
    animate(pulse, [1, 1.42, 1], { duration: 0.5, ease: [0.22, 1, 0.36, 1] });
  }, [burst, reduce, pulse]);

  useAnimationFrame((_, delta) => {
    if (reduce) return;
    const p = physics.current;
    const dt = Math.min(delta, 50) / 1000;
    p.vel += (p.target - p.vel) * Math.min(1, dt * 4.5); // ease toward the target speed
    angle.set((angle.get() + p.vel * dt) % 360);
  });

  return (
    <motion.svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("h-7 w-7 overflow-visible", className)}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <GlowFilter glow={glow} />
      <circle cx="12" cy="12" r="10" />
      <motion.g style={{ rotate: angle, originX: 0.5, originY: 0.5 }}>
        <path d="m14.31 8 5.74 9.94" />
        <path d="M9.69 8h11.48" />
        <path d="m7.38 12 5.74-9.94" />
        <path d="M9.69 16 3.95 6.06" />
        <path d="M14.31 16H2.83" />
        <path d="m16.62 12-5.74 9.94" />
      </motion.g>
      <motion.path d="M10.3 9.5 15 12l-4.7 2.5Z" fill="currentColor" stroke="none" style={{ scale: pulse, originX: 0.5, originY: 0.5 }} />
    </motion.svg>
  );
}

/** A soft white halo whose strength follows the hover state (a blurred copy of the disc, drawn behind the mark). */
function GlowFilter({ glow }: { glow: MotionValue<number> }) {
  const opacity = useTransform(glow, [0, 1], [0, 0.32]);
  return <motion.circle cx="12" cy="12" r="10" stroke="none" fill="currentColor" style={{ opacity, scale: 1.2, originX: 0.5, originY: 0.5, filter: "blur(5px)" }} />;
}

export function Logo({ className, busy }: { className?: string; busy?: boolean }) {
  const ws = useWorkspaceOptional();
  const working = busy ?? ws?.busy ?? false;
  const [hovered, setHovered] = useState(false);
  const [clicks, setClicks] = useState(0);
  return (
    <span
      className={cn("logo-group flex items-center gap-2.5", className)}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onPointerDown={() => setClicks((c) => c + 1)}
    >
      <LogoMark className="h-8 w-8 text-white" busy={working} hovered={hovered} burst={clicks} />
      <span className="wordmark font-display text-[1.75rem] italic leading-none tracking-tight" data-busy={working || undefined}>
        {BRAND.name}
      </span>
    </span>
  );
}
