"use client";

import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils/cn";

/**
 * SyncButton
 * ──────────
 * Replaces the passive "Stale" badge with an action: pull the latest data.
 *
 * Clicking POSTs to /api/connections/tranzact/sync, which runs an *incremental*
 * forward sync — each pipeline fetches from its last successful date up to today
 * (NOT a historical backfill; that lives in HistoryBackfill). The button then
 * polls the same endpoint for `running` and, once the run finishes, revalidates
 * every `/api/dashboard/*` SWR key so all panels pick up the fresh rows.
 *
 * The status query is keyed on the shared endpoint URL, so every SyncButton on
 * the page reflects the same running state — clicking one spins them all.
 */
interface SyncState {
  running: boolean;
}

async function statusFetcher(url: string): Promise<SyncState> {
  const res = await apiFetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function SyncButton({ className }: { className?: string }) {
  const { mutate: globalMutate } = useSWRConfig();
  const { data, mutate } = useSWR<SyncState>(
    "/api/connections/tranzact/sync",
    statusFetcher,
    { refreshInterval: (d) => (d?.running ? 3000 : 0), revalidateOnFocus: false },
  );

  const [starting, setStarting] = useState(false);
  const running = starting || (data?.running ?? false);
  const wasRunning = useRef(false);

  // When a run transitions running → idle, refresh all dashboard panels.
  useEffect(() => {
    if (wasRunning.current && !running) {
      globalMutate(
        (key) => typeof key === "string" && key.startsWith("/api/dashboard"),
        undefined,
        { revalidate: true },
      );
    }
    wasRunning.current = running;
  }, [running, globalMutate]);

  async function onClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (running) return;
    setStarting(true);
    try {
      await apiFetch("/api/connections/tranzact/sync", { method: "POST" });
    } catch {
      /* errors surface via the status poll / panel reload */
    } finally {
      setStarting(false);
      mutate(); // pick up running=true and begin polling
    }
  }

  return (
    <button
      onClick={onClick}
      disabled={running}
      title="Sync to the latest data"
      className={cn(
        "flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-medium transition-colors",
        "bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 hover:bg-indigo-500/20 disabled:opacity-70 disabled:cursor-default",
        className,
      )}
    >
      <RefreshCw className={cn("w-2.5 h-2.5", running && "animate-spin")} />
      {running ? "Syncing…" : "Sync"}
    </button>
  );
}
