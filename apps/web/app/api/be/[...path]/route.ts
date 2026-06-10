/**
 * Generic BFF forwarder: Browser → /api/be/<path> → FastAPI /<path>
 * Used for Layer-2 (profile/memory) and future mutation endpoints. Attaches the
 * internal key + workspace id + cookie, never exposing FastAPI to the browser.
 */
import { NextRequest, NextResponse } from "next/server";

const FASTAPI_URL  = process.env.FASTAPI_INTERNAL_URL ?? "http://localhost:8000";
const INTERNAL_KEY = process.env.INTERNAL_API_KEY     ?? "";

async function proxy(request: NextRequest, segments: string[]) {
  const path     = segments.join("/");
  const qs       = request.nextUrl.search;
  const upstream = `${FASTAPI_URL}/${path}${qs}`;
  const isGet    = request.method === "GET";
  const isDelete = request.method === "DELETE";
  const body     = isGet || isDelete ? undefined : await request.text();

  try {
    const res = await fetch(upstream, {
      method: request.method,
      headers: {
        "Content-Type":   "application/json",
        "X-Internal-Key": INTERNAL_KEY,
        "X-Workspace-Id": request.headers.get("x-workspace-id") ?? "",
        Cookie: request.headers.get("cookie") ?? "",
      },
      body: body || undefined,
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    console.error("[BFF] /api/be upstream error:", err);
    return NextResponse.json({ detail: "Upstream service unavailable" }, { status: 503 });
  }
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
export async function PUT(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
