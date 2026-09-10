"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import { StageFlow, Tabs, SectionHead, type Stage } from "@/components/dashboard/StageFlow";
import {
  InventoryTablePanel, InventoryCategoryTablePanel, ProductionTablePanel,
  ProductionPanel, BomCoveragePanel,
} from "@/components/dashboard/panels";
import { useInventorySummary, useProductionSummary, useBomCoverage } from "@/hooks/useDashboard";
import { formatCurrency } from "@/lib/utils/cn";

/**
 * Stock & making — the middle of both loops, where money is neither cash nor
 * a receivable but goods sitting on a shelf or half-built on the floor.
 *
 * Framed as capital, not as counts: stock value is money that has stopped
 * moving, and the questions are how much of it, how long it has been there,
 * and what is being turned into finished goods.
 */
const TABS = [
  { key: "stock", label: "Stock" },
  { key: "categories", label: "By category" },
  { key: "production", label: "Production" },
];

export default function OperationsPage() {
  const [range, setRange] = useState<DateRange>({});
  const [tab, setTab] = useState("stock");

  const inv = useInventorySummary();
  const prod = useProductionSummary(range.start || range.end ? range : {});
  const bom = useBomCoverage();

  const i = inv.data?.data;
  const p = prod.data?.data;
  const b = bom.data?.data;

  const stages: Stage[] = [
    {
      key: "stock", label: "Capital in stock",
      value: i ? formatCurrency(i.total_value, true) : "—",
      note: i ? `${i.total_skus} SKUs held` : undefined,
      stuck: i?.zero_stock_count
        ? { value: String(i.zero_stock_count), label: "at zero or negative" }
        : undefined,
      loading: inv.isLoading,
    },
    {
      key: "wip", label: "On the floor",
      value: p ? String(p.wip_count) : "—",
      note: p ? "work orders in progress" : undefined,
      loading: prod.isLoading,
    },
    {
      key: "made", label: "Completed",
      value: p ? String(p.completed_count) : "—",
      note: p ? `${p.avg_cycle_days} day average cycle` : undefined,
      loading: prod.isLoading,
    },
    {
      key: "bom", label: "Costable",
      value: b ? `${b.coverage_pct}%` : "—",
      note: b ? `${b.items_with_bom} of ${b.total_items} items have a BOM` : undefined,
      stuck: b?.items_missing_bom
        ? { value: String(b.items_missing_bom), label: "cannot be costed" }
        : undefined,
      loading: bom.isLoading,
    },
  ];

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto w-full animate-rise space-y-5">
      <PageHeader
        title="Stock &amp; making"
        subtitle="Money that is currently goods — on a shelf, or half-built on the floor"
      >
        <DateRangePicker value={range} onChange={setRange} />
      </PageHeader>

      <StageFlow stages={stages} active={tab} onSelect={setTab} />

      <SectionHead
        question="How much is being made, and how much is being scrapped?"
        note="A reject rate that drifts up is the earliest warning a process has slipped."
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ProductionPanel range={range} />
        <BomCoveragePanel />
      </div>

      <SectionHead question="The detail" />
      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "stock" && <InventoryTablePanel />}
      {tab === "categories" && <InventoryCategoryTablePanel />}
      {tab === "production" && <ProductionTablePanel />}
    </div>
  );
}
