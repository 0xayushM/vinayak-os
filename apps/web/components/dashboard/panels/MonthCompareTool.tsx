"use client";

import { useState } from "react";
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { useMonthlySales } from "@/hooks/useDashboard";
import { tooltipStyle, fmt, selectCls } from "./_shared";

export function MonthCompareTool() {
  const { data, error, isLoading } = useMonthlySales(12);
  const months = data?.data?.months ?? [];
  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");
  const effA = a || (months.length >= 2 ? months[months.length - 2].month : "");
  const effB = b || (months.length >= 1 ? months[months.length - 1].month : "");
  const rowA = months.find((m) => m.month === effA);
  const rowB = months.find((m) => m.month === effB);
  const va = rowA?.revenue ?? 0;
  const vb = rowB?.revenue ?? 0;
  // Change is always chronological (later month vs earlier), independent of which
  // dropdown holds which — so Feb↔Apr and Apr↔Feb give the same answer. Month
  // strings are "YYYY-MM", so a string compare is a date compare.
  const earlier = effA <= effB ? effA : effB;
  const later = effA <= effB ? effB : effA;
  const vEarlier = (earlier === effA ? va : vb);
  const vLater = (later === effA ? va : vb);
  const delta = vLater - vEarlier;
  const pct = vEarlier ? (delta / vEarlier) * 100 : null;
  return (
    <PanelWrapper title="Compare Months" subtitle="Pick any two months to compare sales"
      meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-4 pt-1">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-zinc-400">Compare</span>
          <select value={effA} onChange={(e) => setA(e.target.value)} className={selectCls}>
            {months.map((m) => <option key={m.month} value={m.month}>{m.month}</option>)}
          </select>
          <span className="text-zinc-500">with</span>
          <select value={effB} onChange={(e) => setB(e.target.value)} className={selectCls}>
            {months.map((m) => <option key={m.month} value={m.month}>{m.month}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <KpiCard label={effA || "Month A"} value={formatCurrency(va, true)} accent="blue"
            sub={`${formatNumber(rowA?.invoice_count ?? 0)} invoices`} />
          <KpiCard label={effB || "Month B"} value={formatCurrency(vb, true)} accent="blue"
            sub={`${formatNumber(rowB?.invoice_count ?? 0)} invoices`} />
          <KpiCard label={`Change (${earlier} → ${later})`}
            value={`${delta >= 0 ? "+" : ""}${formatCurrency(delta, true)}`}
            accent={delta >= 0 ? "emerald" : "red"}
            sub={pct == null ? "—" : `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% vs ${earlier}`} />
        </div>
        <ResponsiveContainer width="100%" height={150}>
          <BarChart data={months} margin={{ top: 6, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(192,132,87,0.08)" vertical={false} />
            <XAxis dataKey="month" tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} minTickGap={8} />
            <YAxis tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
            <Tooltip {...tooltipStyle} formatter={fmt("Sales")} />
            <Bar dataKey="revenue" radius={[3, 3, 0, 0]}>
              {months.map((m) => (
                <Cell key={m.month} fill={m.month === effA || m.month === effB ? "#F2DEC8" : "rgba(192,132,87,0.35)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </PanelWrapper>
  );
}

/** Ranked chase list — deterministic, paginated. */
