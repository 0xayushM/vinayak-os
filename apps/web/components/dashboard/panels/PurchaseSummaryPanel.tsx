"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { usePurchaseSummary } from "@/hooks/useDashboard";
import { toRangeOpts, rangeSubtitle } from "./_shared";

export function PurchaseSummaryPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = usePurchaseSummary(toRangeOpts(range));
  const d = data?.data;
  return (
    <PanelWrapper title="Purchases" subtitle={rangeSubtitle(range)} meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-2 gap-4 pt-2">
        <KpiCard label="Spend · goods value" value={formatCurrency(d?.period_total_goods ?? d?.period_total ?? 0, true)} accent="amber" sub={`${d?.invoice_count ?? 0} invoices`} />
        <KpiCard label="Spend · invoice total" value={formatCurrency(d?.period_total_invoiced ?? 0, true)} accent="emerald" sub="incl. tax / freight" />
        <KpiCard label="Monthly Avg" value={formatCurrency(d?.monthly_avg ?? 0, true)} accent="blue" sub={`invoiced ${formatCurrency(d?.monthly_avg_invoiced ?? 0, true)}`} />
        <KpiCard label="Active Vendors" value={formatNumber(d?.vendor_count ?? 0)} accent="violet" />
      </div>
      <p className="text-[10.5px] text-zinc-600 pt-2">
        Goods value = sum of line items (ex-tax). Invoice total = printed grand total (incl. tax/freight).
      </p>
    </PanelWrapper>
  );
}
