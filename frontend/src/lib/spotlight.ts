"use client";

import { useSyncExternalStore } from "react";

/**
 * Which movie the pointer is hovering. This lives in its own tiny store (not in the app-wide React context) so that
 * moving the mouse across cards re-renders ONLY the backdrop that reacts to it, instead of every card and the whole chat.
 */
export interface Spotlight {
  movieId: number;
  title: string;
  year: number | null;
}

let current: Spotlight | null = null;
const listeners = new Set<() => void>();

export function setSpotlight(next: Spotlight | null): void {
  const same = current === next || (current && next && current.movieId === next.movieId);
  if (same) return; // re-entering the same card is a no-op, not a render
  current = next;
  listeners.forEach((l) => l());
}

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => listeners.delete(cb);
};

export function useSpotlight(): Spotlight | null {
  return useSyncExternalStore(subscribe, () => current, () => null);
}
