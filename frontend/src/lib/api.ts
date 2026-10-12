import { StreamUnavailable, streamTurn } from "./stream";
import type {
  ChatResponse,
  CompareResponse,
  EvaluationReport,
  FeedbackAction,
  Health,
  LlmCheck,
  Meta,
  MovieSummary,
  ProfileUpdate,
  SessionState,
  TasteProfile,
  StreamHandlers,
} from "./types";

import { accessDenied, API_URL, ApiError, authHeaders } from "./http";

export { API_URL, ApiError };

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number; keepCode?: boolean }): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), init?.timeoutMs ?? 60_000);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...authHeaders(), ...(init?.headers ?? {}) },
    });
    if (!res.ok) {
      let message = `Request failed (${res.status})`;
      let code = "error";
      try {
        const body = await res.json();
        message = body?.error?.message ?? message;
        code = body?.error?.code ?? code;
      } catch {
        /* non-JSON error body */
      }
      if (code === "access_denied" && !init?.keepCode) accessDenied();
      throw new ApiError(res.status, message, code);
    }
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError(0, "The request took too long. Please try again.", "timeout");
    }
    throw new ApiError(0, "Can't reach the recommender service right now. Please try again in a moment.", "unreachable");
  } finally {
    clearTimeout(timer);
  }
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/health", { timeoutMs: 10_000 }),
  /** Check an access code (a wrong one rejects with the server's message; it never clears a stored code). */
  verifyAccess: (code: string) => request<{ ok: boolean; token?: string }>("/access/verify", { ...post({ code }), timeoutMs: 15_000, keepCode: true }),
  llmStatus: () => request<LlmCheck>("/llm/status", { timeoutMs: 40_000 }),
  meta: () => request<Meta>("/meta"),
  searchMovies: (q: string, limit = 8) =>
    request<{ results: MovieSummary[] }>(`/movies?q=${encodeURIComponent(q)}&limit=${limit}`).then((r) => r.results),
  movie: (id: number) => request<MovieSummary>(`/movies/${id}`),
  posters: (ids: number[]) =>
    request<{ enabled: boolean; posters: Record<string, string | null> }>(`/posters?ids=${ids.join(",")}`, { timeoutMs: 15_000 }),
  chat: (session_id: string, message: string) => request<ChatResponse>("/chat", post({ session_id, message })),
  /** Streaming turn (real progress + early picks). Falls back to the plain endpoint if streaming is unavailable. */
  chatStream: async (session_id: string, message: string, handlers?: StreamHandlers) => {
    try {
      return await streamTurn("/chat/stream", { session_id, message }, handlers);
    } catch (e) {
      if (e instanceof StreamUnavailable) return request<ChatResponse>("/chat", post({ session_id, message }));
      throw e;
    }
  },
  recommendStream: async (session_id: string, opts: { anchor_movie_id?: number; count?: number; fresh?: boolean } = {}, handlers?: StreamHandlers) => {
    try {
      return await streamTurn("/recommend/stream", { session_id, ...opts }, handlers);
    } catch (e) {
      if (e instanceof StreamUnavailable) return request<ChatResponse>("/recommend", post({ session_id, ...opts }));
      throw e;
    }
  },
  recommend: (session_id: string, opts: { anchor_movie_id?: number; count?: number; fresh?: boolean } = {}) =>
    request<ChatResponse>("/recommend", post({ session_id, ...opts })),
  compare: (session_id: string, opts: { count?: number; anchor_movie_id?: number } = {}) =>
    request<CompareResponse>("/compare", post({ session_id, ...opts })),
  feedback: (session_id: string, movie_id: number, action: FeedbackAction) =>
    request<TasteProfile>("/feedback", post({ session_id, movie_id, action })),
  session: (id: string) => request<SessionState>(`/sessions/${id}`),
  putProfile: (id: string, update: ProfileUpdate) =>
    request<TasteProfile>(`/sessions/${id}/profile`, { method: "PUT", body: JSON.stringify(update) }),
  reset: (id: string, keepProfile: boolean) =>
    request<TasteProfile>(`/sessions/${id}/reset?keep_profile=${keepProfile}`, { method: "POST" }),
  evaluation: () => request<EvaluationReport>("/evaluation"),
};
