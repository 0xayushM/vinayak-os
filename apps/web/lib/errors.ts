/**
 * lib/errors.ts
 * ─────────────
 * Turns failed API calls into sentences a business owner can read.
 *
 * The people using this product are not engineers. "Internal server error",
 * "HTTP 503" or "Failed to fetch" reads as "this product is broken". Every
 * error that can reach the screen goes through here first: `ApiError.message`
 * is always the plain-language version, and the raw upstream detail is kept on
 * `.detail` for the console only.
 */

export type ErrorKind =
  | "offline"      // the browser has no connection
  | "unreachable"  // our servers could not be reached / are restarting
  | "session"      // signed out or session expired
  | "forbidden"    // signed in, but this account can't see this
  | "not_found"
  | "busy"         // rate limited
  | "rejected"     // a 4xx with a message meant for people
  | "server";      // anything 5xx — our fault, not theirs

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ErrorKind;
  /** Raw upstream detail — for logs, never for the screen. */
  readonly detail: unknown;

  constructor(status: number, kind: ErrorKind, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
    this.detail = detail;
  }
}

const MESSAGES: Record<ErrorKind, string> = {
  offline:     "You appear to be offline. Check your internet connection — this will load again once you're back.",
  unreachable: "We couldn't reach our servers just now. This is usually brief — please try again in a moment.",
  session:     "Your session has ended. Please sign in again to continue.",
  forbidden:   "Your account doesn't have access to this. Ask an admin on your team if you need it.",
  not_found:   "We couldn't find what you were looking for. It may have been moved or removed.",
  busy:        "Things are a little busy right now. Please wait a few seconds and try again.",
  rejected:    "That didn't go through. Please check and try again.",
  server:      "We hit a problem loading this. Your data is safe — please try again in a moment.",
};

/** Short headline to pair with the message in larger error states. */
export const TITLES: Record<ErrorKind, string> = {
  offline:     "You're offline",
  unreachable: "Couldn't connect",
  session:     "Please sign in again",
  forbidden:   "No access",
  not_found:   "Not found",
  busy:        "Busy right now",
  rejected:    "Couldn't complete that",
  server:      "Couldn't load this",
};

// Server messages that name internals (exceptions, keys, config, SQL) are for
// us, not for the person using the app.
const TECHNICAL = /error:|exception|traceback|token|database|sql|fernet|_url|\bkey\b|must be one of|null|undefined|\bhttp\b|[{}[\]<>]|\w+_\w+/i;

function humanDetail(detail: unknown): string | null {
  if (typeof detail !== "string") return null;
  const d = detail.trim();
  if (!d || d.length > 180 || TECHNICAL.test(d)) return null;
  return d;
}

function kindForStatus(status: number): ErrorKind {
  if (status === 401) return "session";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 429) return "busy";
  if (status === 502 || status === 503 || status === 504) return "unreachable";
  if (status >= 500) return "server";
  return "rejected";
}

/** Build a friendly ApiError from a status code and whatever the server said. */
export function apiErrorFor(status: number, detail?: unknown): ApiError {
  const kind = kindForStatus(status);
  // A 4xx with a clear, human sentence (e.g. "Action is already approved;
  // nothing to do") says more than our generic text. 5xx details never show.
  const human = kind === "rejected" || kind === "forbidden" ? humanDetail(detail) : null;
  return new ApiError(status, kind, human ?? MESSAGES[kind], detail);
}

/** Read a failed Response into an ApiError. Safe on non-JSON bodies. */
export async function apiErrorFromResponse(res: Response): Promise<ApiError> {
  let detail: unknown = res.statusText;
  try {
    const body = await res.json();
    detail = body?.detail ?? body;
  } catch {
    /* non-JSON body — keep statusText */
  }
  return apiErrorFor(res.status, detail);
}

/** The error thrown when the request never reached a server at all. */
export function networkError(cause: unknown): ApiError {
  const offline = typeof navigator !== "undefined" && navigator.onLine === false;
  const kind: ErrorKind = offline ? "offline" : "unreachable";
  return new ApiError(0, kind, MESSAGES[kind], cause);
}

/**
 * Any caught value → a sentence safe to put on screen. Use in every `catch`
 * whose message is shown to the user.
 */
export function friendlyMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof TypeError) return networkError(e).message; // fetch() network failure
  return MESSAGES.server;
}

export function errorKind(e: unknown): ErrorKind {
  if (e instanceof ApiError) return e.kind;
  if (e instanceof TypeError) return networkError(e).kind;
  return "server";
}

/** Worth offering a "Try again" button for — the problem may clear on its own. */
export function isRetryable(e: unknown): boolean {
  return ["offline", "unreachable", "busy", "server"].includes(errorKind(e));
}
