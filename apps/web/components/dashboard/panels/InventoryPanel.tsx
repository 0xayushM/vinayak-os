"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { useInventorySummary, useInventoryByCategory } from "@/hooks/useDashboard";
import { GREEN, tooltipStyle, fmt } from "./_shared";

export function InventoryPanel() {
  const { data: sumData, error: sumError, isLoading: sumLoading } = useInventorySummary();
  const { data: catData } = useInventoryByCategory();
  const d          = sumData?.data;
  const categories = catData?.data?.categories ?? [];
  return (
    <PanelWrapper title="Inventory" subtitle="Stock valuation" meta={sumData?.meta} loading={sumLoading} error={sumError}>
      <div className="space-y-3 pt-1">
        <div className="grid grid-cols-2 gap-3">
          <KpiCard label="Total Value" value={formatCurrency(d?.total_value ?? 0, true)} accent="blue" />
          <KpiCard label="SKUs Tracked" value={formatNumber(d?.total_skus ?? 0)} accent="emerald" />
          <KpiCard label="Low Stock" value={formatNumber(d?.low_stock_count ?? 0)} accent="amber" />
          <KpiCard label="Zero Stock" value={formatNumber(d?.zero_stock_count ?? 0)} accent="red" />
        </div>
        {categories.length > 0 && (
          <ResponsiveContainer width="100%" height={90}>
            <BarChart data={categories.slice(0, 6)} margin={{ top: 0, right: 4, left: -20, bottom: 0 }}>
              <XAxis dataKey="category" tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
              <Tooltip {...tooltipStyle} formatter={fmt("Value")} />
              <Bar dataKey="value" fill={GREEN} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </PanelWrapper>
  );
}

// Inventory category breakdown table (Inventory page).
