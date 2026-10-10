"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import { api } from "@/lib/api";

/** Module-level poster cache exposed as an external store so React reads it without effect-driven setState. */
const cache = new Map<number, string | null>();
const inflight = new Set<number>();
const listeners = new Set<() => void>();
let version = 0;

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => listeners.delete(cb);
};
const getVersion = () => version;
const notify = () => {
  version += 1;
  listeners.forEach((l) => l());
};

async function load(ids: number[]) {
  for (let i = 0; i < ids.length; i += 24) {
    const batch = ids.slice(i, i + 24);
    try {
      const res = await api.posters(batch);
      batch.forEach((id) => cache.set(id, res.posters[String(id)] ?? null));
    } catch {
      /* transient failure: stay uncached so a later render retries; the typographic art shows meanwhile */
    } finally {
      batch.forEach((id) => inflight.delete(id));
      notify();
    }
  }
}

/**
 * Resolves real poster URLs through the backend (which talks to TMDB only if a key is configured).
 * Missing posters resolve to `null` and the UI draws typographic art instead - never a made-up URL.
 */
export function usePosters(ids: number[], enabled: boolean): Record<number, string | null> {
  const v = useSyncExternalStore(subscribe, getVersion, getVersion);
  const key = ids.join(",");

  useEffect(() => {
    if (!enabled) return;
    const missing = ids.filter((id) => !cache.has(id) && !inflight.has(id));
    if (!missing.length) return;
    missing.forEach((id) => inflight.add(id));
    void load(missing);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);

  return useMemo(() => {
    void v; // recompute whenever the cache changes
    const out: Record<number, string | null> = {};
    ids.forEach((id) => {
      if (cache.has(id)) out[id] = cache.get(id) ?? null;
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, v]);
}
