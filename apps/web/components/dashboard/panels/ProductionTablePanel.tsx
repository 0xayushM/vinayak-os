"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatNumber } from "@/lib/utils/cn";
import { FilterableTable, ServerColumn, ServerSort } from "@/components/dashboard/FilterableTable";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import { useProductionList, type ProductionRow } from "@/hooks/useDashboard";
import { fmtDate, CoverageNote, StatusBadge, StatusFilter, PAGE_SIZE } from "./_shared";

export function ProductionTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "production_date", direction: "desc" });
  const { data, error, isLoading } = useProductionList({
    start: range?.start, end: range?.end, search: search || undefined, status: status || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<ProductionRow>[] = [
    { key: "production_date", header: "Date", sortKey: "production_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.production_date)}</span> },
    { key: "work_order_number", header: "Work order", sortKey: "work_order_number", cell: (r) => <span className="font-mono text-zinc-400">{r.work_order_number}</span> },
    { key: "sku", header: "SKU", cell: (r) => <span className="block truncate max-w-[150px]"><span className="font-mono text-zinc-500">{r.sku_code}</span>{r.sku_name ? ` · ${r.sku_name}` : ""}</span> },
    { key: "process_name", header: "Process", cell: (r) => <span className="block truncate max-w-[130px]">{r.process_name}</span> },
    { key: "planned_qty", header: "Planned", align: "right", sortKey: "planned_qty", cell: (r) => formatNumber(r.planned_qty) },
    { key: "produced_qty", header: "Produced", align: "right", sortKey: "produced_qty", cell: (r) => <span className="text-[#F2DEC8]/90">{formatNumber(r.produced_qty)}</span> },
    { key: "rejected_qty", header: "Rejected", align: "right", sortKey: "rejected_qty", cell: (r) => <span className={r.rejected_qty > 0 ? "text-amber-300" : "text-zinc-400"}>{formatNumber(r.rejected_qty)}</span> },
    { key: "status", header: "Status", align: "center", cell: (r) => <StatusBadge status={r.status} /> },
  ];
  return (
    <PanelWrapper title="Production — process records" subtitle="Work orders, output and rejects" meta={data?.meta} error={error}>
      <FilterableTable<ProductionRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.work_order_number}-${r.process_name ?? ""}-${r.produced_qty}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search work order, SKU, process…" emptyMessage="No production records match these filters."
        toolbar={<StatusFilter value={status} options={["Planned", "In Progress", "Completed", "On Hold"]} onChange={(v) => { setStatus(v); setPage(0); }} />}
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Inventory valuation rows (snapshot — no date window).
