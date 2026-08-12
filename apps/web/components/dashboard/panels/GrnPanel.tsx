"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useGrnSummary } from "@/hooks/useDashboard";
import { toRangeOpts, rangeSubtitle } from "./_shared";

export function GrnPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useGrnSummary(toRangeOpts(range));
  const d = data?.data;
  return (
    <PanelWrapper title="GRN / Goods Received" subtitle={rangeSubtitle(range)} meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-3 gap-4 pt-2">
        <KpiCard label="GRNs Received" value={formatNumber(d?.received_count ?? 0)} accent="blue" sub={formatCurrency(d?.total_value ?? 0, true)} />
        <KpiCard label="Pending QIR" value={formatNumber(d?.pending_qir ?? 0)} accent="amber" />
        <KpiCard label="Rejection Rate" value={`${((d?.rejection_rate ?? 0) * 100).toFixed(1)}%`} accent={(d?.rejection_rate ?? 0) > 0.05 ? "red" : "emerald"} />
      </div>
    </PanelWrapper>
  );
}
