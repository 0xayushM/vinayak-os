/**
 * lib/supabase/server.ts
 * ──────────────────────
 * Supabase client for server components + route handlers. Reads/refreshes the
 * session from the request cookies. Writes are wrapped in try/catch because
 * server components are not allowed to set cookies (only route handlers and
 * proxy.ts are).
 */
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
  const store = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => store.getAll(),
        setAll: (list) => {
          try {
            list.forEach(({ name, value, options }) => store.set(name, value, options));
          } catch {
            // Called from a server component — safe to ignore, proxy.ts refreshes.
          }
        },
      },
    },
  );
}

/**
 * Authorization header for BFF → FastAPI calls. FastAPI's `get_current_user`
 * verifies this Supabase access token (HS256) and maps email → company_id.
 * Returns an empty object when there is no session, so the backend answers 401.
 */
export async function backendAuthHeaders(): Promise<Record<string, string>> {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  return session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {};
}
