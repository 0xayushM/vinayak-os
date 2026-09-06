"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { FilterableTable, ServerColumn, ServerSort } from "@/components/dashboard/FilterableTable";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useSalesOrders, type SalesOrderRow } from "@/hooks/useDashboard";
import { fmtDate, CoverageNote, StatusBadge, StatusFilter, PAGE_SIZE } from "./_shared";

export function SalesOrdersTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "order_date", direction: "desc" });
  const { data, error, isLoading } = useSalesOrders({
    start: range?.start, end: range?.end, search: search || undefined, status: status || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<SalesOrderRow>[] = [
    { key: "order_date", header: "Ordered", sortKey: "order_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.order_date)}</span> },
    { key: "order_number", header: "Order #", cell: (r) => <span className="font-mono text-zinc-400">{r.order_number}</span> },
    { key: "customer_name", header: "Customer", sortKey: "customer_name", cell: (r) => <span className="block truncate max-w-[160px]">{r.customer_name}</span> },
    { key: "sku", header: "SKU", cell: (r) => <span className="block truncate max-w-[150px]"><span className="font-mono text-zinc-500">{r.sku_code}</span>{r.sku_name ? ` · ${r.sku_name}` : ""}</span> },
    { key: "pending_qty", header: "Pending", align: "right", sortKey: "pending_qty", cell: (r) => formatNumber(r.pending_qty) },
    { key: "order_value", header: "Value", align: "right", sortKey: "order_value", cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.order_value, true)}</span> },
    { key: "delivery_date", header: "Delivery", sortKey: "delivery_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.delivery_date)}</span> },
    { key: "status", header: "Status", align: "center", cell: (r) => <StatusBadge status={r.status} /> },
  ];
  return (
    <PanelWrapper title="Sales orders — line items" subtitle="Open and historical order book" meta={data?.meta} error={error}>
      <FilterableTable<SalesOrderRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.order_number}-${r.sku_code ?? ""}-${r.order_value}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search customer, order #, SKU…" emptyMessage="No sales orders match these filters."
        toolbar={<StatusFilter value={status} options={["Open", "Partial", "Closed", "Cancelled"]} onChange={(v) => { setStatus(v); setPage(0); }} />}
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Purchase order line items.
