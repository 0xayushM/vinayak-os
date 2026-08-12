"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { DataTable } from "@/components/dashboard/DataTable";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useTopSkus } from "@/hooks/useDashboard";
import { toRangeOpts } from "./_shared";

export function TopSkusTablePanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useTopSkus(toRangeOpts(range));
  const skus = data?.data?.skus ?? [];
  type Sku = (typeof skus)[number];
  return (
    <PanelWrapper title="Top SKUs — detail" subtitle="Quantity & revenue" meta={data?.meta} loading={isLoading} error={error}>
      <DataTable<Sku>
        rows={skus}
        rowKey={(s) => s.sku_code}
        emptyMessage="No SKU sales in this period."
        initialSort={{ key: "revenue", dir: "desc" }}
        columns={[
          { key: "sku_code", header: "SKU", sortValue: (s) => s.sku_code,
            cell: (s) => <span className="font-mono text-zinc-400">{s.sku_code}</span> },
          { key: "item_name", header: "Name", sortValue: (s) => s.item_name ?? "",
            cell: (s) => <span className="block truncate max-w-[260px]">{s.item_name}</span> },
          { key: "qty_sold", header: "Qty sold", align: "right", sortValue: (s) => s.qty_sold,
            cell: (s) => formatNumber(s.qty_sold) },
          { key: "revenue", header: "Revenue", align: "right", sortValue: (s) => s.revenue,
            cell: (s) => <span className="text-[#F2DEC8]/90">{formatCurrency(s.revenue, true)}</span> },
        ]}
      />
    </PanelWrapper>
  );
}
