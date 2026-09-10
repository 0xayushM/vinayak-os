/**
 * hooks/usePulse.ts
 * ──────────────────
 * The Pulse: the cards the owner lands on, and the two actions a card can
 * start directly (draft a chase, log an experiment).
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

export type Confidence = "CERTAIN" | "PROBABLE" | "UNCERTAIN";

export interface PulseCard {
  key: string;
  title: string;
  headline: { value: number; display: string };
  change: { value: number; display: string; direction: "good" | "bad" | "flat"; label: string } | null;
  why: string;
  items: { label: string; value: string; entity_ref?: string }[];
  action: { label: string; kind: string; params: Record<string, unknown> } | null;
  confidence: Confidence;
  severity: number;
  stale: boolean;
  last_synced_at: string | null;
}

export interface PulseResponse {
  cards: PulseCard[];
  role: string | null;
  failed: string[];
  no_data: boolean;
  needs_attention: number;
}

export function usePulse(sort: "role" | "severity" = "role") {
  return useSWR<PulseResponse>(`/api/be/dashboard/pulse?sort=${sort}`, fetcher, {
    revalidateOnFocus: false,
    refreshInterval: 5 * 60 * 1000,
  });
}

export interface InferredPayments {
  count: number;
  avg_days_to_pay: number | null;
  median_days_to_pay: number | null;
  history_days: number;
  history_building: boolean;
  payments: {
    customer_name: string; invoice_number: string; amount: number;
    paid_on: string | null; days_to_pay: number | null; days_late: number | null;
  }[];
}

export function useInferredPayments() {
  return useSWR<InferredPayments>("/api/be/dashboard/payments/inferred", fetcher, {
    revalidateOnFocus: false,
  });
}

// ── actions a card can start ──────────────────────────────────────────────────

export async function draftChase(customerRef: string, tone?: "gentle" | "firm") {
  const res = await apiFetch("/api/be/dashboard/actions/draft-chase", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tone ? { customer_ref: customerRef, tone } : { customer_ref: customerRef }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
  return data;
}

export async function createExperiment(body: {
  title: string; hypothesis?: string; metric?: string;
  source?: "manual" | "ai_suggested"; status?: string;
  /** Naming a metric makes the experiment close itself when its window ends. */
  metric_key?: string; window_days?: number; entity_ref?: string;
}) {
  const res = await apiFetch("/api/be/dashboard/experiments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
  return data;
}
