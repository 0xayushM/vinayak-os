"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { FilterableTable, ServerColumn, ServerSort } from "@/components/dashboard/FilterableTable";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { usePurchaseInvoices, type PurchaseInvoiceRow } from "@/hooks/useDashboard";
import { fmtDate, CoverageNote, PAGE_SIZE } from "./_shared";

export function PurchaseInvoicesTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "invoice_date", direction: "desc" });
  const { data, error, isLoading } = usePurchaseInvoices({
    start: range?.start, end: range?.end, search: search || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<PurchaseInvoiceRow>[] = [
    { key: "invoice_date", header: "Date", sortKey: "invoice_date",
      cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.invoice_date)}</span> },
    { key: "invoice_number", header: "Invoice #", cell: (r) => <span className="font-mono text-zinc-400">{r.invoice_number}</span> },
    { key: "vendor_name", header: "Vendor", sortKey: "vendor_name", cell: (r) => <span className="block truncate max-w-[180px]">{r.vendor_name}</span> },
    { key: "item", header: "Item", cell: (r) => <span className="block truncate max-w-[160px]"><span className="font-mono text-zinc-500">{r.item_code}</span>{r.item_name ? ` · ${r.item_name}` : ""}</span> },
    { key: "quantity", header: "Qty", align: "right", sortKey: "quantity", cell: (r) => formatNumber(r.quantity) },
    { key: "line_total", header: "Line total", align: "right", sortKey: "line_total", cell: (r) => formatCurrency(r.line_total, true) },
    { key: "invoice_total", header: "Invoice total", align: "right", sortKey: "invoice_total", cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.invoice_total, true)}</span> },
  ];
  return (
    <PanelWrapper title="Purchase invoices — line items" subtitle="Search, sort and page through every purchase line" meta={data?.meta} error={error}>
      <FilterableTable<PurchaseInvoiceRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.invoice_number}-${r.item_code ?? ""}-${r.line_total}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search vendor, invoice #, item…" emptyMessage="No purchase invoices match these filters."
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Sales order line items.
