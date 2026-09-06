"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { useBomCoverage } from "@/hooks/useDashboard";

export function BomCoveragePanel() {
  const { data, error, isLoading } = useBomCoverage();
  const d = data?.data;
  const pct = d?.coverage_pct ?? 0;
  return (
    <PanelWrapper title="BOM Coverage" subtitle="Items with routing" meta={data?.meta} loading={isLoading} error={error}>
      <div className="pt-2 space-y-3">
        <div className="flex items-end justify-between">
          <span className="text-3xl font-semibold tracking-tight text-[#C08457] tabular-nums">{pct.toFixed(1)}%</span>
          <span className="text-xs text-zinc-500">{d?.items_with_bom}/{d?.total_items} items</span>
        </div>
        <div className="w-full bg-white/[0.06] rounded-full h-2 overflow-hidden">
          <div className="h-full rounded-full bg-[#C08457] transition-all" style={{ width: `${pct}%` }} />
        </div>
        {(d?.items_missing_bom ?? 0) > 0 && (
          <p className="text-xs text-amber-400">{d?.items_missing_bom} items missing BOM</p>
        )}
      </div>
    </PanelWrapper>
  );
}
