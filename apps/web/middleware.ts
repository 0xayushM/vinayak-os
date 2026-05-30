/**
 * middleware.ts
 * ─────────────
 * Cookie-presence gate (no JWT verification here — that happens in FastAPI).
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
import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "vb_access_token";
const LOGIN_PATH  = "/login";
const HOME_PATH   = "/";

function isProtected(pathname: string): boolean {
  return pathname === "/" || pathname.startsWith("/w/");
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get(COOKIE_NAME)?.value;

  // Already logged in and trying to visit /login → go home (brand resolver)
  if (pathname === LOGIN_PATH && token) {
    return NextResponse.redirect(new URL(HOME_PATH, request.url));
  }

  // Not logged in and trying to visit a protected route → go to login
  if (isProtected(pathname) && !token) {
    const loginUrl = new URL(LOGIN_PATH, request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
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
