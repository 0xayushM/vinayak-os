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
  const count = d?.received_count ?? 0;
  const rejection = d?.rejection_rate ?? 0;
  return (
    <PanelWrapper title="GRN / Goods Received" subtitle={rangeSubtitle(range)} meta={data?.meta} loading={isLoading} error={error}>
      <div className="flex-1 grid grid-cols-2 grid-rows-[auto_auto] content-between gap-4 pt-2">
        <KpiCard label="GRNs Received" value={formatNumber(count)} accent="blue" sub={formatCurrency(d?.total_value ?? 0, true)} />
        <KpiCard label="Avg / GRN" value={formatCurrency(count > 0 ? (d?.total_value ?? 0) / count : 0, true)} accent="violet" sub="received value" />
        <KpiCard label="Pending QIR" value={formatNumber(d?.pending_qir ?? 0)} accent="amber" sub="awaiting inspection" />
        <KpiCard label="Rejection Rate" value={`${(rejection * 100).toFixed(1)}%`} accent={rejection > 0.05 ? "red" : "emerald"} sub={rejection > 0.05 ? "above 5%" : "within 5%"} />
      </div>
    </PanelWrapper>
  );
}
