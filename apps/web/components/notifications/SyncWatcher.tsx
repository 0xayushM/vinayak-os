"use client";

/**
 * SyncWatcher
 * ───────────
 * Mounted once per workspace. Polls the TranzAct sync status (shared SWR key,
 * so it dedupes with SyncButton / SyncProgressBanner) and turns outcomes into
 * notifications + toasts:
 *   • each report that failed or timed out → its own error/warning entry,
 *   • a summary when the run finishes,
 *   • a guard if a run somehow stays "running" far too long.
 * Dedupe keys (built from finished_at / started_at) keep it from firing twice.
 */

import { useEffect } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { useNotifications } from "./NotificationsProvider";

type PipelineStatus = "pending" | "running" | "success" | "failed" | "timed_out";

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
  started_at: string | null;
  finished_at: string | null;
  pipelines: Pipeline[];
}

async function syncFetcher(url: string): Promise<SyncState> {
  const res = await apiFetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

const STUCK_AFTER_MS = 15 * 60 * 1000; // 15 min — backend caps each report at ~110s

export function SyncWatcher() {
  const { notify } = useNotifications();

  const { data } = useSWR<SyncState>(
    "/api/connections/tranzact/sync",
    syncFetcher,
    { refreshInterval: (d) => (d?.running ? 2500 : 0), revalidateOnFocus: false },
  );

  useEffect(() => {
    if (!data || data.total === 0) return;

    // Stuck-run guard (shouldn't trigger given the backend watchdog).
    if (data.running && data.started_at) {
      const age = Date.now() - new Date(data.started_at).getTime();
      if (age > STUCK_AFTER_MS) {
        notify({
          level: "warning",
          title: "Sync is taking unusually long",
          body: `Started ${Math.round(age / 60000)} min ago and still running. You may want to retry.`,
          dedupeKey: `stuck:${data.started_at}`,
        });
      }
      return;
    }

    const finished = !data.running && data.completed >= data.total && data.finished_at;
    if (!finished) return;
    const stamp = data.finished_at as string;

    const failed = data.pipelines.filter((p) => p.status === "failed");
    const timedOut = data.pipelines.filter((p) => p.status === "timed_out");
    const ok = data.pipelines.filter((p) => p.status === "success");

    failed.forEach((p) =>
      notify({
        level: "error",
        title: `${p.label} failed to sync`,
        body: p.error ?? "The report could not be fetched.",
        dedupeKey: `${stamp}:${p.key}:failed`,
      }),
    );
    timedOut.forEach((p) =>
      notify({
        level: "warning",
        title: `${p.label} timed out`,
        body: p.error ?? "The report took too long and was stopped.",
        dedupeKey: `${stamp}:${p.key}:timeout`,
      }),
    );

    // One summary per finished run.
    const problems = failed.length + timedOut.length;
    notify({
      level: problems === 0 ? "success" : problems >= ok.length ? "error" : "warning",
      title:
        problems === 0
          ? `Sync complete — ${ok.length} report${ok.length === 1 ? "" : "s"} updated`
          : `Sync finished with ${problems} issue${problems === 1 ? "" : "s"}`,
      body:
        problems === 0
          ? undefined
          : `${ok.length} updated, ${failed.length} failed, ${timedOut.length} timed out.`,
      dedupeKey: `${stamp}:summary`,
    });
  }, [data, notify]);

  return null;
}
