"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency } from "@/lib/utils/cn";
import { useCollectionsPriority } from "@/hooks/useDashboard";
import { DraftChaseButton, Pager, PER_PAGE } from "./_shared";

/** `rows` lets a caller shorten the table when the panel shares a row with a
 *  compact chart — a ten-row table beside a four-bar chart is what leaves half
 *  a card empty. */
export function CollectionsPriorityPanel({ rows: perPage = PER_PAGE }: { rows?: number } = {}) {
  const { data, error, isLoading } = useCollectionsPriority();
  const d = data?.data;
  const items = d?.items ?? [];
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(items.length / perPage));
  const rows = items.slice(page * perPage, page * perPage + perPage);
  return (
    <PanelWrapper title="Collections Priority" subtitle="Overdue receivables ranked by recovery impact"
      meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-3 pt-1">
        <div className="grid grid-cols-2 gap-4">
          <KpiCard label="Total Overdue" value={formatCurrency(d?.total_overdue ?? 0, true)} accent="red" />
          <KpiCard label="Top Customer Share" value={`${(d?.top_share_pct ?? 0).toFixed(1)}%`} accent="amber"
            sub="of overdue in one account" />
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wide opacity-60">
              <th className="text-left py-1.5 pr-2 font-medium">Customer</th>
              <th className="text-right py-1.5 px-2 font-medium">Outstanding</th>
              <th className="text-right py-1.5 px-2 font-medium">Days overdue</th>
              <th className="text-right py-1.5 pl-2 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => (
              <tr key={i} className="border-t border-white/5">
                <td className="py-1.5 pr-2 truncate max-w-[200px]">{c.customer_name}</td>
                <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(c.outstanding, true)}</td>
                <td className="py-1.5 px-2 text-right tabular-nums">{c.days_overdue}</td>
                <td className="py-1.5 pl-2 text-right"><DraftChaseButton customer={c.customer_name} /></td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={4} className="py-3 text-center opacity-60">Nothing overdue — nice.</td></tr>
            )}
          </tbody>
        </table>
        <Pager page={page} pageCount={pageCount} onPage={setPage} total={items.length} />
      </div>
    </PanelWrapper>
  );
}

/** Customer credit table — searchable, sortable-by-verdict, paginated. */
