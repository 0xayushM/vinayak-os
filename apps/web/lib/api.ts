/**
 * lib/api.ts
 * ──────────
 * Workspace-aware fetch helper.
 *
 * Every page lives under /w/{workspace}/… so the active brand is encoded in the
 * URL (one brand per browser tab). `getWorkspace()` reads that slug from the
 * current pathname and `apiFetch()` attaches it to outgoing API calls as the
 * `X-Workspace-Id` header. The BFF forwards that header to FastAPI, where
 * `require_workspace` scopes every query to the right brand.
 *
 * Because the workspace is in the URL, two tabs open on two different brands
 * each send their own header and see their own data — no shared global state.
 */

const WORKSPACE_HEADER = "X-Workspace-Id";
const WS_RE = /^\/w\/([^/]+)/;

/** Read the active workspace slug from the current pathname (client-only). */
export function getWorkspace(): string | null {
  if (typeof window === "undefined") return null;
  const m = window.location.pathname.match(WS_RE);
  return m ? decodeURIComponent(m[1]) : null;
}

/** Build the path prefix for the active (or given) workspace. */
export function workspacePath(ws: string | null, suffix = ""): string {
  if (!ws) return suffix || "/";
  return `/w/${encodeURIComponent(ws)}${suffix}`;
}

/**
 * fetch() wrapper that always sends credentials and tags the request with the
 * active workspace. Use for every browser → /api/* call.
 *
 * @param workspace  Override the workspace slug (useful during onboarding when
 *                   the URL hasn't changed to /w/{ws}/… yet). Pass null to
 *                   explicitly send no header; omit to read from the URL.
 */
export function apiFetch(
  input: string,
  init: RequestInit = {},
  workspace?: string | null,
): Promise<Response> {
  const ws = workspace !== undefined ? workspace : getWorkspace();
  const headers = new Headers(init.headers);
  if (ws) headers.set(WORKSPACE_HEADER, ws);
  return fetch(input, { ...init, credentials: "include", headers });
}
