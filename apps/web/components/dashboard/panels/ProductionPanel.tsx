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
  const wip = d?.wip_count ?? 0;
  const done = d?.completed_count ?? 0;
  const jobs = wip + done;
  const donePct = jobs > 0 ? (done / jobs) * 100 : 0;
  return (
    <PanelWrapper title="Production" subtitle={rangeSubtitle(range, "WIP & completed jobs")} meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-3 gap-4 pt-2">
        <KpiCard label="WIP Jobs" value={formatNumber(wip)} accent="blue" sub={formatCurrency(d?.wip_value ?? 0, true)} />
        <KpiCard label="Completed" value={formatNumber(done)} accent="emerald" />
        <KpiCard label="Avg Cycle Time" value={`${(d?.avg_cycle_days ?? 0).toFixed(1)}d`} accent="amber" />
      </div>

      {/* How the job book splits — finished against still on the floor. */}
      <div className="mt-auto pt-4 space-y-2.5">
        <div className="flex items-baseline justify-between text-[11px]">
          <span className="text-[10.5px] font-medium text-[#7a6055] uppercase tracking-[0.08em]">Jobs</span>
          <span className="text-[#F2DEC8]/80 tabular-nums">{formatNumber(jobs)}</span>
        </div>
        <div className="flex w-full h-2 rounded-full overflow-hidden bg-white/[0.06]">
          <div className="h-full bg-[#d4a070]" style={{ width: `${donePct}%` }} />
          <div className="h-full bg-[#C08457]/45" style={{ width: `${jobs > 0 ? 100 - donePct : 0}%` }} />
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="flex items-center gap-1.5 text-zinc-400">
            <span className="w-2 h-2 rounded-full bg-[#d4a070]" /> Completed {donePct.toFixed(0)}%
          </span>
          <span className="flex items-center gap-1.5 text-zinc-400">
            <span className="w-2 h-2 rounded-full bg-[#C08457]/45" /> In progress {jobs > 0 ? (100 - donePct).toFixed(0) : 0}%
          </span>
        </div>
      </div>
    </PanelWrapper>
  );
}

// ── Row-level detail tables (server-side search / date filter / pagination) ───
