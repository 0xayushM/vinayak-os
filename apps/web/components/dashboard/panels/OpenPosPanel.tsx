"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { useOpenPOs } from "@/hooks/useDashboard";

export function OpenPosPanel() {
  const { data, error, isLoading } = useOpenPOs();
  const d = data?.data;
  return (
    <PanelWrapper title="Open Purchase Orders" subtitle="Live PO book" meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-3 pt-1">
        <div className="grid grid-cols-3 gap-4">
          <KpiCard label="Open POs" value={formatNumber(d?.open_count ?? 0)} accent="blue" />
          <KpiCard label="Open Value" value={formatCurrency(d?.open_value ?? 0, true)} accent="amber" />
          <KpiCard label="Overdue POs" value={formatNumber(d?.overdue_count ?? 0)} accent="red" />
        </div>
        <div className="space-y-1">
          {(d?.by_vendor ?? []).slice(0, 5).map((v) => (
            <div key={v.vendor_name} className="flex justify-between text-xs gap-2">
              <span title={v.vendor_name} className="text-zinc-400 truncate max-w-[180px]">{v.vendor_name}</span>
              <span className="text-[#F2DEC8]/75 tabular-nums">{formatCurrency(v.value, true)}</span>
            </div>
          ))}
        </div>
      </div>
    </PanelWrapper>
  );
}
