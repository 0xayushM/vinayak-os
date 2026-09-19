/**
 * hooks/useBrain.ts
 * ──────────────────
 * What the brain did while nobody was watching: which watchers exist, when
 * each last ran, what it found, and what it proposed.
 */
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { apiErrorFromResponse } from "@/lib/errors";

async function fetcher<T>(url: string): Promise<T> {
  const res = await apiFetch(url);
  if (!res.ok) throw await apiErrorFromResponse(res);
  return res.json();
}

export interface Watcher {
  key: string;
  title: string;
  what_it_does: string;
  enabled: boolean;
  interval_minutes: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  halted: boolean;
}

export interface BrainRun {
  id: number;
  workflow_key: string;
  title: string;
  trigger: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  status: string;
  events_emitted: number;
  actions_proposed: number;
  summary: string | null;
  error: string | null;
}

export interface BrainEvent {
  id: number;
  event_type: string;
  entity_ref: string | null;
  payload: Record<string, unknown>;
  severity: number;
  source: string | null;
  created_at: string | null;
  processed_at: string | null;
  processed_by: string | null;
  outcome: Record<string, unknown>;
}

export interface BrainResponse {
  workflows: Watcher[];
  runs: BrainRun[];
  events: BrainEvent[];
  counts: {
    pending_events: number;
    events_this_week: number;
    runs_this_week: number;
    errors_this_week: number;
    proposals_this_week: number;
    awaiting_approval: number;
  };
}

export function useBrain() {
  return useSWR<BrainResponse>("/api/be/dashboard/brain", fetcher, {
    refreshInterval: 60_000,
  });
}

export async function setWatcherEnabled(key: string, enabled: boolean) {
  const res = await apiFetch(`/api/be/dashboard/brain/workflows/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error("Could not change that watcher");
  return res.json();
}

export async function runWatcherNow(key: string) {
  const res = await apiFetch(`/api/be/dashboard/brain/run/${key}`, { method: "POST" });
  if (!res.ok) throw new Error("Could not run that watcher");
  return res.json();
}

// ── Worker health (Sync page) ────────────────────────────────────────────────
// Each section can come back as { error } on its own — a missing table must
// show as that sentence, not as a blank panel.
export type SectionError = { error: string };

export function sectionError(s: unknown): string | null {
  return s && typeof s === "object" && "error" in s ? String((s as SectionError).error) : null;
}

export interface WorkerStatus {
  state: "alive" | "stale" | "never";
  alive: boolean;
  last_beat_at: string | null;
  minutes_since_beat: number | null;
  stale_after_minutes: number;
  worker_id: string | null;
  role: string | null;
  version: string | null;
  started_at: string | null;
  jobs: number | null;
  other_schedulers: { worker_id: string; role: string; last_beat_at: string | null }[];
}

export interface HaltedWatcher {
  key: string;
  title: string;
  last_error: string | null;
  last_run_at: string | null;
  consecutive_errors: number;
}

export interface BrainStatus {
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_workflow: string | null;
  halted: HaltedWatcher[];
}

export interface FeedStatus {
  failing: { pipeline_name: string; completed_at: string | null; error_message: string | null }[];
  stale: { pipeline_name: string; completed_at: string | null }[];
  last_completed_at: string | null;
  feeds: { pipeline_name: string; status: string; completed_at: string | null; stale: boolean }[];
}

export interface RecentAlert {
  kind: string;
  subject: string;
  global: boolean;
  first_seen_at: string | null;
  last_seen_at: string | null;
  times_seen: number;
  last_sent_at: string | null;
  email_error: string | null;
}

export interface WorkerHealth {
  checked_at: string;
  worker: WorkerStatus | SectionError;
  brain: BrainStatus | SectionError;
  sync: FeedStatus | SectionError;
  alerts: RecentAlert[] | SectionError;
}

export function useWorkerHealth() {
  return useSWR<WorkerHealth>("/api/be/dashboard/worker", fetcher, {
    refreshInterval: 60_000,
    revalidateOnFocus: true,
  });
}

/** "4m ago" — the only time format a run log needs. */
export function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (secs < 90) return "just now";
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return `${Math.round(secs / 86400)}d ago`;
}
