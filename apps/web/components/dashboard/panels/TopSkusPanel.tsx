"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useTopSkus } from "@/hooks/useDashboard";
import { toRangeOpts, rangeSubtitle, CoverageNote } from "./_shared";

export function TopSkusPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useTopSkus(toRangeOpts(range));
  const skus = data?.data?.skus ?? [];
  const max  = skus[0]?.revenue ?? 1;
  return (
    <PanelWrapper title="Top SKUs by Revenue" subtitle={rangeSubtitle(range)} meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-2 pt-1">
        {skus.slice(0, 8).map((s) => (
          <div key={s.sku_code} className="flex items-center gap-2 text-xs">
            <span title={s.sku_code} className="text-zinc-500 font-mono w-24 shrink-0 truncate">{s.sku_code}</span>
            <div className="flex-1 bg-white/[0.06] rounded-full h-1.5 overflow-hidden">
              <div className="h-full rounded-full bg-[#C08457]" style={{ width: `${(s.revenue / max) * 100}%` }} />
            </div>
            <span className="text-[#F2DEC8]/75 tabular-nums w-16 text-right shrink-0">{formatCurrency(s.revenue, true)}</span>
          </div>
        ))}
        {skus.length === 0 && <p className="text-xs text-zinc-600 pt-3">No SKU sales in this period.</p>}
      </div>
      <CoverageNote from={data?.data?.window_from} to={data?.data?.window_to} />
    </PanelWrapper>
  );
}

// Detailed Top-SKU table (used on the SKUs page) — sortable + paginated.
