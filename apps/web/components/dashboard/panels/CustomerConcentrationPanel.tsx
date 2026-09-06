"use client";

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useCustomerConcentration } from "@/hooks/useDashboard";
import { toRangeOpts, COLORS, tooltipStyle, fmt } from "./_shared";

export function CustomerConcentrationPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useCustomerConcentration(toRangeOpts(range));
  const slices = data?.data?.slices ?? [];
  return (
    <PanelWrapper title="Customer Concentration" subtitle="Top 5 + Others" meta={data?.meta} loading={isLoading} error={error}>
      <div className="flex items-center gap-4">
        <ResponsiveContainer width={120} height={120}>
          <PieChart>
            <Pie data={slices} dataKey="revenue" cx="50%" cy="50%" innerRadius={30} outerRadius={52} paddingAngle={2}>
              {slices.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="transparent" />
              ))}
            </Pie>
            <Tooltip {...tooltipStyle} formatter={fmt("Revenue")} />
          </PieChart>
        </ResponsiveContainer>
        <div className="flex-1 space-y-1.5">
          {slices.map((s, i) => (
            <div key={`${s.name}-${i}`} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                <span title={s.name} className="text-[#F2DEC8]/75 truncate max-w-[150px]">{s.name}</span>
              </div>
              <span className="text-zinc-500 tabular-nums">{s.pct.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
    </PanelWrapper>
  );
}
