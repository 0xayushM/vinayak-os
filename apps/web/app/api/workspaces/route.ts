/**
 * app/api/workspaces/route.ts
 * ────────────────────────────
 * BFF proxy for workspace (brand) management.
 *   GET  /api/workspaces  → FastAPI GET  /workspaces/   (list brands owner can open)
 *   POST /api/workspaces  → FastAPI POST /workspaces/   (create a new brand)
 *
 * No X-Workspace-Id needed: these operate across all of the owner's brands and
 * are authorised purely by the JWT cookie.
 */
import { NextRequest, NextResponse } from "next/server";

const FASTAPI_URL  = process.env.FASTAPI_INTERNAL_URL ?? "http://localhost:8000";
const INTERNAL_KEY = process.env.INTERNAL_API_KEY     ?? "";

async function proxy(request: NextRequest, method: "GET" | "POST") {
  const upstream = `${FASTAPI_URL}/workspaces/`;
  const body = method === "POST" ? await request.text() : undefined;
  try {
    const res = await fetch(upstream, {
      method,
      headers: {
        "Content-Type":   "application/json",
        "X-Internal-Key": INTERNAL_KEY,
        Cookie: request.headers.get("cookie") ?? "",
      },
      body: body || undefined,
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    console.error("[BFF] /api/workspaces upstream error:", err);
    return NextResponse.json({ detail: "Upstream service unavailable" }, { status: 503 });
  }
}

export async function GET(request: NextRequest) {
  return proxy(request, "GET");
}
export async function POST(request: NextRequest) {
  return proxy(request, "POST");
}
