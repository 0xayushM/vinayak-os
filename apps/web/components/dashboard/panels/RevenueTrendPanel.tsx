"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useRevenueTrend } from "@/hooks/useDashboard";
import { toRangeOpts, rangeSubtitle, BLUE, tooltipStyle, fmt } from "./_shared";

export function RevenueTrendPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useRevenueTrend(toRangeOpts(range));
  const months = data?.data?.months ?? [];
  return (
    <PanelWrapper title="Revenue Trend" subtitle={rangeSubtitle(range, "Monthly · all data")} meta={data?.meta} loading={isLoading} error={error}>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={months} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(192,132,87,0.08)" vertical={false} />
          <XAxis dataKey="month" tick={{ fill: "#C4977A", fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#C4977A", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
          <Tooltip {...tooltipStyle} formatter={fmt("Revenue")} />
          <Bar dataKey="revenue" fill={BLUE} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </PanelWrapper>
  );
}
