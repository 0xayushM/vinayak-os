"use client";

import { useState } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { FilterableTable, ServerColumn, ServerSort } from "@/components/dashboard/FilterableTable";
import { useInventoryList, type InventoryRow } from "@/hooks/useDashboard";
import { PAGE_SIZE } from "./_shared";

export function InventoryTablePanel() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "total_value", direction: "desc" });
  const { data, error, isLoading } = useInventoryList({
    search: search || undefined, page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<InventoryRow>[] = [
    { key: "sku_code", header: "SKU", cell: (r) => <span className="font-mono text-zinc-400">{r.sku_code}</span> },
    { key: "sku_name", header: "Name", sortKey: "sku_name", cell: (r) => <span className="block truncate max-w-[200px]">{r.sku_name}</span> },
    { key: "category", header: "Category", sortKey: "category", cell: (r) => <span className="text-zinc-400">{r.category ?? "—"}</span> },
    { key: "warehouse", header: "Warehouse", cell: (r) => <span className="text-zinc-400 truncate max-w-[120px] block">{r.warehouse ?? "—"}</span> },
    { key: "quantity", header: "Qty", align: "right", sortKey: "quantity", cell: (r) => <span className={r.is_negative_stock ? "text-red-400" : ""}>{formatNumber(r.quantity)}</span> },
    { key: "unit_cost", header: "Unit cost", align: "right", sortKey: "unit_cost", cell: (r) => formatCurrency(r.unit_cost, true) },
    { key: "total_value", header: "Value", align: "right", sortKey: "total_value", cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.total_value, true)}</span> },
  ];
  return (
    <PanelWrapper title="Inventory — valuation detail" subtitle="Every SKU, searchable and sortable" meta={data?.meta} error={error}>
      <FilterableTable<InventoryRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.sku_code}-${r.warehouse ?? ""}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search SKU, name, category, warehouse…" emptyMessage="No stock rows match these filters."
      />
    </PanelWrapper>
  );
}

// ── Finance: dynamic, deterministic (non-AI) tools ────────────────────────────
// These are the finance-specific tools that don't live on any other page. They
// double as the read layer the Brain queries to answer finance questions.
