"use client";

import useSWR from "swr";
import { Loader2, CheckCircle2, Database } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils/cn";

/**
 * MigrationProgress
 * ─────────────────
 * Live data-sync progress shown at the top of the notification sidebar while a
 * sync is running. Polls the per-report cursor status and renders an overall
 * bar plus the reports currently in flight. Renders nothing when idle.
 */
interface PipelineStatus {
  key: string;
  label: string;
  status: "idle" | "running" | "success" | "failed";
  rows_stored: number;
  total_items: number | null;
  complete: boolean;
  percent: number;
}

async function fetcher(url: string): Promise<{ pipelines: PipelineStatus[] }> {
  const res = await apiFetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function MigrationProgress() {
  const { data } = useSWR<{ pipelines: PipelineStatus[] }>(
    "/api/connections/tranzact/sync/pipelines",
    fetcher,
    {
      refreshInterval: (d) =>
        d?.pipelines?.some((p) => p.status === "running") ? 2500 : 0,
      revalidateOnFocus: true,
    },
  );

  const pipelines = data?.pipelines ?? [];
  const running = pipelines.filter((p) => p.status === "running");
  if (running.length === 0) return null; // only show during an active sync

  const total = pipelines.length;
  const done = pipelines.filter((p) => p.complete).length;
  const rows = pipelines.reduce((s, p) => s + (p.rows_stored ?? 0), 0);
  const overallPct = total ? Math.round((done / total) * 100) : 0;

  return (
    <div className="px-4 py-3 border-b border-white/[0.07] bg-[#C08457]/[0.04]">
      <div className="flex items-center gap-2 mb-2">
        <Database className="w-3.5 h-3.5 text-[#C08457]" />
        <span className="text-xs font-medium text-[#F2DEC8]">Syncing TranzAct data</span>
        <span className="ml-auto text-[11px] text-zinc-500 tabular-nums">
          {done}/{total} reports · {rows.toLocaleString("en-IN")} rows
        </span>
      </div>

      <div className="w-full bg-white/[0.06] rounded-full h-1 overflow-hidden mb-2.5">
        <div className="h-full rounded-full bg-[#C08457] transition-all" style={{ width: `${overallPct}%` }} />
      </div>

      <ul className="space-y-1.5">
        {running.map((p) => (
          <li key={p.key} className="flex items-center gap-2 text-[11px]">
            <Loader2 className="w-3 h-3 text-[#C08457] animate-spin shrink-0" />
            <span className="text-[#F2DEC8]/80 truncate flex-1">{p.label}</span>
            <span className="text-zinc-500 tabular-nums shrink-0">
              {p.total_items
                ? `${p.rows_stored.toLocaleString("en-IN")}/${p.total_items.toLocaleString("en-IN")}`
                : `${p.rows_stored.toLocaleString("en-IN")}`}
            </span>
          </li>
        ))}
      </ul>

      {done === total && (
        <p className="flex items-center gap-1.5 text-[11px] text-[#d4a070] mt-2">
          <CheckCircle2 className="w-3.5 h-3.5" /> All reports synced
        </p>
      )}
    </div>
  );
}
