"use client";

/** components/dashboard/panels/_shared.tsx — helpers shared across panel files. */
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import type { RangeOpts } from "@/hooks/useDashboard";

/** Proposes a payment reminder for a customer → lands in the Approvals inbox. */
export function DraftChaseButton({ customer }: { customer: string }) {
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const draft = async () => {
    setState("sending");
    try {
      const res = await apiFetch("/api/be/dashboard/actions/draft-chase", {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customer_ref: customer }),
      });
      setState(res.ok ? "done" : "error");
    } catch {
      setState("error");
    }
  };
  return (
    <button
      onClick={draft}
      disabled={state === "sending" || state === "done"}
      className="text-[11px] px-2 py-1 rounded border border-white/10 hover:border-[#C08457]/50 hover:text-[#F2DEC8] text-zinc-400 disabled:opacity-50 whitespace-nowrap"
      title="Draft a payment reminder (goes to Approvals for your review)"
    >
      {state === "done" ? "Queued ✓" : state === "sending" ? "…" : state === "error" ? "Retry" : "Draft reminder"}
    </button>
  );
}

// ── Shared helpers ────────────────────────────────────────────────────────────
/** A page-level date range (start/end) → the hook's RangeOpts shape.
 *  With no explicit range we send nothing, so the backend returns the brand's
 *  full data coverage. The top-right date picker is the only thing that narrows
 *  the view — there is no default day window. */
export function toRangeOpts(range: DateRange | undefined): RangeOpts {
  if (range?.start || range?.end) return { start: range.start, end: range.end };
  return {};
}

/** Subtitle that reflects whether the global date picker is narrowing the view. */
export function rangeSubtitle(range: DateRange | undefined, allLabel = "All data"): string {
  return range?.start || range?.end ? "Selected range" : allLabel;
}

/** Pretty-print an ISO date (YYYY-MM-DD or full ISO) → "12 Apr 2026". */
export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function CoverageNote({ from, to }: { from?: string | null; to?: string | null }) {
  if (!from && !to) return null;
  return (
    <p className="text-[10.5px] text-zinc-600 pt-2">
      Data in view: {fmtDate(from)} – {fmtDate(to)}
    </p>
  );
}

// ── Chart palette (dark theme) ────────────────────────────────────────────────
export const COLORS = ["#C08457", "#d4a070", "#C4977A", "#F2DEC8", "#8a6050", "#e0c8b0"];
export const BLUE  = "#C08457";
export const GREEN = "#d4a070";
export const AMBER = "#C08457";

export const tooltipStyle = {
  contentStyle: {
    background: "rgba(14,14,18,0.95)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    boxShadow: "0 12px 32px -16px rgba(0,0,0,0.8)",
    fontSize: 12,
  },
  labelStyle: { color: "#C4977A" },
  itemStyle: { color: "#F2DEC8" },
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function fmt(label: string): (v: any) => [string, string] {
  return (v) => [formatCurrency(Number(v ?? 0)), label];
}

// ── moved from domain panel files ─────────────────────────────

export const PAGE_SIZE = 25;


export const statusPill: Record<string, string> = {
  paid:    "bg-[#C08457]/10 text-[#d4a070] border-[#C08457]/20",
  unpaid:  "bg-amber-500/10 text-amber-300 border-amber-500/20",
  partial: "bg-[#C08457]/15 text-[#C08457] border-[#C08457]/20",
};


export function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-zinc-600">—</span>;
  const cls = statusPill[status.toLowerCase()] ?? "bg-white/[0.05] text-zinc-400 border-white/[0.08]";
  return <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${cls}`}>{status}</span>;
}

// Sales invoice line items — searchable, date-filterable, server-paginated.


export function StatusFilter({ value, options, onChange }: {
  value: string; options: string[]; onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-[var(--bg-elevated)] text-[#F2DEC8]/75 text-[11px] rounded-lg px-2 py-2 border border-white/[0.08] focus:border-[#C08457] focus:outline-none shrink-0 [color-scheme:dark]"
    >
      <option value="">All statuses</option>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

// Purchase invoice line items.


export const PER_PAGE = 10;


export function Pager({ page, pageCount, onPage, total }:
  { page: number; pageCount: number; onPage: (p: number) => void; total: number }) {
  if (pageCount <= 1) return <p className="pt-2 text-[11px] text-zinc-600">{total} row{total === 1 ? "" : "s"}</p>;
  return (
    <div className="flex items-center justify-between pt-2 text-xs text-zinc-500">
      <button disabled={page <= 0} onClick={() => onPage(page - 1)}
        className="px-2 py-1 rounded disabled:opacity-30 hover:text-zinc-200">← Prev</button>
      <span>Page {page + 1} / {pageCount} · {total} rows</span>
      <button disabled={page >= pageCount - 1} onClick={() => onPage(page + 1)}
        className="px-2 py-1 rounded disabled:opacity-30 hover:text-zinc-200">Next →</button>
    </div>
  );
}


export const selectCls =
  "ml-2 rounded-lg bg-black/30 border border-white/10 px-2.5 py-1.5 text-sm text-zinc-100 outline-none focus:border-[#C08457]/60";


export const searchCls =
  "w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-[#C08457]/60";

/** One-screen finance snapshot — the headline numbers, computed. */

