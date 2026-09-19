"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatNumber } from "@/lib/utils/cn";
import { useBomCoverage } from "@/hooks/useDashboard";

export function BomCoveragePanel() {
  const { data, error, isLoading } = useBomCoverage();
  const d = data?.data;
  const pct = d?.coverage_pct ?? 0;
  const missing = d?.items_missing_bom ?? 0;
  return (
    <PanelWrapper title="BOM Coverage" subtitle="Items with routing" meta={data?.meta} loading={isLoading} error={error}>
      <div className="pt-2 space-y-3">
        <div className="flex items-end justify-between">
          <span className="text-3xl font-semibold tracking-tight text-[#C08457] tabular-nums">{pct.toFixed(1)}%</span>
          <span className="text-xs text-zinc-500">{formatNumber(d?.items_with_bom ?? 0)}/{formatNumber(d?.total_items ?? 0)} items</span>
        </div>
        <div className="w-full bg-white/[0.06] rounded-full h-2 overflow-hidden">
          <div className="h-full rounded-full bg-[#C08457] transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <div className="mt-auto pt-4 grid grid-cols-2 gap-4">
        <KpiCard label="With BOM" value={formatNumber(d?.items_with_bom ?? 0)} accent="emerald" sub="can be costed" />
        <KpiCard label="Missing BOM" value={formatNumber(missing)} accent={missing > 0 ? "amber" : "emerald"} sub={missing > 0 ? "no cost build-up" : "all covered"} />
      </div>
    </PanelWrapper>
  );
}
