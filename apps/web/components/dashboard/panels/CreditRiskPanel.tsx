"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency } from "@/lib/utils/cn";
import { useCreditRisk, type CreditRiskItem } from "@/hooks/useDashboard";
import { Pager, PER_PAGE, searchCls } from "./_shared";

export function CreditRiskPanel() {
  const { data, error, isLoading } = useCreditRisk();
  const d = data?.data;
  const all: CreditRiskItem[] = d?.items ?? [];
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const filtered = q ? all.filter((c) => c.customer_name.toLowerCase().includes(q.toLowerCase())) : all;
  const pageCount = Math.max(1, Math.ceil(filtered.length / PER_PAGE));
  const safePage = Math.min(page, pageCount - 1);
  const rows = filtered.slice(safePage * PER_PAGE, safePage * PER_PAGE + PER_PAGE);
  const badge = (v: string) =>
    v === "hold"
      ? "bg-red-500/15 text-red-300 border border-red-500/30"
      : "bg-amber-500/15 text-amber-300 border border-amber-500/30";
  return (
    <PanelWrapper title="Credit Risk" subtitle="Deterministic flags — a human still makes the credit call"
      meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-3 pt-1">
        <div className="grid grid-cols-2 gap-4">
          <KpiCard label="Hold" value={String(d?.hold_count ?? 0)} accent="red" sub="don't extend more credit" />
          <KpiCard label="Watch" value={String(d?.watch_count ?? 0)} accent="amber" />
        </div>
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }}
          placeholder="Search customer…" className={searchCls} />
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wide opacity-60">
              <th className="text-left py-1.5 pr-2 font-medium">Customer</th>
              <th className="text-right py-1.5 px-2 font-medium">Outstanding</th>
              <th className="text-left py-1.5 px-2 font-medium">Flags</th>
              <th className="text-right py-1.5 pl-2 font-medium">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => (
              <tr key={i} className="border-t border-white/5">
                <td className="py-1.5 pr-2 truncate max-w-[200px]">{c.customer_name}</td>
                <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(c.outstanding, true)}</td>
                <td className="py-1.5 px-2 opacity-70 text-xs">{c.flags.join(", ")}</td>
                <td className="py-1.5 pl-2 text-right">
                  <span className={`px-2 py-0.5 rounded text-xs uppercase ${badge(c.verdict)}`}>{c.verdict}</span>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={4} className="py-3 text-center opacity-60">No matching customers.</td></tr>
            )}
          </tbody>
        </table>
        <Pager page={safePage} pageCount={pageCount} onPage={setPage} total={filtered.length} />
      </div>
    </PanelWrapper>
  );
}

/** Money in (sales) vs out (purchase spend) per month, and the net. Compact. */
