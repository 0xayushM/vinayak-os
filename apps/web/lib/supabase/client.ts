/**
 * lib/supabase/client.ts
 * ──────────────────────
 * Browser Supabase client. Supabase Auth (GoTrue) owns login/passwords/sessions;
 * the session is stored in cookies so the server (proxy.ts + BFF route handlers)
 * can read it too.
 */
import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
