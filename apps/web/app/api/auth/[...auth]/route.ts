/**
 * app/api/auth/[...auth]/route.ts
 * BFF proxy for platform auth endpoints.
 *   GET  /api/auth/me      → FastAPI /auth/me
 *
 * Login/logout are handled by Supabase Auth on the client; FastAPI only verifies
 * the Supabase access token, which is forwarded here as a Bearer header.
 */
import { NextRequest, NextResponse } from "next/server";
import { backendAuthHeaders } from "@/lib/supabase/server";

const FASTAPI_URL  = process.env.FASTAPI_INTERNAL_URL ?? "http://localhost:8000";
const INTERNAL_KEY = process.env.INTERNAL_API_KEY     ?? "";

async function proxy(request: NextRequest, segments: string[]) {
  const path     = segments.join("/");
  const upstream = `${FASTAPI_URL}/auth/${path}`;
  const isGet    = request.method === "GET";
  const body     = isGet ? undefined : await request.text();

  const res = await fetch(upstream, {
    method: request.method,
    headers: {
      "Content-Type":   "application/json",
      "X-Internal-Key": INTERNAL_KEY,
      ...(await backendAuthHeaders()),
      Cookie: request.headers.get("cookie") ?? "",
    },
    body: body || undefined,
    cache: "no-store",
  });

  const data     = await res.json();
  const response = NextResponse.json(data, { status: res.status });

  const setCookie = res.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);

  return response;
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ auth: string[] }> },
) {
  return proxy(req, (await params).auth);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ auth: string[] }> },
) {
  return proxy(req, (await params).auth);
}
