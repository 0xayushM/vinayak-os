/**
 * hooks/useBrain.ts
 * ──────────────────
 * What the brain did while nobody was watching: which watchers exist, when
 * each last ran, what it found, and what it proposed.
 */
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

async function fetcher<T>(url: string): Promise<T> {
  const res = await apiFetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
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

/** "4m ago" — the only time format a run log needs. */
export function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (secs < 90) return "just now";
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return `${Math.round(secs / 86400)}d ago`;
}
