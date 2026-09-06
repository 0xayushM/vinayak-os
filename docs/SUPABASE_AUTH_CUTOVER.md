# Supabase Auth — Cutover Guide

Replaces the legacy custom email+password/JWT with **Supabase Auth**. The backend
change is already merged and **gated**: until `SUPABASE_JWT_SECRET` is set, the
app keeps using the legacy path — so nothing breaks before you cut over.

**Scope:** auth only. The data layer stays raw SQL on Supabase Postgres; tenancy
stays app-level (`company_id` + `require_workspace`). The `users` table is kept as
the **email → company_id** mapping the backend reads after cutover.

---

## What's already done (backend, gated)

- `config.py`: `SUPABASE_URL/ANON_KEY/SERVICE_ROLE_KEY/JWT_SECRET`.
- `api/routes/auth.py`: when `SUPABASE_JWT_SECRET` is set, `get_current_user`
  verifies the Supabase access token (Bearer header), maps `email → company_id`
  via `users`, and `/auth/login` is disabled (Supabase owns login). Legacy path
  and its tests remain intact when the secret is unset.
- `scripts/migrate_users_to_supabase.py`: creates Supabase accounts for existing
  users, preserving the company mapping.

## Cutover, in order

### 1. Supabase project + env
In the Supabase dashboard → Project Settings → API, copy the URL, `anon` key,
`service_role` key, and (API → JWT settings) the **JWT secret**. Set backend env:
```
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...            # setting this flips the backend to Supabase mode
```
Frontend `apps/web/.env.local`:
```
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```
> If your project uses the newer **asymmetric JWT signing keys** (RS256/ES256)
> instead of the shared HS256 secret, verify via JWKS instead — swap
> `_verify_supabase_jwt` to fetch `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`
> and decode with the public key. HS256 + `SUPABASE_JWT_SECRET` is the default.

### 2. Migrate existing users
```
PYTHONPATH=. python -m vinayak.scripts.migrate_users_to_supabase            # dry run
PYTHONPATH=. python -m vinayak.scripts.migrate_users_to_supabase --apply --send-reset
```
Accounts are created email-confirmed with no password; the reset email lets each
user set one. Company access is preserved via the `users` table.

### 3. Frontend — install + files
```
cd apps/web && npm install @supabase/supabase-js @supabase/ssr
```

**`lib/supabase/client.ts`** (browser):
```ts
import { createBrowserClient } from "@supabase/ssr";
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
```

**`lib/supabase/server.ts`** (server components + route handlers):
```ts
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
        setAll: (list) => { try { list.forEach(({ name, value, options }) => store.set(name, value, options)); } catch {} },
      },
    },
  );
}
```

**`middleware.ts`** (replace the cookie-presence gate — same redirect rules,
Supabase session instead of `vb_access_token`):
```ts
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const isProtected = (p: string) => p === "/" || p.startsWith("/w/");

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (list) => { list.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          list.forEach(({ name, value, options }) => response.cookies.set(name, value, options)); },
    } },
  );
  const { data: { user } } = await supabase.auth.getUser();
  const { pathname } = request.nextUrl;
  if (pathname === "/login" && user) return NextResponse.redirect(new URL("/", request.url));
  if (isProtected(pathname) && !user) {
    const url = new URL("/login", request.url); url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return response;
}
export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.).*)"] };
```

**`app/login/page.tsx`** (the sign-in call):
```ts
"use client";
import { createClient } from "@/lib/supabase/client";
// ...in the submit handler:
const supabase = createClient();
const { error } = await supabase.auth.signInWithPassword({ email, password });
if (error) setError(error.message);
else window.location.href = new URLSearchParams(location.search).get("next") ?? "/";
```

**BFF proxy** — attach the Supabase access token when forwarding to FastAPI. In
each `app/api/**/route.ts` that proxies to the backend (e.g. `be/[...path]`),
add the Bearer header alongside the existing `X-Internal-Key` / `X-Workspace-Id`:
```ts
import { createClient } from "@/lib/supabase/server";
const supabase = await createClient();
const { data: { session } } = await supabase.auth.getSession();
// headers forwarded to FastAPI:
headers.set("Authorization", `Bearer ${session?.access_token ?? ""}`);
```

### 4. Flip + verify
Setting `SUPABASE_JWT_SECRET` switches the backend automatically. Verify:
`GET /auth/me` returns the user with the resolved `company_id`; a request with a
tampered/absent token → 401; `POST /auth/login` → 400 ("handled by Supabase").
Run `tsc --noEmit` in `apps/web` after installing the packages.

### 5. Rollback
Unset `SUPABASE_JWT_SECRET` → the backend reverts to the legacy JWT path
instantly. Keep the legacy `users.password_hash` until Supabase is confirmed.

## After cutover (optional cleanup)
Once Supabase is confirmed in production: remove `_issue_jwt` / legacy `/login`
password logic, drop `JWT_SECRET`, and consider phase-2 Postgres RLS with
`auth.uid()` for defense-in-depth tenancy.
