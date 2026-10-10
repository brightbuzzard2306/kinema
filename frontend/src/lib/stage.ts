"use client";

import { useSyncExternalStore } from "react";
import type { Strategy } from "./types";

/**
 * What the server is really doing right now (from the streaming endpoint). Its own tiny store so the badge in the top bar can
 * react without re-rendering the chat or any card.
 *
 * Some real steps take ~10 ms (ranking). To keep them readable each status is DISPLAYED for at least MIN_DWELL; this only paces the
 * label, never the data (the picks and reply are shown the moment they arrive).
 */
export type Stage = { step: "interpret" | "rank" | "write"; strategy?: Strategy } | null;

const MIN_DWELL = 650;
let current: Stage = null;
let shownAt = 0;
let queued: Stage | undefined;
let timer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();

const same = (a: Stage, b: Stage) => a?.step === b?.step && a?.strategy === b?.strategy;

function apply(next: Stage): void {
  if (same(current, next)) return;
  current = next;
  shownAt = Date.now();
  listeners.forEach((l) => l());
}

export function setStage(next: Stage): void {
  if (next === null) {
    // the turn is over: clear immediately
    clearTimeout(timer);
    timer = undefined;
    queued = undefined;
    apply(null);
    return;
  }
  const wait = current ? Math.max(0, shownAt + MIN_DWELL - Date.now()) : 0;
  if (wait === 0 && timer === undefined) return apply(next);
  queued = next;
  if (timer === undefined) {
    timer = setTimeout(() => {
      timer = undefined;
      const q = queued;
      queued = undefined;
      if (q) apply(q);
    }, wait);
  }
}

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => listeners.delete(cb);
};

export const useStage = (): Stage => useSyncExternalStore(subscribe, () => current, () => null);
