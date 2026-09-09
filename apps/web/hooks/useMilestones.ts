/**
 * hooks/useMilestones.ts
 * ──────────────────────
 * Hooks for the milestone-evidence surface: who I am (role, permissions),
 * usage, experiments, incidents, the Milestone board, and workspace users.
 * All calls go through the generic BFF (/api/be/*) or /api/auth/*.
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

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  const res = await apiFetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
  return data as T;
}

// ── me ────────────────────────────────────────────────────────────────────────
export type Role = "owner" | "finance" | "accountant" | "sales" | "viewer" | "admin";
export interface Me {
  email: string;
  company_id: string;
  role: Role | null;
  role_chosen: boolean;
  may_approve_messages: boolean;
  may_approve_money: boolean;
  pinned_cards: string[] | null;
  display_name: string | null;
}
export function useMe() {
  return useSWR<Me>("/api/auth/me", fetcher, { revalidateOnFocus: false });
}
export function saveMe(body: { role?: Role; display_name?: string; pinned_cards?: string[] }) {
  return send<Me>("/api/auth/me", "PUT", body);
}

/** The card order each role starts with. Users can rearrange later; this is only the seed. */
export const ROLE_LAYOUTS: Record<Exclude<Role, "admin">, { label: string; blurb: string; cards: string[] }> = {
  owner:      { label: "I run the company",   blurb: "What changed, cash, risks, decisions waiting",
                cards: ["week_delta", "cash_30d", "aging_drift", "reorder_radar", "concentration", "inbox"] },
  finance:    { label: "I run the accounts",  blurb: "Working capital, aging, cash, collections",
                cards: ["working_capital", "aging_drift", "payment_behaviour", "cash_30d", "collections_proof", "anomalies"] },
  accountant: { label: "I'm the CA",          blurb: "Exceptions, period figures, data quality",
                cards: ["anomalies", "data_quality", "aging_drift", "working_capital", "cash_30d"] },
  sales:      { label: "I run sales",         blurb: "Credit flags, regulars gone quiet, pipeline",
                cards: ["reorder_radar", "credit_flags", "week_delta", "quotes", "overdue_orders"] },
  viewer:     { label: "I just need to look", blurb: "Read-only overview",
                cards: ["week_delta", "cash_30d", "aging_drift"] },
};

// ── usage ─────────────────────────────────────────────────────────────────────
export interface UsageWeek { week_start: string; active_days: number; qualifies: boolean; partial: boolean }
export interface UsageStats {
  user_email: string; window_days: number; active_days_in_window: number; last_active: string | null;
  weeks: UsageWeek[]; best_run_weeks: number; best_run_days: number;
  current_run_weeks: number; current_run_days: number; current_week: UsageWeek | null; meets_60_days: boolean;
}
export function useMyUsage() {
  return useSWR<UsageStats>("/api/be/dashboard/usage/me", fetcher, { revalidateOnFocus: false });
}

// ── experiments ───────────────────────────────────────────────────────────────
export type ExperimentStatus = "proposed" | "accepted" | "running" | "closed" | "rejected";
export interface Experiment {
  id: string; title: string; hypothesis: string | null; source: "ai_suggested" | "manual";
  status: ExperimentStatus; metric: string | null; baseline: number | null; target: number | null;
  result: number | null; outcome: "positive" | "negative" | "inconclusive" | null; outcome_notes: string | null;
  action_refs: unknown[]; evidence: Record<string, unknown>; proposed_by: string | null; decided_by: string | null;
  started_at: string | null; ends_at: string | null; closed_at: string | null; created_at: string; updated_at: string;
}
export interface ExperimentCounts {
  logged: number; with_outcomes: number; ai_suggested: number; ai_suggested_acted_on: number; running: number; proposed: number;
}
export function useExperiments(status?: ExperimentStatus) {
  const qs = status ? `?status=${status}` : "";
  return useSWR<{ experiments: Experiment[]; counts: ExperimentCounts }>(
    `/api/be/dashboard/experiments${qs}`, fetcher, { revalidateOnFocus: false });
}
export function createExperiment(body: Partial<Experiment> & { title: string }) {
  return send<{ experiment: Experiment }>("/api/be/dashboard/experiments", "POST", body);
}
export function patchExperiment(id: string, body: Partial<Experiment>) {
  return send<{ experiment: Experiment }>(`/api/be/dashboard/experiments/${id}`, "PATCH", body);
}

// ── incidents ─────────────────────────────────────────────────────────────────
export interface Incident {
  id: string; severity: "critical" | "major" | "minor"; title: string; detail: string | null;
  started_at: string | null; resolved_at: string | null; reported_by: string | null;
}
export function useIncidents() {
  return useSWR<{ incidents: Incident[] }>("/api/be/dashboard/incidents", fetcher, { revalidateOnFocus: false });
}
export function createIncident(body: { severity: Incident["severity"]; title: string; detail?: string }) {
  return send<{ id: string }>("/api/be/dashboard/incidents", "POST", body);
}
export function patchIncident(id: string, body: { resolved?: boolean; detail?: string; severity?: Incident["severity"] }) {
  return send<{ ok: boolean }>(`/api/be/dashboard/incidents/${id}`, "PATCH", body);
}

// ── the board ─────────────────────────────────────────────────────────────────
export interface Criterion {
  key: string; title: string; status: "met" | "in_progress" | "not_started" | "at_risk";
  detail: string; value: number | null; target: number | null; extra?: unknown;
}
export interface Board {
  dates: { start: string; month_3_demo: string; month_6_review: string; month_8_latest: string;
           month_12_review: string; month_24_review: string; days_to_month_6: number };
  tracked_user: string; criteria: Criterion[];
}
export function useMilestoneBoard() {
  return useSWR<Board>("/api/be/dashboard/milestones", fetcher, { revalidateOnFocus: false });
}
export function saveMilestoneSettings(body: { milestone_start_date?: string; milestone_user_email?: string }) {
  return send<{ ok: boolean }>("/api/be/dashboard/milestones/settings", "PUT", body);
}

// ── workspace users (owner/admin) ─────────────────────────────────────────────
export interface WorkspaceUser {
  email: string; role: Role | null; may_approve_messages: boolean; may_approve_money: boolean;
  display_name: string | null; global_admin: boolean;
}
export function useWorkspaceUsers() {
  return useSWR<{ users: WorkspaceUser[] }>("/api/be/workspaces/users", fetcher, { revalidateOnFocus: false });
}
export function saveWorkspaceUser(body: { email: string; role?: Role; may_approve_messages?: boolean; may_approve_money?: boolean }) {
  return send<{ ok: boolean }>("/api/be/workspaces/users", "PUT", body);
}
