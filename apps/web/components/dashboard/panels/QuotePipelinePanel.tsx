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
  const open = d?.open_value ?? 0;
  const won = d?.won_value ?? 0;
  const quoted = open + won;
  const wonPct = quoted > 0 ? (won / quoted) * 100 : 0;
  return (
    <PanelWrapper title="Quote Pipeline" subtitle={rangeSubtitle(range)} meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-3 gap-4 pt-2">
        <KpiCard label="Open Quotes" value={formatNumber(d?.open_count ?? 0)} accent="blue" sub={formatCurrency(open, true)} />
        <KpiCard label="Won" value={formatNumber(d?.won_count ?? 0)} accent="emerald" sub={formatCurrency(won, true)} />
        <KpiCard label="Conversion Rate" value={`${((d?.conversion_rate ?? 0) * 100).toFixed(1)}%`} accent="violet" />
      </div>

      {/* Where the quoted value sits — won against still open. */}
      <div className="mt-auto pt-4 space-y-2.5">
        <div className="flex items-baseline justify-between text-[11px]">
          <span className="text-[10.5px] font-medium text-[#7a6055] uppercase tracking-[0.08em]">Quoted value</span>
          <span className="text-[#F2DEC8]/80 tabular-nums">{formatCurrency(quoted, true)}</span>
        </div>
        <div className="flex w-full h-2 rounded-full overflow-hidden bg-white/[0.06]">
          <div className="h-full bg-[#d4a070]" style={{ width: `${wonPct}%` }} />
          <div className="h-full bg-[#C08457]/45" style={{ width: `${quoted > 0 ? 100 - wonPct : 0}%` }} />
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="flex items-center gap-1.5 text-zinc-400">
            <span className="w-2 h-2 rounded-full bg-[#d4a070]" /> Won {wonPct.toFixed(0)}%
          </span>
          <span className="flex items-center gap-1.5 text-zinc-400">
            <span className="w-2 h-2 rounded-full bg-[#C08457]/45" /> Open {quoted > 0 ? (100 - wonPct).toFixed(0) : 0}%
          </span>
        </div>
        {quoted === 0 && <p className="text-[11px] text-zinc-600">No quotes in this period.</p>}
      </div>
    </PanelWrapper>
  );
}
