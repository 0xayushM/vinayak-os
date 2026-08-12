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
      <div className="space-y-3 pt-1">
        <div className="flex gap-4">
          <KpiCard label="Open Orders" value={formatNumber(d?.open_count ?? 0)} accent="blue" />
          <KpiCard label="Open Value" value={formatCurrency(d?.open_value ?? 0, true)} accent="emerald" />
          <KpiCard label="Oldest Order" value={`${d?.oldest_order_days ?? 0}d`} accent="amber" />
        </div>
        <div className="space-y-1">
          {byStatus.map((s) => (
            <div key={s.status} className="flex justify-between text-xs">
              <span className="text-zinc-400">{s.status}</span>
              <div className="flex gap-3">
                <span className="text-zinc-500">{s.count} orders</span>
                <span className="text-[#F2DEC8]/75 tabular-nums">{formatCurrency(s.value, true)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </PanelWrapper>
  );
}

// Open orders by-status detail table (Orders page).
