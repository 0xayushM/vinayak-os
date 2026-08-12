"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency } from "@/lib/utils/cn";
import { useCustomerFinance, type CustomerFinanceRow } from "@/hooks/useDashboard";
import { Pager, PER_PAGE, searchCls } from "./_shared";

export function CustomerFinancePanel() {
  const { data, error, isLoading } = useCustomerFinance();
  const all: CustomerFinanceRow[] = data?.data?.items ?? [];
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState<"outstanding" | "revenue" | "overdue">("outstanding");
  const [page, setPage] = useState(0);
  const filtered = (q ? all.filter((c) => c.customer_name.toLowerCase().includes(q.toLowerCase())) : all)
    .slice().sort((a, b) => b[sortKey] - a[sortKey]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PER_PAGE));
  const safePage = Math.min(page, pageCount - 1);
  const rows = filtered.slice(safePage * PER_PAGE, safePage * PER_PAGE + PER_PAGE);
  const badge = (v: string) =>
    v === "hold" ? "bg-red-500/15 text-red-300 border border-red-500/30"
      : v === "watch" ? "bg-amber-500/15 text-amber-300 border border-amber-500/30"
      : "bg-emerald-500/12 text-emerald-300/80 border border-emerald-500/25";
  const th = (label: string, key?: "outstanding" | "revenue" | "overdue") => (
    <th className={`py-1.5 px-2 font-medium ${key ? "cursor-pointer select-none hover:text-zinc-200" : ""} ${key === sortKey ? "text-zinc-200" : ""}`}
      onClick={() => key && (setSortKey(key), setPage(0))}>
      {label}{key === sortKey ? " ↓" : ""}
    </th>
  );
  return (
    <PanelWrapper title="Customer Finance" subtitle={`Look up any customer · ${data?.data?.customer_count ?? 0} total`}
      meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-3 pt-1">
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }}
          placeholder="Search customer…" className={searchCls} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[560px]">
            <thead>
              <tr className="text-xs uppercase tracking-wide opacity-60 text-right">
                <th className="text-left py-1.5 pr-2 font-medium">Customer</th>
                {th("Revenue", "revenue")}
                {th("Outstanding", "outstanding")}
                {th("Overdue", "overdue")}
                <th className="text-right py-1.5 pl-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c, i) => (
                <tr key={i} className="border-t border-white/5">
                  <td className="py-1.5 pr-2 truncate max-w-[200px]">{c.customer_name}</td>
                  <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(c.revenue, true)}</td>
                  <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(c.outstanding, true)}</td>
                  <td className="py-1.5 px-2 text-right tabular-nums opacity-80">{c.overdue ? formatCurrency(c.overdue, true) : "—"}</td>
                  <td className="py-1.5 pl-2 text-right">
                    <span className={`px-2 py-0.5 rounded text-xs uppercase ${badge(c.verdict)}`}>{c.verdict}</span>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={5} className="py-3 text-center opacity-60">No matching customers.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <Pager page={safePage} pageCount={pageCount} onPage={setPage} total={filtered.length} />
      </div>
    </PanelWrapper>
  );
}
