"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency } from "@/lib/utils/cn";
import { useFinanceOverview } from "@/hooks/useDashboard";

export function FinanceOverviewPanel() {
  const { data, error, isLoading } = useFinanceOverview();
  const d = data?.data;
  return (
    <PanelWrapper title="Finance Snapshot" subtitle="The headline numbers, computed — no AI"
      meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 pt-1">
        <KpiCard label="Revenue (goods)" value={formatCurrency(d?.revenue_goods ?? 0, true)} accent="blue" />
        <KpiCard label="Outstanding" value={formatCurrency(d?.outstanding ?? 0, true)} accent="blue" />
        <KpiCard label="Overdue" value={formatCurrency(d?.overdue ?? 0, true)} accent="red"
          sub={`${(d?.overdue_pct ?? 0).toFixed(1)}% of AR`} />
        <KpiCard label="DSO" value={d?.dso_days != null ? `${d.dso_days} days` : "—"} accent="amber"
          sub="days to get paid" />
      </div>
    </PanelWrapper>
  );
}

/** Dynamic month-vs-month comparison — pick any two months. */
