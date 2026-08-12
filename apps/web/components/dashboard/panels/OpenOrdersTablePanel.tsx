"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { DataTable } from "@/components/dashboard/DataTable";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { useOpenOrders } from "@/hooks/useDashboard";

export function OpenOrdersTablePanel() {
  const { data, error, isLoading } = useOpenOrders();
  const rows = data?.data?.by_status ?? [];
  type Row = (typeof rows)[number];
  return (
    <PanelWrapper title="Orders by status — detail" subtitle="Count & value per status" meta={data?.meta} loading={isLoading} error={error}>
      <DataTable<Row>
        rows={rows}
        rowKey={(r) => r.status}
        emptyMessage="No open orders."
        initialSort={{ key: "value", dir: "desc" }}
        columns={[
          { key: "status", header: "Status", sortValue: (r) => r.status, cell: (r) => r.status },
          { key: "count", header: "Orders", align: "right", sortValue: (r) => r.count, cell: (r) => formatNumber(r.count) },
          { key: "value", header: "Value", align: "right", sortValue: (r) => r.value,
            cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.value, true)}</span> },
        ]}
      />
    </PanelWrapper>
  );
}

// Open POs by-vendor detail table (POs page).
