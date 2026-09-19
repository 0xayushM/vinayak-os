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
  const best = months.reduce<(typeof months)[number] | null>((b, m) => (!b || m.revenue > b.revenue ? m : b), null);
  const latest = months[months.length - 1];
  return (
    <PanelWrapper title="Revenue Trend" subtitle={rangeSubtitle(range, "Monthly · all data")} meta={data?.meta} loading={isLoading} error={error}>
      <div className="flex-1 min-h-[160px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={months} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(192,132,87,0.08)" vertical={false} />
            <XAxis dataKey="month" tick={{ fill: "#C4977A", fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#C4977A", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
            <Tooltip {...tooltipStyle} formatter={fmt("Revenue")} />
            <Bar dataKey="revenue" fill={BLUE} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {best && latest && (
        <div className="flex justify-between gap-3 pt-3 mt-3 border-t border-white/[0.05] text-[11px]">
          <div className="min-w-0">
            <p className="text-zinc-600">Best month</p>
            <p className="text-[#F2DEC8]/80 tabular-nums truncate">{best.month} · {formatCurrency(best.revenue, true)}</p>
          </div>
          <div className="min-w-0 text-right">
            <p className="text-zinc-600">Latest</p>
            <p className="text-[#F2DEC8]/80 tabular-nums truncate">{latest.month} · {formatCurrency(latest.revenue, true)}</p>
          </div>
        </div>
      )}
    </PanelWrapper>
  );
}
