"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { FilterableTable, ServerColumn, ServerSort } from "@/components/dashboard/FilterableTable";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { usePurchaseOrders, type PurchaseOrderRow } from "@/hooks/useDashboard";
import { fmtDate, CoverageNote, StatusBadge, StatusFilter, PAGE_SIZE } from "./_shared";

export function PurchaseOrdersTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "po_date", direction: "desc" });
  const { data, error, isLoading } = usePurchaseOrders({
    start: range?.start, end: range?.end, search: search || undefined, status: status || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<PurchaseOrderRow>[] = [
    { key: "po_date", header: "PO date", sortKey: "po_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.po_date)}</span> },
    { key: "po_number", header: "PO #", cell: (r) => <span className="font-mono text-zinc-400">{r.po_number}</span> },
    { key: "vendor_name", header: "Vendor", sortKey: "vendor_name", cell: (r) => <span className="block truncate max-w-[160px]">{r.vendor_name}</span> },
    { key: "item", header: "Item", cell: (r) => <span className="block truncate max-w-[150px]"><span className="font-mono text-zinc-500">{r.item_code}</span>{r.item_name ? ` · ${r.item_name}` : ""}</span> },
    { key: "pending_qty", header: "Pending", align: "right", sortKey: "pending_qty", cell: (r) => formatNumber(r.pending_qty) },
    { key: "po_value", header: "Value", align: "right", sortKey: "po_value", cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.po_value, true)}</span> },
    { key: "expected_date", header: "Expected", sortKey: "expected_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.expected_date)}</span> },
    { key: "status", header: "Status", align: "center", cell: (r) => <StatusBadge status={r.status} /> },
  ];
  return (
    <PanelWrapper title="Purchase orders — line items" subtitle="Open and historical PO book" meta={data?.meta} error={error}>
      <FilterableTable<PurchaseOrderRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.po_number}-${r.item_code ?? ""}-${r.po_value}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search vendor, PO #, item…" emptyMessage="No purchase orders match these filters."
        toolbar={<StatusFilter value={status} options={["Open", "Partial", "Closed", "Cancelled"]} onChange={(v) => { setStatus(v); setPage(0); }} />}
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Production process records.
