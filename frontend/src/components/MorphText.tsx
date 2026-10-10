"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

const CHARS = "01ABCDEFGHIJKLMNOPQRSTUVWXYZ#$%&*";
const STAGGER_MS = 22; // delay between neighbouring characters (left to right)
const SCRAMBLE_MS = 300; // how long one character shuffles before it settles
const TICK_MS = 40;

type Cell = { ch: string; live: boolean };

/** Centre `s` inside exactly `w` cells, so every line has the same footprint. */
function pad(s: string, w: number): string[] {
  const text = s.length > w ? s.slice(0, w) : s;
  const total = w - text.length;
  const left = Math.floor(total / 2);
  return (" ".repeat(left) + text + " ".repeat(total - left)).split("");
}
const rand = () => CHARS[Math.floor(Math.random() * CHARS.length)]!;

/**
 * Text that morphs in place between lines inside a FIXED-WIDTH box (`width` characters; use the longest line you will show).
 * Only the characters that actually change shuffle, left to right, dimmed while they shuffle and bright once settled, so the layout never moves.
 * `intro` plays a first reveal on mount. Reduced-motion users get an instant swap. Screen readers get the real text, not the shuffle.
 * Use a monospace font: every cell is the same width.
 */
export function MorphText({
  text,
  width,
  intro = false,
  className,
  liveClassName = "text-white/30",
  settledClassName = "text-white/90",
}: {
  text: string;
  width: number;
  intro?: boolean;
  className?: string;
  liveClassName?: string;
  settledClassName?: string;
}) {
  const reduce = useReducedMotion();
  const [cells, setCells] = useState<Cell[]>(() => pad(text, width).map((ch) => ({ ch, live: false }))); // same on server and client
  const cellsRef = useRef<Cell[]>(cells);
  const firstRun = useRef(true);

  useEffect(() => {
    const target = pad(text, width);
    const first = firstRun.current;
    firstRun.current = false;
    const from = cellsRef.current.map((c) => c.ch);
    const animateAll = first && intro;
    if (first && !intro) return; // initial text is already on screen

    const t0 = performance.now();
    const plan = target.map((ch, i) => {
      const same = !animateAll && from[i] === ch;
      const start = i * STAGGER_MS;
      return { ch, same, start, end: start + SCRAMBLE_MS + Math.random() * 140, prev: animateAll ? " " : (from[i] ?? " ") };
    });

    const apply = (next: Cell[]) => {
      cellsRef.current = next;
      setCells(next);
    };
    const step = () => {
      const now = performance.now() - t0;
      let done = true;
      const next = plan.map((p): Cell => {
        if (p.same || reduce || now >= p.end) return { ch: p.ch, live: false };
        done = false;
        if (now >= p.start) return { ch: p.ch === " " && p.prev === " " ? " " : rand(), live: true };
        return { ch: p.prev, live: false };
      });
      apply(next);
      return done;
    };

    if (reduce) {
      const id = setTimeout(step, 0);
      return () => clearTimeout(id);
    }
    const id = setInterval(() => {
      if (step()) clearInterval(id);
    }, TICK_MS);
    return () => clearInterval(id);
  }, [text, width, intro, reduce]);

  return (
    <span className={cn("inline-flex whitespace-pre font-mono [--trk:0.14em] sm:[--trk:0.24em]", className)} style={{ letterSpacing: "var(--trk)" }}>
      <span className="sr-only">{text}</span>
      {cells.map((c, i) => (
        <span
          key={i}
          aria-hidden
          className={cn("inline-block text-center transition-colors duration-150", c.live ? liveClassName : settledClassName)}
          style={{ width: "calc(1ch + var(--trk))" }}
        >
          {c.ch}
        </span>
      ))}
    </span>
  );
}
