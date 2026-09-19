"use client";

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useCustomerConcentration } from "@/hooks/useDashboard";
import { toRangeOpts, COLORS, tooltipStyle, fmt } from "./_shared";

export function CustomerConcentrationPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useCustomerConcentration(toRangeOpts(range));
  const slices = data?.data?.slices ?? [];
  const named = slices.filter((s) => s.name !== "Others");
  const topShare = named.reduce((sum, s) => sum + s.pct, 0);
  return (
    <PanelWrapper title="Customer Concentration" subtitle="Top 5 + Others" meta={data?.meta} loading={isLoading} error={error}>
      {slices.length === 0 ? (
        <p className="text-xs text-zinc-600 pt-3">No customer revenue in this period.</p>
      ) : (
        <>
          <div className="flex items-end justify-between gap-3 pt-1">
            <div>
              <p className="text-[10.5px] font-medium text-[#7a6055] uppercase tracking-[0.08em]">Top {named.length} share</p>
              <p className="text-[26px] leading-none font-semibold tracking-tight tabular-nums text-[#F2DEC8] mt-1.5">{topShare.toFixed(1)}%</p>
            </div>
            <p className="text-[11px] text-[#7a6055] text-right">of revenue</p>
          </div>
          <div className="flex-1 flex items-center gap-4 pt-4">
            <div className="w-[112px] h-[112px] shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={slices} dataKey="revenue" cx="50%" cy="50%" innerRadius={34} outerRadius={54} paddingAngle={2}>
                    {slices.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip {...tooltipStyle} formatter={fmt("Revenue")} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 min-w-0 space-y-2">
              {slices.map((s, i) => (
                <div key={`${s.name}-${i}`} className="flex items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                    <span title={s.name} className="text-[#F2DEC8]/75 truncate">{s.name}</span>
                  </div>
                  <span className="text-zinc-500 tabular-nums shrink-0">{s.pct.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </PanelWrapper>
  );
}
