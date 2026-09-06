"use client";

import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency } from "@/lib/utils/cn";
import { useCashMovement } from "@/hooks/useDashboard";
import { tooltipStyle, fmt } from "./_shared";

export function CashMovementPanel() {
  const { data, error, isLoading } = useCashMovement(12);
  const d = data?.data;
  const months = d?.months ?? [];
  const net = d?.net ?? 0;
  return (
    <PanelWrapper title="Cash Movement" subtitle="Money in vs out, monthly"
      meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-4 pt-1">
        <div className="grid grid-cols-3 gap-4">
          <KpiCard label="Money in" value={formatCurrency(d?.total_in ?? 0, true)} accent="emerald" sub="sales (goods)" />
          <KpiCard label="Money out" value={formatCurrency(d?.total_out ?? 0, true)} accent="red" sub="purchase spend" />
          <KpiCard label="Net" value={formatCurrency(net, true)}
            accent={net >= 0 ? "blue" : "red"} sub="in − out" />
        </div>
        <ResponsiveContainer width="100%" height={150}>
          <BarChart data={months} margin={{ top: 6, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(192,132,87,0.08)" vertical={false} />
            <XAxis dataKey="month" tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} minTickGap={8} />
            <YAxis tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
            <Tooltip {...tooltipStyle} formatter={fmt("Net")} />
            <Bar dataKey="net" radius={[3, 3, 0, 0]}>
              {months.map((m) => <Cell key={m.month} fill={m.net >= 0 ? "#4ea36a" : "#c0564a"} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </PanelWrapper>
  );
}

/** Searchable per-customer finance lookup — the dynamic drill-down. */
