"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency } from "@/lib/utils/cn";
import { FilterableTable, ServerColumn, ServerSort } from "@/components/dashboard/FilterableTable";
import { useArInvoices, type ArInvoiceRow } from "@/hooks/useDashboard";
import { fmtDate, PAGE_SIZE } from "./_shared";

export function ArInvoicesTablePanel() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [sort, setSort] = useState<ServerSort>({ sort: "outstanding_amount", direction: "desc" });

  const { data, error, isLoading } = useArInvoices({
    search: search || undefined, overdue_only: overdueOnly,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const rows = d?.rows ?? [];

  const columns: ServerColumn<ArInvoiceRow>[] = [
    { key: "customer_name", header: "Customer", sortKey: "customer_name",
      cell: (r) => <span className="block truncate max-w-[200px]">{r.customer_name}</span> },
    { key: "invoice_number", header: "Invoice #",
      cell: (r) => <span className="font-mono text-zinc-400">{r.invoice_number}</span> },
    { key: "invoice_date", header: "Invoiced", sortKey: "invoice_date",
      cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.invoice_date)}</span> },
    { key: "due_date", header: "Due", sortKey: "due_date",
      cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.due_date)}</span> },
    { key: "invoice_amount", header: "Amount", align: "right", sortKey: "invoice_amount",
      cell: (r) => formatCurrency(r.invoice_amount, true) },
    { key: "outstanding_amount", header: "Outstanding", align: "right", sortKey: "outstanding_amount",
      cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.outstanding_amount, true)}</span> },
    { key: "days_overdue", header: "Overdue", align: "right", sortKey: "days_overdue",
      cell: (r) => r.days_overdue == null ? "—" : <span className={r.days_overdue > 0 ? "text-amber-300" : "text-zinc-400"}>{r.days_overdue}d</span> },
    { key: "aging_bucket", header: "Bucket", align: "center",
      cell: (r) => <span className="text-zinc-400">{r.aging_bucket ?? "—"}</span> },
  ];

  return (
    <PanelWrapper title="AR invoices — line items" subtitle="Outstanding receivables, invoice by invoice" meta={data?.meta} error={error}>
      <FilterableTable<ArInvoiceRow>
        columns={columns}
        rows={rows}
        rowKey={(r) => `${r.invoice_number}-${r.customer_name}`}
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
        searchPlaceholder="Search customer or invoice #…"
        emptyMessage="No receivables match these filters."
        toolbar={
          <button
            onClick={() => { setOverdueOnly((v) => !v); setPage(0); }}
            className={`text-[11px] rounded-lg px-2.5 py-2 border transition-colors shrink-0 ${
              overdueOnly
                ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
                : "text-zinc-400 border-white/[0.08] hover:text-[#F2DEC8]/90"
            }`}
          >
            Overdue only
          </button>
        }
      />
    </PanelWrapper>
  );
}

// Status-filter dropdown shared by order/PO/production tables.
