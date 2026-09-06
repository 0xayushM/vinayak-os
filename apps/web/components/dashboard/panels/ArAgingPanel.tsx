"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency } from "@/lib/utils/cn";
import { useArSummary } from "@/hooks/useDashboard";
import { AMBER, tooltipStyle, fmt } from "./_shared";

export function ArAgingPanel() {
  const { data, error, isLoading } = useArSummary();
  const d = data?.data;
  const buckets = d?.buckets ?? [];
  return (
    <PanelWrapper title="AR Aging" subtitle="Outstanding receivables" meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-3 pt-1">
        <div className="grid grid-cols-2 gap-4">
          <KpiCard label="Total Outstanding" value={formatCurrency(d?.total_outstanding ?? 0, true)} accent="blue" />
          <KpiCard label="Overdue" value={formatCurrency(d?.overdue_amount ?? 0, true)} accent="red" sub={`${((d?.overdue_pct ?? 0) * 100).toFixed(1)}% of total`} />
        </div>
        <ResponsiveContainer width="100%" height={120}>
          <BarChart data={buckets} layout="vertical" margin={{ left: 0, right: 8, top: 0, bottom: 0 }}>
            <XAxis type="number" tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
            <YAxis type="category" dataKey="bucket" tick={{ fill: "#C4977A", fontSize: 10 }} axisLine={false} tickLine={false} width={60} />
            <Tooltip {...tooltipStyle} formatter={fmt("Amount")} />
            <Bar dataKey="amount" fill={AMBER} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </PanelWrapper>
  );
}

// AR aging bucket breakdown table (AR page).
