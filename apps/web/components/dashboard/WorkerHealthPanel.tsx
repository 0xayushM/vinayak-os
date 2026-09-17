"use client";

import Link from "next/link";
import { AlertTriangle, CheckCircle, Loader2, ServerCrash } from "lucide-react";
import {
  useWorkerHealth, sectionError, timeAgo,
  type WorkerStatus, type BrainStatus, type FeedStatus, type RecentAlert,
} from "@/hooks/useBrain";
import { getWorkspace, workspacePath } from "@/lib/api";
import { cn, syncLabel } from "@/lib/utils/cn";

/**
 * Is the background work actually running?
 *
 * The worker's failure mode is silence: when it stops, nothing on screen
 * breaks, the numbers just stop changing. This panel says so in one line —
 * worker up or down, watchers that have stopped, feeds that are failing — and
 * when it cannot find out, it says that too rather than showing nothing.
 */

function Row({ tone, children }: { tone: "ok" | "warn" | "bad"; children: React.ReactNode }) {
  const Icon = tone === "ok" ? CheckCircle : tone === "warn" ? AlertTriangle : ServerCrash;
  return (
    <div className="flex items-start gap-2 text-[12.5px]">
      <Icon className={cn("w-3.5 h-3.5 shrink-0 mt-0.5",
        tone === "ok" ? "text-[#C08457]" : tone === "warn" ? "text-amber-400" : "text-red-400")} />
      <div className="min-w-0 text-zinc-300">{children}</div>
    </div>
  );
}

function SectionFailed({ what, error }: { what: string; error: string }) {
  return (
    <Row tone="bad">
      Couldn’t read {what}: <span className="text-red-300/80">{error}</span>
    </Row>
  );
}

function WorkerLine({ w }: { w: WorkerStatus }) {
  if (w.state === "never") {
    return (
      <Row tone="bad">
        <span className="text-red-300">The background worker has never reported in.</span>{" "}
        Syncs, the morning brief and watchers are probably not running.
      </Row>
    );
  }
  const meta = [
    w.role === "api" ? "running inside the API" : null,
    w.version ? `version ${w.version}` : null,
  ].filter(Boolean).join(" · ");
  return (
    <>
      <Row tone={w.alive ? "ok" : "bad"}>
        {w.alive
          ? <>Background worker is running — last check-in {timeAgo(w.last_beat_at)}.</>
          : <><span className="text-red-300">Background worker is down</span> — last check-in {timeAgo(w.last_beat_at)}. Data won’t update until it’s back.</>}
        {meta && <span className="text-zinc-600"> · {meta}</span>}
      </Row>
      {w.other_schedulers.length > 0 && (
        <Row tone="warn">
          {w.other_schedulers.length === 1 ? "Another scheduler is" : `${w.other_schedulers.length} other schedulers are`}{" "}
          also running ({w.other_schedulers.map((o) => o.worker_id).join(", ")}) — jobs may run twice.
        </Row>
      )}
    </>
  );
}

function HaltedLine({ brain }: { brain: BrainStatus }) {
  if (brain.halted.length === 0) {
    return (
      <Row tone="ok">
        No watchers stopped{brain.last_run_at ? ` — last ran ${timeAgo(brain.last_run_at)}` : ""}.
      </Row>
    );
  }
  return (
    <Row tone="bad">
      <span className="text-red-300">
        {brain.halted.length} watcher{brain.halted.length > 1 ? "s" : ""} stopped after repeated errors:
      </span>{" "}
      {brain.halted.map((h) => h.title).join(", ")}.{" "}
      <Link href={workspacePath(getWorkspace(), "/dashboard/brain")}
            className="text-[#C08457] hover:underline">
        Review on Business Brain
      </Link>
    </Row>
  );
}

function FeedsLine({ sync }: { sync: FeedStatus }) {
  if (sync.feeds.length === 0) {
    return <Row tone="warn">No syncs have run for this workspace yet.</Row>;
  }
  if (sync.failing.length === 0 && sync.stale.length === 0) {
    return (
      <Row tone="ok">
        All {sync.feeds.length} feeds syncing — last completed {timeAgo(sync.last_completed_at)}.
      </Row>
    );
  }
  return (
    <>
      {sync.failing.length > 0 && (
        <Row tone="bad">
          <span className="text-red-300">Failing:</span>{" "}
          {sync.failing.map((f) => syncLabel(f.pipeline_name)).join(", ")}
        </Row>
      )}
      {sync.stale.length > 0 && (
        <Row tone="warn">
          Not updated recently: {sync.stale.map((f) => syncLabel(f.pipeline_name)).join(", ")}
        </Row>
      )}
    </>
  );
}

export function WorkerHealthPanel() {
  const { data, error, isLoading } = useWorkerHealth();

  if (isLoading) {
    return (
      <div className="surface-card p-4 flex items-center gap-2 text-[12.5px] text-zinc-500">
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Checking background work…
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-400">
        Couldn’t check background work: {error?.message ?? "no response"}
      </div>
    );
  }

  const workerErr = sectionError(data.worker);
  const brainErr = sectionError(data.brain);
  const syncErr = sectionError(data.sync);
  const alertsErr = sectionError(data.alerts);
  const unsent = alertsErr ? [] : (data.alerts as RecentAlert[]).filter((a) => a.email_error);

  return (
    <div className="surface-card p-4 space-y-2">
      <p className="text-sm font-medium text-zinc-50">Background work</p>
      {workerErr
        ? <SectionFailed what="the worker heartbeat" error={workerErr} />
        : <WorkerLine w={data.worker as WorkerStatus} />}
      {brainErr
        ? <SectionFailed what="watcher status" error={brainErr} />
        : <HaltedLine brain={data.brain as BrainStatus} />}
      {syncErr
        ? <SectionFailed what="sync status" error={syncErr} />
        : <FeedsLine sync={data.sync as FeedStatus} />}
      {alertsErr && <SectionFailed what="recent alerts" error={alertsErr} />}
      {unsent.length > 0 && (
        <Row tone="warn">
          {unsent.length} recent alert{unsent.length > 1 ? "s" : ""} could not be emailed
          ({unsent[0].email_error}).
        </Row>
      )}
    </div>
  );
}
