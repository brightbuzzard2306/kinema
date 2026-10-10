/** Shared by the plain API client and the streaming client (kept separate so the two never import each other). */

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code: string = "error",
  ) {
    super(message);
    this.name = "ApiError";
  }
  get unreachable() {
    return this.status === 0;
  }
}

/** True when the API runs on this machine (development): no point waiting for a sleeping host. */
export const API_IS_LOCAL = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/.test(API_URL);

// ---- access code (the site can be private; the code is typed once and kept in this browser)
const ACCESS_KEY = "kinema.access.v1";

export function getAccessCode(): string {
  try {
    return localStorage.getItem(ACCESS_KEY) ?? "";
  } catch {
    return "";
  }
}
export function setAccessCode(code: string): void {
  try {
    localStorage.setItem(ACCESS_KEY, code);
  } catch {
    /* storage blocked: the code is asked for again next visit */
  }
}
export function clearAccessCode(): void {
  try {
    localStorage.removeItem(ACCESS_KEY);
  } catch {
    /* ignore */
  }
}
export const authHeaders = (): Record<string, string> => {
  const code = getAccessCode();
  return code ? { "X-Access-Code": code } : {};
};

let onDenied: (() => void) | null = null;
/** The app registers one listener; it is told whenever the server rejects the stored code. */
export function setDeniedHandler(fn: (() => void) | null): void {
  onDenied = fn;
}
/** A response said "access_denied": forget the stored code and let the app show the access screen. */
export function accessDenied(): void {
  clearAccessCode();
  onDenied?.();
}
