"use client";

import { useState } from "react";
import { Play, Pause, AlertTriangle, Loader2, Activity } from "lucide-react";
import {
  useBrain, setWatcherEnabled, runWatcherNow, timeAgo,
  type BrainRun, type BrainEvent,
} from "@/hooks/useBrain";
import { cn } from "@/lib/utils/cn";

/**
 * What the brain did on its own.
 *
 * A background system nobody can inspect is a background system nobody
 * trusts — and the first question after "it chased a customer on Tuesday" is
 * always "why, and what else has it been doing?". Everything here is read
 * straight from the run log and the event bus, so there is no second version
 * of the truth to drift out of step with what actually happened.
 */

function Stat({ label, value, tone }: { label: string; value: number; tone?: "warn" }) {
  return (
    <div className="surface-card p-3">
      <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{label}</p>
      <p className={cn("text-xl font-semibold tabular-nums mt-1",
        tone === "warn" && value > 0 ? "text-amber-300" : "text-[#F2DEC8]")}>{value}</p>
    </div>
  );
}

function RunRow({ r }: { r: BrainRun }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg bg-black/20 border border-white/[0.05] px-3 py-2">
      <div className="min-w-0">
        <p className="text-[12.5px] text-zinc-200 truncate">
          {r.summary || r.title}
        </p>
        <p className="text-[11px] text-zinc-600 mt-0.5">
          {r.title} · {r.trigger === "manual" ? "run by hand" : "on schedule"}
          {r.duration_ms != null && ` · ${r.duration_ms}ms`}
        </p>
        {r.error && <p className="text-[11px] text-red-400 mt-1">{r.error}</p>}
      </div>
      <span className="text-[11px] text-zinc-500 shrink-0 tabular-nums">
        {timeAgo(r.started_at)}
      </span>
    </div>
  );
}

function EventRow({ e }: { e: BrainEvent }) {
  const reason = (e.outcome?.reason as string) || "";
  const acted = Boolean(e.outcome?.action);
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg bg-black/20 border border-white/[0.05] px-3 py-2">
      <div className="min-w-0">
        <p className="text-[12.5px] text-zinc-200 truncate">
          <span className="font-mono text-[11.5px] text-[#C08457]">{e.event_type}</span>
          {e.entity_ref && <span className="text-zinc-400"> · {e.entity_ref.replace(/^.*?:/, "")}</span>}
        </p>
        <p className="text-[11px] text-zinc-600 mt-0.5 line-clamp-2">
          {acted ? "Proposed an action for approval." : reason || "Not yet processed."}
        </p>
      </div>
      <span className="text-[11px] text-zinc-500 shrink-0 tabular-nums">
        {timeAgo(e.created_at)}
      </span>
    </div>
  );
}

export function BrainActivity() {
  const { data, isLoading, mutate } = useBrain();
  const [busy, setBusy] = useState<string | null>(null);

  async function toggle(key: string, enabled: boolean) {
    setBusy(key);
    try { await setWatcherEnabled(key, enabled); await mutate(); }
    finally { setBusy(null); }
  }

  async function runNow(key: string) {
    setBusy(key);
    try { await runWatcherNow(key); await mutate(); }
    finally { setBusy(null); }
  }

  if (isLoading) return <p className="text-sm text-zinc-500">Loading…</p>;
  if (!data) return null;
  const c = data.counts;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 items-start">
        <Stat label="Runs this week" value={c.runs_this_week} />
        <Stat label="Things noticed" value={c.events_this_week} />
        <Stat label="Proposed for you" value={c.proposals_this_week} />
        <Stat label="Failed runs" value={c.errors_this_week} tone="warn" />
      </div>

      <div>
        <h2 className="text-[15px] font-semibold text-[#F2DEC8]">What is watching</h2>
        <p className="text-[11.5px] text-zinc-500 mt-0.5">
          Each one is a query and a threshold, not a judgement call. Turn any of
          them off and it stops running for this business only.
        </p>
        <div className="space-y-2 mt-3">
          {data.workflows.map((w) => (
            <div key={w.key} className="surface-card p-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[13px] text-zinc-100 flex items-center gap-2">
                  {w.title}
                  {w.halted && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-red-400">
                      <AlertTriangle className="w-3 h-3" /> stopped after repeated errors
                    </span>
                  )}
                </p>
                <p className="text-[11.5px] text-zinc-500 mt-0.5">{w.what_it_does}</p>
                <p className="text-[11px] text-zinc-600 mt-1 tabular-nums">
                  ran {timeAgo(w.last_run_at)} · every {formatEvery(w.interval_minutes)}
                  {w.last_error && <span className="text-red-400"> · {w.last_error.slice(0, 80)}</span>}
                </p>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={() => runNow(w.key)}
                  disabled={busy === w.key}
                  className="text-[11.5px] px-2.5 py-1 rounded-lg text-zinc-400 hover:text-[#C08457] hover:bg-white/[0.04] transition disabled:opacity-40"
                >
                  {busy === w.key ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Run now"}
                </button>
                <button
                  onClick={() => toggle(w.key, !w.enabled)}
                  disabled={busy === w.key}
                  title={w.enabled ? "Pause this watcher" : "Resume this watcher"}
                  className={cn("p-1.5 rounded-lg transition disabled:opacity-40",
                    w.enabled ? "text-[#C08457] hover:bg-[#C08457]/10"
                              : "text-zinc-600 hover:text-zinc-300 hover:bg-white/[0.04]")}
                >
                  {w.enabled ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <div>
          <h2 className="text-[15px] font-semibold text-[#F2DEC8] flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#C08457]" /> Recent runs
          </h2>
          <div className="space-y-1.5 mt-3">
            {data.runs.length === 0
              ? <p className="text-[12.5px] text-zinc-600">Nothing has run yet.</p>
              : data.runs.map((r) => <RunRow key={r.id} r={r} />)}
          </div>
        </div>
        <div>
          <h2 className="text-[15px] font-semibold text-[#F2DEC8]">What it noticed</h2>
          <div className="space-y-1.5 mt-3">
            {data.events.length === 0
              ? <p className="text-[12.5px] text-zinc-600">Nothing noticed yet.</p>
              : data.events.map((e) => <EventRow key={e.id} e={e} />)}
          </div>
        </div>
      </div>
    </div>
  );
}

function formatEvery(minutes: number): string {
  if (minutes < 60) return `${minutes} minutes`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} hours`;
  const days = Math.round(minutes / (60 * 24));
  return days === 7 ? "week" : `${days} days`;
}
