"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { FilterableTable, ServerColumn, ServerSort } from "@/components/dashboard/FilterableTable";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useSalesInvoices, type SalesInvoiceRow } from "@/hooks/useDashboard";
import { fmtDate, CoverageNote, StatusBadge, PAGE_SIZE } from "./_shared";

export function SalesInvoicesTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "invoice_date", direction: "desc" });

  const { data, error, isLoading } = useSalesInvoices({
    start: range?.start, end: range?.end, search: search || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const rows = d?.rows ?? [];

  const columns: ServerColumn<SalesInvoiceRow>[] = [
    { key: "invoice_date", header: "Date", sortKey: "invoice_date",
      cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.invoice_date)}</span> },
    { key: "invoice_number", header: "Invoice #",
      cell: (r) => <span className="font-mono text-zinc-400">{r.invoice_number}</span> },
    { key: "customer_name", header: "Customer", sortKey: "customer_name",
      cell: (r) => <span className="block truncate max-w-[180px]">{r.customer_name}</span> },
    { key: "sku", header: "SKU",
      cell: (r) => <span className="block truncate max-w-[160px]"><span className="font-mono text-zinc-500">{r.sku_code}</span>{r.sku_name ? ` · ${r.sku_name}` : ""}</span> },
    { key: "quantity", header: "Qty", align: "right", sortKey: "quantity",
      cell: (r) => formatNumber(r.quantity) },
    { key: "line_total", header: "Line total", align: "right", sortKey: "line_total",
      cell: (r) => formatCurrency(r.line_total, true) },
    { key: "invoice_total", header: "Invoice total", align: "right", sortKey: "invoice_total",
      cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.invoice_total, true)}</span> },
    { key: "payment_status", header: "Status", align: "center",
      cell: (r) => <StatusBadge status={r.payment_status} /> },
  ];

  return (
    <PanelWrapper title="Sales invoices — line items" subtitle="Search, sort and page through every invoice line" meta={data?.meta} error={error}>
      <FilterableTable<SalesInvoiceRow>
        columns={columns}
        rows={rows}
        rowKey={(r) => `${r.invoice_number}-${r.sku_code ?? ""}-${r.line_total}`}
        page={d?.page ?? 0}
        pageCount={d?.page_count ?? 1}
        filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE}
        sort={sort}
        loading={isLoading}
        search={search}
        onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort}
        onPageChange={setPage}
        searchPlaceholder="Search customer, invoice #, SKU…"
        emptyMessage="No invoices match these filters."
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// AR invoice line items — searchable, bucket/overdue filterable, server-paginated.
