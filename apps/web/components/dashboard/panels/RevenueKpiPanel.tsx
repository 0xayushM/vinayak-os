"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useRevenueSummary } from "@/hooks/useDashboard";
import { toRangeOpts, rangeSubtitle, CoverageNote } from "./_shared";

export function RevenueKpiPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useRevenueSummary(toRangeOpts(range));
  const d = data?.data;
  return (
    <PanelWrapper
      title="Revenue Overview"
      subtitle={rangeSubtitle(range)}
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="grid grid-cols-2 gap-4 pt-2">
        <KpiCard label="Revenue · goods value" value={formatCurrency(d?.period_total_goods ?? d?.period_total ?? 0, true)} accent="blue" sub={`${formatNumber(d?.invoice_count ?? 0)} invoices`} />
        <KpiCard label="Revenue · invoice total" value={formatCurrency(d?.period_total_invoiced ?? 0, true)} accent="emerald" sub="incl. tax / freight" />
        <KpiCard label="Avg / Invoice" value={formatCurrency(d?.avg_invoice_value ?? 0, true)} accent="violet" sub="per printed invoice (incl. tax)" />
        <KpiCard label="Monthly Avg (12mo)" value={formatCurrency(d?.monthly_avg ?? 0, true)} accent="amber" sub={`invoiced ${formatCurrency(d?.monthly_avg_invoiced ?? 0, true)}`} />
        {/* <KpiCard label={`YTD ${d?.ytd_year ?? ""} · goods`} value={formatCurrency(d?.ytd_total ?? 0, true)} accent="blue" sub={`${formatNumber(d?.customer_count ?? 0)} customers`} />
        <KpiCard label={`YTD ${d?.ytd_year ?? ""} · invoiced`} value={formatCurrency(d?.ytd_invoiced ?? 0, true)} accent="emerald" /> */}
      </div>
      {/* <p className="text-[10.5px] text-zinc-600 pt-2">
        Goods value = sum of line items (ex-tax). Invoice total = printed invoice grand total (incl. tax/freight).
      </p> */}
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Daily revenue line/area chart — the analytics centerpiece.
