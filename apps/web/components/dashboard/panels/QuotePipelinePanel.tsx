"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useQuoteSummary } from "@/hooks/useDashboard";
import { toRangeOpts, rangeSubtitle } from "./_shared";

export function QuotePipelinePanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useQuoteSummary(toRangeOpts(range));
  const d = data?.data;
  return (
    <PanelWrapper title="Quote Pipeline" subtitle={rangeSubtitle(range)} meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-3 gap-4 pt-2">
        <KpiCard label="Open Quotes" value={formatNumber(d?.open_count ?? 0)} accent="blue" sub={formatCurrency(d?.open_value ?? 0, true)} />
        <KpiCard label="Won" value={formatNumber(d?.won_count ?? 0)} accent="emerald" sub={formatCurrency(d?.won_value ?? 0, true)} />
        <KpiCard label="Conversion Rate" value={`${((d?.conversion_rate ?? 0) * 100).toFixed(1)}%`} accent="violet" />
      </div>
    </PanelWrapper>
  );
}
