"use client";

import { useState } from "react";
import useSWR from "swr";
import { History, Loader2, Download, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { apiFetch } from "@/lib/api";

interface CoverageItem {
  key: string;
  label: string;
  oldest_fetched_date: string | null;
}
interface HistoryState {
  running: boolean;
  coverage: CoverageItem[];
}

async function fetcher(url: string): Promise<HistoryState> {
  const res = await apiFetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

// Earliest covered date across all reports — the "data available from" floor.
function earliest(coverage: CoverageItem[]): string | null {
  const dates = coverage.map((c) => c.oldest_fetched_date).filter(Boolean) as string[];
  if (dates.length === 0) return null;
  return dates.sort()[0];
}

interface Props {
  /** "full" shows coverage + the pull-older-history action; "coverage" is read-only. */
  mode?: "full" | "coverage";
}

export function HistoryBackfill({ mode = "full" }: Props) {
  const { data, mutate } = useSWR<HistoryState>(
    "/api/connections/tranzact/history",
    fetcher,
    { refreshInterval: (d) => (d?.running ? 3000 : 0), revalidateOnFocus: false },
  );
  const [pending, setPending] = useState(false);
  const [note, setNote] = useState("");

  const coverage = data?.coverage ?? [];
  const running = data?.running ?? false;
  const since = earliest(coverage);

  async function pullMore() {
    setPending(true);
    setNote("");
    try {
      const res = await apiFetch("/api/connections/tranzact/history", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ months: 1 }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(d.detail ?? `HTTP ${res.status}`);
      setNote(d.status === "already_running" ? "A backfill is already running." : "Pulling one more month of history…");
      mutate();
    } catch (err) {
      setNote(err instanceof Error ? err.message : String(err));
    } finally {
      setPending(false);
    }
  }

  const busy = running || pending;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4 max-w-xl">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-violet-600/20 border border-violet-500/20 flex items-center justify-center">
          <History className="w-4 h-4 text-violet-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Historical data</h3>
          <p className="text-xs text-zinc-500">
            {since ? `Data available from ${fmtDate(since)}` : "No history fetched yet"}
          </p>
        </div>
        {running && (
          <span className="ml-auto flex items-center gap-1.5 text-[11px] text-violet-400">
            <Loader2 className="w-3 h-3 animate-spin" /> Backfilling…
          </span>
        )}
      </div>

      {/* Per-report coverage */}
      <ul className="space-y-1.5">
        {coverage.map((c) => (
          <li key={c.key} className="flex items-center justify-between text-xs">
            <span className="text-zinc-400">{c.label}</span>
            <span className="tabular-nums text-zinc-500 flex items-center gap-1.5">
              {c.oldest_fetched_date && <CheckCircle className="w-3 h-3 text-emerald-500/70" />}
              {fmtDate(c.oldest_fetched_date)}
            </span>
          </li>
        ))}
        {coverage.length === 0 && (
          <li className="text-xs text-zinc-600">Connect TranzAct and run an initial sync first.</li>
        )}
      </ul>

      {mode === "full" && (
        <div className="space-y-2 pt-1">
          <button
            onClick={pullMore}
            disabled={busy}
            className={cn(
              "w-full flex items-center justify-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg transition-colors",
              "bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-50",
            )}
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            {running ? "Backfilling…" : "Pull one more month of history"}
          </button>
          <p className="text-[11px] text-zinc-600">
            Initial sync covers the last month for speed. Each click reaches one
            month further back; the nightly job continues this automatically.
          </p>
          {note && <p className="text-[11px] text-zinc-400">{note}</p>}
        </div>
      )}
    </div>
  );
}
