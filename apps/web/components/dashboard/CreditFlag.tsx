"use client";

import useSWR from "swr";
import { ShieldAlert, Eye } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils/cn";

/**
 * The visible end of the first synapse.
 *
 * Accounts notices a customer has stopped paying; this is where Sales finds
 * out — on the quote, on the order, next to the name, before the next one is
 * taken. The badge carries the reason in the hover, because a warning nobody
 * can interrogate is a warning people route around.
 *
 * One fetch decorates every screen. Asking per row would be the same
 * information at twenty times the cost, and the set stays small because a flag
 * is only raised when something is actually wrong.
 */

export interface CreditFlag {
  customer_ref: string;
  level: "hold" | "watch";
  reason: string;
  raised_at: string | null;
  overridden: boolean;
}

async function fetcher(url: string) {
  const res = await apiFetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useFlags() {
  return useSWR<{ flags: Record<string, CreditFlag>; hold_count: number; watch_count: number }>(
    "/api/be/dashboard/flags", fetcher, { revalidateOnFocus: false },
  );
}

export function FlagBadge({ flag, compact }: { flag?: CreditFlag; compact?: boolean }) {
  if (!flag || flag.overridden) return null;
  const hold = flag.level === "hold";
  const Icon = hold ? ShieldAlert : Eye;
  return (
    <span
      title={flag.reason}
      className={cn(
        "inline-flex items-center gap-1 shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
        hold
          ? "border-red-400/40 text-red-300 bg-red-500/10"
          : "border-amber-300/30 text-amber-300 bg-amber-400/[0.08]",
      )}
    >
      <Icon className="w-3 h-3" />
      {compact ? null : hold ? "On hold" : "Watch"}
    </span>
  );
}
