import { accessDenied, API_URL, ApiError, authHeaders } from "./http";
import type { CardsEvent, ChatResponse, StepEvent, StreamHandlers } from "./types";

/** Thrown when streaming itself isn't available (old server, proxy that strips it, no body reader...). The caller falls back to the plain endpoint. */
export class StreamUnavailable extends Error {}

const IDLE_MS = 45_000; // no bytes at all for this long => give up
const TOTAL_MS = 120_000;

function parseBlock(block: string): { name: string; data: unknown } | null {
  if (!block || block.startsWith(":")) return null; // heartbeat comment
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  try {
    return { name, data: JSON.parse(data.join("\n")) };
  } catch {
    return null;
  }
}

/**
 * POST to a Server-Sent-Events endpoint and resolve with the final ChatResponse. Progress (step / cards) is reported as it happens.
 * - failure BEFORE any event arrives  -> StreamUnavailable (caller retries on the non-streaming endpoint; nothing was applied twice)
 * - failure AFTER events have arrived -> ApiError (the turn may already be saved, so no silent retry)
 */
export async function streamTurn(path: string, body: unknown, handlers: StreamHandlers = {}): Promise<ChatResponse> {
  const controller = new AbortController();
  let idle: ReturnType<typeof setTimeout> | undefined;
  const arm = () => {
    clearTimeout(idle);
    idle = setTimeout(() => controller.abort(), IDLE_MS);
  };
  const total = setTimeout(() => controller.abort(), TOTAL_MS);
  let sawEvent = false;
  try {
    arm();
    let res: Response;
    try {
      res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...authHeaders() },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch {
      throw new StreamUnavailable("network");
    }
    if (!res.ok) {
      let message: string | undefined;
      let code = "error";
      try {
        const j = await res.json();
        message = j?.error?.message;
        code = j?.error?.code ?? code;
      } catch {
        /* not JSON */
      }
      if (!message) throw new StreamUnavailable(`http ${res.status}`); // route missing / proxy error page: use the plain endpoint
      if (code === "access_denied") accessDenied();
      throw new ApiError(res.status, message, code);
    }
    if (!res.body) throw new StreamUnavailable("no body");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      arm();
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let cut: number;
      while ((cut = buffer.indexOf("\n\n")) !== -1) {
        const parsed = parseBlock(buffer.slice(0, cut));
        buffer = buffer.slice(cut + 2);
        if (!parsed) continue;
        sawEvent = true;
        if (parsed.name === "step") handlers.onStep?.(parsed.data as StepEvent);
        else if (parsed.name === "cards") handlers.onCards?.(parsed.data as CardsEvent);
        else if (parsed.name === "done") return (parsed.data as { response: ChatResponse }).response;
        else if (parsed.name === "error") {
          const e = parsed.data as { status?: number; message?: string; code?: string };
          throw new ApiError(e.status ?? 500, e.message ?? "Something went wrong. Please try again.", e.code ?? "error");
        }
      }
    }
    if (!sawEvent) throw new StreamUnavailable("empty stream");
    throw new ApiError(0, "The connection was interrupted before the reply finished. Please try again.", "interrupted");
  } catch (e) {
    if (e instanceof StreamUnavailable || e instanceof ApiError) throw e;
    if (!sawEvent) throw new StreamUnavailable("aborted before first event");
    throw new ApiError(0, "The connection was interrupted before the reply finished. Please try again.", "interrupted");
  } finally {
    clearTimeout(idle);
    clearTimeout(total);
  }
}
