"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { DataTable } from "@/components/dashboard/DataTable";
import { formatCurrency } from "@/lib/utils/cn";
import { useOpenPOs } from "@/hooks/useDashboard";

export function OpenPosTablePanel() {
  const { data, error, isLoading } = useOpenPOs();
  const rows = data?.data?.by_vendor ?? [];
  type Row = (typeof rows)[number];
  return (
    <PanelWrapper title="Open POs by vendor — detail" subtitle="Outstanding PO value per vendor" meta={data?.meta} loading={isLoading} error={error}>
      <DataTable<Row>
        rows={rows}
        rowKey={(r) => r.vendor_name}
        emptyMessage="No open purchase orders."
        initialSort={{ key: "value", dir: "desc" }}
        columns={[
          { key: "vendor_name", header: "Vendor", sortValue: (r) => r.vendor_name ?? "",
            cell: (r) => <span className="block truncate max-w-[280px]">{r.vendor_name}</span> },
          { key: "value", header: "Open value", align: "right", sortValue: (r) => r.value,
            cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.value, true)}</span> },
        ]}
      />
    </PanelWrapper>
  );
}
