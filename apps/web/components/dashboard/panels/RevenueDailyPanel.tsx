"use client";

import { Area, AreaChart, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useRevenueDaily } from "@/hooks/useDashboard";
import { toRangeOpts, rangeSubtitle, fmtDate, CoverageNote, BLUE, tooltipStyle, fmt } from "./_shared";

export function RevenueDailyPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useRevenueDaily(toRangeOpts(range));
  const days = data?.data?.days ?? [];
  return (
    <PanelWrapper
      title="Daily Revenue"
      subtitle={rangeSubtitle(range)}
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={days} margin={{ top: 6, right: 8, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#C08457" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#C08457" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(192,132,87,0.08)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} minTickGap={32}
            tickFormatter={(v) => { const d = new Date(v + "T00:00:00"); return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }); }} />
          <YAxis tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
          <Tooltip {...tooltipStyle} formatter={fmt("Revenue")} labelFormatter={(l) => fmtDate(String(l))} />
          <Area type="monotone" dataKey="revenue" stroke={BLUE} strokeWidth={2} fill="url(#revFill)" />
        </AreaChart>
      </ResponsiveContainer>
      <CoverageNote from={data?.data?.window_from} to={data?.data?.window_to} />
    </PanelWrapper>
  );
}
