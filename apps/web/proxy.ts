/**
 * proxy.ts  (Next.js 16 — formerly middleware.ts)
 * ──────────────────────────────────────────────
 * Optimistic auth gate backed by the Supabase session cookies. Also refreshes
 * the session on every request so the BFF route handlers always have a valid
 * access token to forward to FastAPI (which does the real verification).
 *
 * Routes:
 *   /            → landing page that resolves the owner's default brand
 *   /w/{brand}/… → per-brand dashboard (one brand per tab)
 *   /login       → sign-in
 *
 * Rules:
 *   1. Authenticated user hitting /login → bounce to the landing page.
 *   2. Unauthenticated user hitting a protected route (/ or /w/…) → /login,
 *      preserving the intended destination in ?next=.
 */
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const LOGIN_PATH = "/login";
const HOME_PATH  = "/";

function isProtected(pathname: string): boolean {
  return pathname === "/" || pathname.startsWith("/w/");
}

export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (list) => {
          list.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          list.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  const { data: { user } } = await supabase.auth.getUser();
  const { pathname } = request.nextUrl;

  if (pathname === LOGIN_PATH && user) {
    return NextResponse.redirect(new URL(HOME_PATH, request.url));
  }

  if (isProtected(pathname) && !user) {
    const loginUrl = new URL(LOGIN_PATH, request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

export const config = {
  matcher: [
    // Landing page (resolves default brand)
    "/",
    // Protect all per-brand pages
    "/w/:path*",
    // Redirect /login if already authenticated
    "/login",
  ],
};
