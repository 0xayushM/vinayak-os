"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { useInventoryByCategory } from "@/hooks/useDashboard";

export function InventoryCategoryTablePanel() {
  const { data, error, isLoading } = useInventoryByCategory();
  const cats = data?.data?.categories ?? [];
  return (
    <PanelWrapper title="Inventory by category — detail" subtitle="Value & SKU count per category" meta={data?.meta} loading={isLoading} error={error}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-zinc-500 border-b border-white/[0.07]">
              <th className="text-left font-medium py-2">Category</th>
              <th className="text-right font-medium py-2">Value</th>
              <th className="text-right font-medium py-2">SKUs</th>
            </tr>
          </thead>
          <tbody>
            {cats.map((c) => (
              <tr key={c.category} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                <td className="py-2 text-[#F2DEC8]/75">{c.category}</td>
                <td className="py-2 text-right text-[#F2DEC8]/90 tabular-nums">{formatCurrency(c.value, true)}</td>
                <td className="py-2 text-right text-zinc-400 tabular-nums">{formatNumber(c.sku_count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {cats.length === 0 && <p className="text-xs text-zinc-600 pt-3">No inventory categories yet.</p>}
      </div>
    </PanelWrapper>
  );
}
