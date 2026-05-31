"use client";

import { useSyncHealth } from "@/hooks/useDashboard";
import { CheckCircle, AlertTriangle, XCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { HistoryBackfill } from "@/components/dashboard/HistoryBackfill";

function StatusIcon({ status }: { status: string }) {
  if (status === "success")
    return <CheckCircle className="w-4 h-4 text-[#C08457] shrink-0" />;
  if (status === "running")
    return <RefreshCw className="w-4 h-4 text-[#C08457] animate-spin shrink-0" />;
  return <XCircle className="w-4 h-4 text-red-500 shrink-0" />;
}

function relTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)    return "Just now";
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function SyncHealthPage() {
  const { data, error, isLoading, mutate } = useSyncHealth();

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-3xl mx-auto w-full animate-rise">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-zinc-50">Sync Health</h1>
          <p className="text-[12.5px] text-zinc-500 mt-1">
            Last 25 pipeline runs across all TranzAct reports
          </p>
        </div>
        <button
          onClick={() => mutate()}
          className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-[#F2DEC8]/90 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </div>

      {/* History coverage — how far back each report has been fetched */}
      <HistoryBackfill mode="coverage" />

      {/* Health banner */}
      {data && (
        <div
          className={cn(
            "rounded-xl border px-4 py-3 flex items-center gap-3 text-sm font-medium",
            data.healthy
              ? "bg-[#C08457]/10 border-[#C08457]/20 text-[#d4a070]"
              : "bg-amber-500/10 border-amber-500/20 text-amber-400",
          )}
        >
          {data.healthy ? (
            <CheckCircle className="w-4 h-4 shrink-0" />
          ) : (
            <AlertTriangle className="w-4 h-4 shrink-0" />
          )}
          {data.healthy
            ? "All pipelines are healthy"
            : `Stale: ${data.stale_pipelines.join(", ")}`}
        </div>
      )}

      {/* Run table */}
      {isLoading && (
        <div className="flex items-center gap-2 text-zinc-500 text-sm">
          <RefreshCw className="w-4 h-4 animate-spin" />
          Loading…
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-400">
          {error.message}
        </div>
      )}

      {data && (
        <div className="surface-card overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/[0.07]">
                <th className="text-left px-4 py-3 text-zinc-500 font-medium">Pipeline</th>
                <th className="text-left px-4 py-3 text-zinc-500 font-medium">Status</th>
                <th className="text-left px-4 py-3 text-zinc-500 font-medium">Started</th>
                <th className="text-left px-4 py-3 text-zinc-500 font-medium">Completed</th>
                <th className="text-right px-4 py-3 text-zinc-500 font-medium">Rows</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((run, i) => (
                <tr
                  key={i}
                  className={cn(
                    "border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors",
                    run.status === "error" && "bg-red-500/5",
                  )}
                >
                  <td className="px-4 py-2.5 font-mono text-[#F2DEC8]/75">{run.pipeline_name}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <StatusIcon status={run.status} />
                      <span
                        className={cn(
                          run.status === "success" && "text-[#d4a070]",
                          run.status === "running" && "text-[#C08457]",
                          run.status === "error"   && "text-red-400",
                        )}
                      >
                        {run.status}
                      </span>
                    </div>
                    {run.error_message && (
                      <p className="text-red-400/70 text-[10px] mt-0.5 truncate max-w-[200px]">
                        {run.error_message}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-zinc-500">{relTime(run.started_at)}</td>
                  <td className="px-4 py-2.5 text-zinc-500">{relTime(run.completed_at)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-zinc-400">
                    {run.rows_upserted != null
                      ? run.rows_upserted.toLocaleString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
