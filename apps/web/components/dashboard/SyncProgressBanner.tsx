"use client";

/**
 * SyncProgressBanner
 * ──────────────────
 * Renders a compact progress bar at the top of the dashboard content area
 * whenever a TranzAct full-sync is running. Polls every 2 s; auto-hides
 * 5 s after the sync finishes.
 */

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { CheckCircle, Circle, Loader2, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { apiFetch } from "@/lib/api";

type PipelineStatus = "pending" | "running" | "success" | "failed";

interface Pipeline {
  key: string;
  label: string;
  status: PipelineStatus;
  rows: number | null;
  error: string | null;
}

interface SyncState {
  running: boolean;
  total: number;
  completed: number;
  current: string | null;
  error: string | null;
  pipelines: Pipeline[];
}

async function syncFetcher(url: string): Promise<SyncState> {
  const res = await apiFetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function SyncProgressBanner() {
  const [expanded, setExpanded] = useState(false);
  const [visible, setVisible] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data } = useSWR<SyncState>(
    "/api/connections/tranzact/sync",
    syncFetcher,
    {
      refreshInterval: (d) => (d?.running ? 2000 : 0),
      revalidateOnFocus: false,
      onSuccess: (d) => {
        if (d.total === 0) return; // no sync started
        setVisible(true);
        if (!d.running && d.completed >= d.total) {
          // Sync just finished — hide after 6 s
          if (hideTimer.current) clearTimeout(hideTimer.current);
          hideTimer.current = setTimeout(() => setVisible(false), 6000);
        }
      },
    },
  );

  useEffect(() => () => { if (hideTimer.current) clearTimeout(hideTimer.current); }, []);

  if (!visible || !data || data.total === 0) return null;

  const pct = data.total > 0 ? Math.round((data.completed / data.total) * 100) : 0;
  const finished = !data.running && data.completed >= data.total;

  return (
    <div className={cn(
      "border-b border-[#292929] bg-[#0E0E0E] transition-all",
      finished ? "border-[#C08457]/15 bg-[#C08457]/5" : "",
    )}>
      {/* Compact bar */}
      <div className="flex items-center gap-3 px-4 sm:px-6 lg:px-8 py-2">
        {finished
          ? <CheckCircle className="w-3.5 h-3.5 shrink-0 text-[#d4a070]" />
          : <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-[#C08457]" />
        }

        <div className="flex-1 min-w-0 space-y-0.5">
          <p className="text-[11px] text-zinc-400">
            {finished
              ? `Sync complete — ${data.completed} reports imported`
              : `Syncing TranzAct data… ${data.completed}/${data.total} reports`
            }
          </p>
          <div className="h-1 w-full overflow-hidden rounded-full bg-[#292929]">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-700",
                finished ? "bg-[#C08457]" : "bg-[#C08457]",
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        <button
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 text-zinc-600 hover:text-[#DBC3AE]/75 transition-colors"
          title={expanded ? "Hide details" : "Show details"}
        >
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Expanded pipeline list */}
      {expanded && data.pipelines.length > 0 && (
        <div className="px-4 sm:px-6 lg:px-8 pb-3">
          <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-x-6 gap-y-1">
            {data.pipelines.map((p) => (
              <li key={p.key} className="flex items-center gap-1.5 text-[11px]">
                {p.status === "success" && <CheckCircle className="w-3 h-3 shrink-0 text-[#d4a070]" />}
                {p.status === "running" && <Loader2 className="w-3 h-3 shrink-0 animate-spin text-[#C08457]" />}
                {p.status === "failed"  && <XCircle className="w-3 h-3 shrink-0 text-red-400" />}
                {p.status === "pending" && <Circle className="w-3 h-3 shrink-0 text-zinc-700" />}
                <span className={cn(
                  "truncate",
                  p.status === "success" ? "text-zinc-400"
                  : p.status === "running" ? "text-[#DBC3AE]/90"
                  : p.status === "failed"  ? "text-red-400"
                  : "text-zinc-700",
                )}>
                  {p.label}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
