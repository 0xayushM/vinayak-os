/**
 * BFF proxy for the connection LIST endpoint (base path).
 * Browser → GET /api/connections/ → FastAPI GET /connections/
 *
 * The catch-all `[...path]/route.ts` only matches paths with at least one
 * segment, so a request to `/api/connections/` (no segment) would 404. This
 * index route handles that base case — used by OnboardingGate to check whether
 * TranzAct is connected.
 */
import { NextRequest, NextResponse } from "next/server";

const FASTAPI_URL  = process.env.FASTAPI_INTERNAL_URL ?? "http://localhost:8000";
const INTERNAL_KEY = process.env.INTERNAL_API_KEY     ?? "";

export async function GET(request: NextRequest) {
  const upstream = `${FASTAPI_URL}/connections/`;
  try {
    const res = await fetch(upstream, {
      method: "GET",
      headers: {
        "Content-Type":   "application/json",
        "X-Internal-Key": INTERNAL_KEY,
        Cookie: request.headers.get("cookie") ?? "",
      },
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    console.error("[BFF] /api/connections upstream error:", err);
    return NextResponse.json({ detail: "Upstream service unavailable" }, { status: 503 });
  }
}
