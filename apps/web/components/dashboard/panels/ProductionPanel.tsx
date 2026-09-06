"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useProductionSummary } from "@/hooks/useDashboard";
import { toRangeOpts, rangeSubtitle } from "./_shared";

export function ProductionPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useProductionSummary(toRangeOpts(range));
  const d = data?.data;
  return (
    <PanelWrapper title="Production" subtitle={rangeSubtitle(range, "WIP & completed jobs")} meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-3 gap-4 pt-2">
        <KpiCard label="WIP Jobs" value={formatNumber(d?.wip_count ?? 0)} accent="blue" sub={formatCurrency(d?.wip_value ?? 0, true)} />
        <KpiCard label="Completed" value={formatNumber(d?.completed_count ?? 0)} accent="emerald" />
        <KpiCard label="Avg Cycle Time" value={`${(d?.avg_cycle_days ?? 0).toFixed(1)}d`} accent="amber" />
      </div>
    </PanelWrapper>
  );
}

// ── Row-level detail tables (server-side search / date filter / pagination) ───
