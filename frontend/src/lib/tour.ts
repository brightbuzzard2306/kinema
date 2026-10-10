"use client";

import { useSyncExternalStore } from "react";

/**
 * First-visit tour state. Persisted in localStorage (guarded: private windows / blocked storage must not break the app).
 * step: 0..STEPS-1 while running; `done` once finished or skipped, so it never nags again.
 */
const KEY = "kinema.tour.v1";
export const TOUR_STEPS = 4;

interface TourState {
  step: number;
  done: boolean;
  /** true until we have read storage (so we never flash the tour for returning users) */
  loading: boolean;
}

let state: TourState = { step: 0, done: true, loading: true };
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify({ step: state.step, done: state.done }));
  } catch {
    /* storage blocked: the tour just won't remember its place */
  }
}

/** Read storage once on the client. First-time visitors (nothing stored) get the tour. */
export function loadTour(): void {
  if (!state.loading) return;
  let next: TourState = { step: 0, done: false, loading: false };
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<TourState>;
      const step = Number.isInteger(parsed.step) ? Math.min(Math.max(parsed.step as number, 0), TOUR_STEPS - 1) : 0;
      next = { step, done: parsed.done === true, loading: false };
    }
  } catch {
    next = { step: 0, done: false, loading: false };
  }
  state = next;
  emit();
}

export function goToStep(step: number): void {
  if (step >= TOUR_STEPS) return finishTour();
  state = { ...state, step: Math.max(0, step), done: false, loading: false };
  persist();
  emit();
}
export function finishTour(): void {
  state = { ...state, done: true, loading: false };
  persist();
  emit();
}
export function restartTour(): void {
  state = { step: 0, done: false, loading: false };
  persist();
  emit();
}

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => listeners.delete(cb);
};
export const useTour = (): TourState => useSyncExternalStore(subscribe, () => state, () => ({ step: 0, done: true, loading: true }));
