"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { useOpenOrders } from "@/hooks/useDashboard";

export function OpenOrdersPanel() {
  const { data, error, isLoading } = useOpenOrders();
  const d = data?.data;
  const byStatus = d?.by_status ?? [];
  return (
    <PanelWrapper title="Open Sales Orders" subtitle="Live order book" meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-3 gap-4 pt-1">
        <KpiCard label="Open Orders" value={formatNumber(d?.open_count ?? 0)} accent="blue" />
        <KpiCard label="Open Value" value={formatCurrency(d?.open_value ?? 0, true)} accent="emerald" />
        <KpiCard label="Oldest Order" value={`${d?.oldest_order_days ?? 0}d`} accent="amber" />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto pt-3 space-y-1.5">
        <p className="text-[10.5px] font-medium text-[#7a6055] uppercase tracking-[0.08em]">By status</p>
        {byStatus.map((s) => (
          <div key={s.status} className="flex justify-between gap-2 text-xs">
            <span className="text-zinc-400 truncate">{s.status}</span>
            <div className="flex gap-3 shrink-0">
              <span className="text-zinc-500">{s.count} orders</span>
              <span className="text-[#F2DEC8]/75 tabular-nums">{formatCurrency(s.value, true)}</span>
            </div>
          </div>
        ))}
        {byStatus.length === 0 && <p className="text-xs text-zinc-600">No open orders.</p>}
      </div>
      {d && (
        <p className="text-[11px] text-zinc-500 pt-3 mt-3 border-t border-white/[0.05]">
          {(d.dispatched_pct ?? 0).toFixed(0)}% dispatched
          {" · "}
          <span className={(d.overdue_count ?? 0) > 0 ? "text-red-300/80" : ""}>
            {formatNumber(d.overdue_count ?? 0)} past delivery date
          </span>
        </p>
      )}
    </PanelWrapper>
  );
}

// Open orders by-status detail table (Orders page).
