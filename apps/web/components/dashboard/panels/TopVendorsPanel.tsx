"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useTopVendors } from "@/hooks/useDashboard";
import { toRangeOpts, rangeSubtitle } from "./_shared";

export function TopVendorsPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useTopVendors(toRangeOpts(range));
  const vendors = data?.data?.vendors ?? [];
  const max = vendors[0]?.spend ?? 1;
  return (
    <PanelWrapper title="Top Vendors by Spend" subtitle={rangeSubtitle(range)} meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-2 pt-1">
        {vendors.slice(0, 8).map((v) => (
          <div key={v.vendor_name} className="flex items-center gap-2 text-xs">
            <span title={v.vendor_name} className="text-zinc-400 w-40 shrink-0 truncate">{v.vendor_name}</span>
            <div className="flex-1 bg-white/[0.06] rounded-full h-1.5 overflow-hidden">
              <div className="h-full rounded-full bg-amber-500" style={{ width: `${(v.spend / max) * 100}%` }} />
            </div>
            <span className="text-[#F2DEC8]/75 tabular-nums w-16 text-right shrink-0">{formatCurrency(v.spend, true)}</span>
          </div>
        ))}
        {vendors.length === 0 && <p className="text-xs text-zinc-600 pt-3">No vendor spend in this period.</p>}
      </div>
    </PanelWrapper>
  );
}
