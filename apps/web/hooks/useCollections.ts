/**
 * hooks/useCollections.ts
 * ────────────────────────
 * The chase list, the recovery proof, and the two facts that stop a chase:
 * a promise to pay and a dispute.
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

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
  return data as T;
}

export interface ChaseRow {
  customer_name: string;
  outstanding: number;
  days_overdue: number;
  rung: number;
  rung_label: string | null;
  priority: number;
  reason: string;
}

export interface ChaseList {
  due: ChaseRow[];
  held: ChaseRow[];
  due_count: number;
  held_count: number;
  due_value: number;
  held_value: number;
}

export interface Recovery {
  chases: number;
  measurable: number;
  recovered: number;
  chased_value: number;
  recovery_rate_pct: number;
  window_days: number;
  since_days: number;
  by_rung: Record<string, { chases: number; recovered: number; rate_pct: number }>;
  no_history: boolean;
  caveat?: string;
}

export function useChaseList() {
  return useSWR<ChaseList>("/api/be/dashboard/collections", fetcher);
}

export function useRecovery() {
  return useSWR<Recovery>("/api/be/dashboard/collections/recovery", fetcher);
}

export function recordPromise(body: {
  customer_ref: string; promised_on: string; amount?: number; note?: string;
}) {
  return post("/api/be/dashboard/collections/promise", body);
}

export function setDispute(customer_ref: string, disputed: boolean, note?: string) {
  return post("/api/be/dashboard/collections/dispute", { customer_ref, disputed, note });
}
