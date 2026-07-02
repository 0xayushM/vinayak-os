"use client";

import { useEffect, useRef } from "react";
import useSWR, { useSWRConfig } from "swr";
import { RefreshCw, CheckCircle, XCircle, Loader2, Database, RotateCcw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils/cn";

/**
 * ApiSyncPanel
 * ────────────
 * Run each TranzAct report on its own. Because TranzAct has no server-side date
 * filter, a large history is migrated by WALKING PAGES — the backend keeps a
 * cursor and resumes the remaining pages on each run, so the user never waits on
 * one long call and a migration survives restarts.
 *
 * Polls GET  /api/connections/tranzact/sync/pipelines for progress and
 * POSTs      /api/connections/tranzact/sync/pipeline/{key}            (resume)
 * POSTs      /api/connections/tranzact/sync/pipeline/{key}?restart=true (re-walk)
 */
interface PipelineStatus {
  key: string;
  label: string;
  status: "idle" | "running" | "success" | "failed";
  error: string | null;
  finished_at: string | null;
  rows_stored: number;
  total_items: number | null;
  complete: boolean;
  next_page: number;
  percent: number;
}
interface Resp {
  pipelines: PipelineStatus[];
}

async function fetcher(url: string): Promise<Resp> {
  const res = await apiFetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function subline(p: PipelineStatus): { text: string; tone: string } {
  const stored = p.rows_stored.toLocaleString("en-IN");
  const total = p.total_items?.toLocaleString("en-IN");
  if (p.status === "running")
    return { text: total ? `Migrating… ${stored} / ${total} rows` : `Migrating… ${stored} rows`, tone: "text-[#C08457]" };
  if (p.status === "failed")
    return { text: p.error ?? "Failed", tone: "text-red-400" };
  if (p.complete)
    return { text: total ? `Complete · ${total} rows` : `Complete · ${stored} rows`, tone: "text-[#d4a070]" };
  if (p.rows_stored > 0)
    return { text: total ? `Paused · ${stored} / ${total} rows — resume` : `Paused · ${stored} rows — resume`, tone: "text-zinc-400" };
  return { text: "Not started", tone: "text-zinc-600" };
}

function Bar({ p }: { p: PipelineStatus }) {
  if (p.percent <= 0 && !p.complete) return null;
  return (
    <div className="w-full bg-white/[0.06] rounded-full h-1 overflow-hidden mt-1.5">
      <div
        className={cn("h-full rounded-full transition-all", p.complete ? "bg-[#d4a070]" : "bg-[#C08457]")}
        style={{ width: `${p.complete ? 100 : p.percent}%` }}
      />
    </div>
  );
}

export function ApiSyncPanel() {
  const { mutate: globalMutate } = useSWRConfig();
  const { data, mutate } = useSWR<Resp>(
    "/api/connections/tranzact/sync/pipelines",
    fetcher,
    {
      refreshInterval: (d) =>
        d?.pipelines?.some((p) => p.status === "running") ? 2500 : 0,
      revalidateOnFocus: false,
    },
  );

  const pipelines = data?.pipelines ?? [];
  const anyRunning = pipelines.some((p) => p.status === "running");

  // Refresh dashboard panels whenever a run finishes (progressive fill).
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current !== anyRunning) {
      globalMutate(
        (key) => typeof key === "string" && key.startsWith("/api/dashboard"),
        undefined,
        { revalidate: true },
      );
    }
    wasRunning.current = anyRunning;
  }, [anyRunning, globalMutate]);

  async function runAll() {
    mutate(
      (cur) =>
        cur
          ? { pipelines: cur.pipelines.map((p) => ({ ...p, status: "running" as const, error: null })) }
          : cur,
      { revalidate: false },
    );
    try {
      await apiFetch("/api/connections/tranzact/sync/all", {
        method: "POST",
        credentials: "include",
      });
    } catch {
      /* surfaces via the poll */
    } finally {
      mutate();
    }
  }

  async function run(key: string, restart = false) {
    mutate(
      (cur) =>
        cur
          ? {
              pipelines: cur.pipelines.map((p) =>
                p.key === key ? { ...p, status: "running", error: null } : p,
              ),
            }
          : cur,
      { revalidate: false },
    );
    try {
      await apiFetch(
        `/api/connections/tranzact/sync/pipeline/${key}${restart ? "?restart=true" : ""}`,
        { method: "POST", credentials: "include" },
      );
    } catch {
      /* surfaces via the poll */
    } finally {
      mutate();
    }
  }

  return (
    <div className="surface-card p-5 space-y-4 max-w-xl">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-[#C08457]/15 border border-[#C08457]/20 flex items-center justify-center shrink-0">
            <Database className="w-4 h-4 text-[#C08457]" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-[#F2DEC8]">Data sync</h3>
            <p className="text-xs text-zinc-500">
              Run all reports once when you onboard. Large history pulls in the
              background and resumes where it left off — no need to wait.
            </p>
          </div>
        </div>
        <button
          onClick={runAll}
          disabled={anyRunning}
          title="Fetch every report (runs in the background)"
          className={cn(
            "flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors shrink-0",
            "bg-[#C08457] text-black hover:bg-[#d4a070] disabled:opacity-60 disabled:cursor-default",
          )}
        >
          <RefreshCw className={cn("w-3.5 h-3.5", anyRunning && "animate-spin")} />
          {anyRunning ? "Syncing…" : "Sync all"}
        </button>
      </div>

      <ul className="divide-y divide-white/[0.06]">
        {pipelines.length === 0 && (
          <li className="text-xs text-zinc-600 py-2">
            Connect TranzAct first, then run any report below.
          </li>
        )}
        {pipelines.map((p) => {
          const s = subline(p);
          const running = p.status === "running";
          return (
            <li key={p.key} className="py-2.5">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-[#F2DEC8]/90 truncate flex items-center gap-1.5">
                    {p.complete && !running && <CheckCircle className="w-3.5 h-3.5 text-[#d4a070] shrink-0" />}
                    {p.status === "failed" && <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />}
                    {running && <Loader2 className="w-3.5 h-3.5 text-[#C08457] animate-spin shrink-0" />}
                    {p.label}
                  </p>
                  <span className={cn("text-[11px]", s.tone)}>{s.text}</span>
                  <Bar p={p} />
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    onClick={() => run(p.key)}
                    disabled={running}
                    title={p.complete ? "Refresh latest" : p.rows_stored > 0 ? "Resume remaining pages" : "Start migration"}
                    className={cn(
                      "flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors",
                      "bg-[#C08457]/15 text-[#C08457] border border-[#C08457]/30 hover:bg-[#C08457]/25",
                      "disabled:opacity-60 disabled:cursor-default",
                    )}
                  >
                    <RefreshCw className={cn("w-3 h-3", running && "animate-spin")} />
                    {running
                      ? "Running…"
                      : p.complete
                        ? "Refresh"
                        : p.rows_stored > 0
                          ? "Resume"
                          : "Run"}
                  </button>
                  {p.complete && !running && (
                    <button
                      onClick={() => run(p.key, true)}
                      title="Re-pull the whole report from page 1"
                      className="flex items-center justify-center w-7 h-7 rounded-lg text-zinc-500 hover:text-[#F2DEC8]/80 border border-white/[0.08] transition-colors"
                    >
                      <RotateCcw className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
