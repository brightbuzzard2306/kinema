"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { API_IS_LOCAL, getAccessCode, setAccessCode, setDeniedHandler } from "@/lib/http";
import { usePosters } from "@/hooks/usePosters";
import { setSpotlight } from "@/lib/spotlight";
import { setStage } from "@/lib/stage";
import { uid } from "@/lib/utils";
import type {
  ChatMessage,
  ChatResponse,
  CompareResponse,
  FeedbackAction,
  Health,
  LlmCheck,
  Meta,
  MovieCardData,
  StreamHandlers,
  MovieSummary,
  ProfileUpdate,
  TasteProfile,
} from "@/lib/types";

const SESSION_KEY = "kinema.session";
const LEGACY_SESSION_KEY = "kinema.session"; // earlier name of the app: keep users' profiles
const WAKE_LIMIT_MS = 180_000; // a sleeping free host needs up to ~a minute to start; wait this long before giving up
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export interface Toast {
  id: string;
  text: string;
}

interface Workspace {
  ready: boolean;
  /** the host is asleep and starting up (shown as a friendly message instead of an error) */
  waking: boolean;
  /** the site is private and needs its access code */
  locked: boolean;
  /** check the code with the server; resolves when accepted, rejects with the reason when not */
  unlock: (code: string) => Promise<void>;
  /** set when the API cannot be reached or the dataset is missing */
  fatal: string | null;
  health: Health | null;
  meta: Meta | null;
  profile: TasteProfile | null;
  messages: ChatMessage[];
  busy: boolean;
  trending: MovieSummary[];
  posters: Record<number, string | null>;
  postersEnabled: boolean;
  why: MovieCardData | null;
  openWhy: (card: MovieCardData | null) => void;
  profileOpen: boolean;
  setProfileOpen: (open: boolean) => void;
  compareOpen: boolean;
  setCompareOpen: (open: boolean) => void;
  /** Rank the current request with all four strategies (read-only on the server). */
  compare: () => Promise<CompareResponse>;
  /** Ask for posters of movies shown outside the chat/ticker (e.g. the comparison panel). */
  prefetchPosters: (ids: number[]) => void;
  titleOf: (movieId: number) => string;
  /** Mode of the latest reply (or the configured mode before any reply) - never claims Claude is connected falsely. */
  llm: { mode: "claude" | "fallback"; reason: string | null; verified: boolean };
  toasts: Toast[];
  dismissToast: (id: string) => void;
  /** stable function; hover state itself is NOT in this context (see lib/spotlight.ts) */
  setSpotlight: typeof setSpotlight;
  send: (text: string) => Promise<void>;
  retry: (messageId: string) => Promise<void>;
  moreLike: (movie: { movie_id: number; title: string }) => Promise<void>;
  refresh: (label?: string) => Promise<void>;
  feedbackFor: (movieId: number) => "like" | "dislike" | null;
  giveFeedback: (movieId: number, action: FeedbackAction) => Promise<void>;
  updateProfile: (update: ProfileUpdate) => Promise<void>;
  newChat: (keepProfile?: boolean) => Promise<void>;
  reload: () => void;
}

const Ctx = createContext<Workspace | null>(null);

/** For components (like the backdrop) that also render outside the chat workspace. */
export function useWorkspaceOptional(): Workspace | null {
  return useContext(Ctx);
}

export function useWorkspace(): Workspace {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWorkspace must be used inside <WorkspaceProvider>");
  return ctx;
}

function assistantFrom(res: ChatResponse): ChatMessage {
  return {
    id: uid(),
    role: "assistant",
    text: res.reply,
    cards: res.recommendations,
    notes: res.notes,
    changes: res.changes,
    suggestions: res.suggestions,
    unresolved: res.unresolved_titles,
    llm: res.llm,
    intent: res.intent,
  };
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [waking, setWaking] = useState(false);
  const [locked, setLocked] = useState(false);
  const [fatal, setFatal] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [profile, setProfile] = useState<TasteProfile | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [trending, setTrending] = useState<MovieSummary[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [attempt, setAttempt] = useState(0);
  const [llmCheck, setLlmCheck] = useState<LlmCheck | null>(null);
  const [why, openWhy] = useState<MovieCardData | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [extraPosterIds, setExtraPosterIds] = useState<number[]>([]);
  const [fetchedTitles, setFetchedTitles] = useState<Record<number, string>>({});
  const busyRef = useRef(false);

  const toast = useCallback((text: string) => {
    const id = uid();
    setToasts((t) => [...t.slice(-2), { id, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);
  const dismissToast = useCallback((id: string) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  // ───────────── bootstrap: session id, health, meta, restore last conversation
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let id: string | null = null;
      try {
        id = localStorage.getItem(SESSION_KEY) ?? localStorage.getItem(LEGACY_SESSION_KEY);
      } catch {
        /* storage blocked: use an in-memory session */
      }
      if (!id || !/^[A-Za-z0-9_-]{8,64}$/.test(id)) id = uid();
      try {
        localStorage.setItem(SESSION_KEY, id); // also migrates a profile saved under the app's earlier name
      } catch {
        /* storage blocked: the session just won't survive a reload */
      }
      try {
        // a free host sleeps when idle: keep knocking (quietly) instead of showing an error
        const started = Date.now();
        let h: Health;
        for (;;) {
          try {
            h = await api.health();
            break;
          } catch (e) {
            const asleep = e instanceof ApiError && (e.unreachable || (e.status >= 502 && e.status <= 504));
            if (!asleep || API_IS_LOCAL || Date.now() - started > WAKE_LIMIT_MS) throw e;
            if (!cancelled) setWaking(true);
            await sleep(3000);
            if (cancelled) return;
          }
        }
        if (cancelled) return;
        setWaking(false);
        setHealth(h);
        if (h.access?.required && !getAccessCode()) {
          setLocked(true);
          setReady(true);
          return;
        }
        setLocked(false);
        const m = await api.meta().catch(() => null);
        if (cancelled) return;
        if (h.status !== "ok") {
          setFatal(h.dataset.error ?? "The recommender is not ready yet.");
          setReady(true);
          return;
        }
        setMeta(m);
        setSessionId(id);
        if (h.llm.enabled) {
          api.llmStatus().then((c) => !cancelled && setLlmCheck(c)).catch(() => undefined);
        }
        const [state, trend] = await Promise.all([api.session(id), api.searchMovies("", 12).catch(() => [])]);
        if (cancelled) return;
        setProfile(state.profile);
        setTrending(trend);
        if (state.last_cards.length) {
          const lastReply = [...state.history].reverse().find((t) => t.role === "assistant");
          setMessages([
            {
              id: uid(),
              role: "assistant",
              text: lastReply ? `Welcome back. Here is where we left off. ${lastReply.text}` : "Welcome back. Here is where we left off.",
              cards: state.last_cards,
            },
          ]);
        }
        setFatal(null);
      } catch (e) {
        if (cancelled) return;
        setWaking(false);
        if (e instanceof ApiError && e.code === "access_denied") setLocked(true);
        else setFatal(e instanceof ApiError ? e.message : "Something went wrong while starting up.");
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  // the server rejected the stored code (it was changed): ask again
  useEffect(() => {
    setDeniedHandler(() => setLocked(true));
    return () => setDeniedHandler(null);
  }, []);

  const unlock = useCallback(async (code: string) => {
    const res = await api.verifyAccess(code.trim());
    setAccessCode(res.token ?? code.trim()); // the browser keeps the server's token, not the code itself
    setLocked(false);
    setReady(false);
    setFatal(null);
    setAttempt((a) => a + 1);
  }, []);

  const reload = useCallback(() => {
    setReady(false);
    setFatal(null);
    setAttempt((a) => a + 1);
  }, []);

  // ───────────── posters for every card we might show
  const posterIds = useMemo(() => {
    const ids = new Set<number>(trending.map((m) => m.movie_id));
    messages.forEach((m) => m.cards?.forEach((c) => ids.add(c.movie_id)));
    extraPosterIds.forEach((id) => ids.add(id));
    return [...ids];
  }, [messages, trending, extraPosterIds]);
  const postersEnabled = !!health?.posters.enabled;
  const posters = usePosters(posterIds, postersEnabled);

  // ───────────── titles for ids in the profile (cards + trending are free; others fetched once)
  const titles = useMemo(() => {
    const known: Record<number, string> = { ...fetchedTitles };
    trending.forEach((m) => (known[m.movie_id] = m.title));
    messages.forEach((m) => m.cards?.forEach((c) => (known[c.movie_id] = c.title)));
    return known;
  }, [messages, trending, fetchedTitles]);

  useEffect(() => {
    if (!profile) return;
    const missing = [...profile.liked_ids, ...profile.disliked_ids].filter((id) => !titles[id]);
    if (!missing.length) return;
    let cancelled = false;
    Promise.all(missing.map((id) => api.movie(id).catch(() => null))).then((rows) => {
      if (cancelled) return;
      setFetchedTitles((t) => ({ ...t, ...Object.fromEntries(rows.filter(Boolean).map((m) => [m!.movie_id, m!.title])) }));
    });
    return () => {
      cancelled = true;
    };
  }, [profile, titles]);

  const prefetchPosters = useCallback((ids: number[]) => {
    setExtraPosterIds((cur) => (ids.every((id) => cur.includes(id)) ? cur : [...new Set([...cur, ...ids])].slice(-120)));
  }, []);

  const compare = useCallback(async () => {
    if (!sessionId) throw new ApiError(0, "Not ready yet.", "not_ready");
    return api.compare(sessionId, { count: 5 });
  }, [sessionId]);

  const titleOf = useCallback((id: number) => titles[id] ?? `Movie #${id}`, [titles]);

  // ───────────── sending
  const runTurn = useCallback(
    async (userText: string, call: (id: string, handlers: StreamHandlers) => Promise<ChatResponse>, existingUserId?: string) => {
      if (!sessionId || busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      const userId = existingUserId ?? uid();
      const pendingId = uid();
      setMessages((m) => [
        ...m.filter((x) => x.id !== userId),
        { id: userId, role: "user", text: userText },
        { id: pendingId, role: "assistant", text: "", pending: true },
      ]);
      try {
        const res = await call(sessionId, {
          // real milestones from the server: drives the live status in the top bar
          onStep: (e) => setStage({ step: e.step, strategy: e.strategy }),
          // the picks are ready before the reply: show them right away, the sentence follows
          onCards: (c) => {
            setProfile(c.profile);
            setMessages((m) =>
              m.map((x) => (x.id === pendingId ? { ...x, cards: c.cards, notes: c.notes, changes: c.changes, unresolved: c.unresolved, intent: c.intent } : x)),
            );
          },
        });
        setProfile(res.profile);
        setMessages((m) => m.map((x) => (x.id === pendingId ? { ...assistantFrom(res), id: pendingId } : x)));
      } catch (e) {
        const text = e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
        setMessages((m) =>
          m.filter((x) => x.id !== pendingId).map((x) => (x.id === userId ? { ...x, failed: true } : x)),
        );
        toast(text);
      } finally {
        busyRef.current = false;
        setBusy(false);
        setStage(null);
      }
    },
    [sessionId, toast],
  );

  const send = useCallback(
    async (text: string) => {
      const clean = text.trim();
      if (!clean) return;
      await runTurn(clean, (id, h) => api.chatStream(id, clean, h));
    },
    [runTurn],
  );

  const retry = useCallback(
    async (messageId: string) => {
      const msg = messages.find((m) => m.id === messageId);
      if (!msg) return;
      await runTurn(msg.text, (id, h) => api.chatStream(id, msg.text, h), messageId);
    },
    [messages, runTurn],
  );

  const moreLike = useCallback(
    async (movie: { movie_id: number; title: string }) => {
      await runTurn(`More like ${movie.title}`, (id, h) => api.recommendStream(id, { anchor_movie_id: movie.movie_id }, h));
    },
    [runTurn],
  );

  const refresh = useCallback(
    async (label?: string) => {
      await runTurn(label ?? "Refresh my picks with my current profile", (id, h) => api.recommendStream(id, {}, h));
    },
    [runTurn],
  );

  // ───────────── profile & feedback (optimistic with rollback)
  const feedbackFor = useCallback(
    (movieId: number) =>
      profile?.liked_ids.includes(movieId) ? "like" : profile?.disliked_ids.includes(movieId) ? "dislike" : null,
    [profile],
  );

  const giveFeedback = useCallback(
    async (movieId: number, action: FeedbackAction) => {
      if (!sessionId || !profile) return;
      const previous = profile;
      const without = (xs: number[]) => xs.filter((i) => i !== movieId);
      setProfile({
        ...profile,
        liked_ids: action === "like" ? [...without(profile.liked_ids), movieId] : without(profile.liked_ids),
        disliked_ids: action === "dislike" ? [...without(profile.disliked_ids), movieId] : without(profile.disliked_ids),
      });
      try {
        setProfile(await api.feedback(sessionId, movieId, action));
      } catch (e) {
        setProfile(previous);
        toast(e instanceof ApiError ? e.message : "Couldn't save that. Please try again.");
      }
    },
    [sessionId, profile, toast],
  );

  const updateProfile = useCallback(
    async (update: ProfileUpdate) => {
      if (!sessionId || !profile) return;
      const previous = profile;
      setProfile({ ...profile, ...update } as TasteProfile);
      try {
        setProfile(await api.putProfile(sessionId, update));
      } catch (e) {
        setProfile(previous);
        toast(e instanceof ApiError ? e.message : "Couldn't update your profile.");
      }
    },
    [sessionId, profile, toast],
  );

  const newChat = useCallback(
    async (keepProfile = true) => {
      if (!sessionId) return;
      try {
        setProfile(await api.reset(sessionId, keepProfile));
        setMessages([]);
        setSpotlight(null);
      } catch (e) {
        toast(e instanceof ApiError ? e.message : "Couldn't start a new chat.");
      }
    },
    [sessionId, toast],
  );

  const llm = useMemo(() => {
    const last = [...messages].reverse().find((m) => m.llm);
    if (last?.llm) return { ...last.llm, verified: true };
    if (!health?.llm.enabled) return { mode: "fallback" as const, reason: "No Anthropic API key configured.", verified: true };
    if (llmCheck) return { mode: llmCheck.ok ? ("claude" as const) : ("fallback" as const), reason: llmCheck.ok ? null : llmCheck.reason, verified: true };
    return { mode: "claude" as const, reason: "Checking that Claude responds…", verified: false };
  }, [messages, health, llmCheck]);

  const value = useMemo<Workspace>(
    () => ({
      ready, waking, locked, unlock, fatal, health, meta, profile, messages, busy, trending, posters, postersEnabled, why, openWhy, profileOpen, setProfileOpen, compareOpen, setCompareOpen, compare, prefetchPosters, titleOf, llm, toasts,
      dismissToast, setSpotlight, send, retry, moreLike, refresh, feedbackFor, giveFeedback, updateProfile, newChat, reload,
    }),
    [ready, waking, locked, unlock, fatal, health, meta, profile, messages, busy, trending, posters, postersEnabled, why, profileOpen, compareOpen, compare, prefetchPosters, titleOf, llm, toasts, dismissToast,
      send, retry, moreLike, refresh, feedbackFor, giveFeedback, updateProfile, newChat, reload],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export type { MovieCardData };
