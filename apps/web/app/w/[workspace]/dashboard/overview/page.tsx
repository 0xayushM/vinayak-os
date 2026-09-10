"use client";

import { use, useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import { SectionHead } from "@/components/dashboard/StageFlow";
import {
  RevenueKpiPanel, RevenueTrendPanel, RevenueDailyPanel, CustomerConcentrationPanel,
  TopSkusPanel, QuotePipelinePanel, PurchaseSummaryPanel, BomCoveragePanel,
  ArAgingPanel, OpenOrdersPanel, OpenPosPanel, InventoryPanel, GrnPanel, ProductionPanel,
} from "@/components/dashboard/panels";
import { useRevenueSummary } from "@/hooks/useDashboard";

/**
 * Daily overview — the whole business on one screen.
 *
 * Today answers "what changed and what should I do about it". The four
 * business pages answer "where is money stuck in this loop". This page answers
 * neither: it is the scan, the thing you read with a cup of tea to see that
 * everything is roughly where you left it. Numbers here are deliberately the
 * same numbers as elsewhere — that is what a scan is — and every panel links
 * into the page that owns the detail.
 */
export default function OverviewPage({ params }: { params: Promise<{ workspace: string }> }) {
  const { workspace } = use(params);
  const brandName = decodeURIComponent(workspace);
  const [range, setRange] = useState<DateRange>({});

  const { data: revData } = useRevenueSummary(
    range.start || range.end ? { start: range.start, end: range.end } : {},
  );
  const cov = revData?.data;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto w-full animate-rise space-y-5">
      <PageHeader
        title="Daily overview"
        subtitle={`${brandName} · the whole business on one screen`}
      >
        <DateRangePicker
          value={range}
          onChange={setRange}
          dataFrom={cov?.data_from}
          dataTo={cov?.data_to}
          className="shrink-0"
        />
      </PageHeader>

      <SectionHead
        question="How is the business selling?"
        note="Revenue day by day, who it came from, and what they bought."
      />
      <RevenueDailyPanel range={range} />
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 items-start">
        <RevenueKpiPanel range={range} />
        <RevenueTrendPanel range={range} />
        <CustomerConcentrationPanel range={range} />
        <TopSkusPanel range={range} />
      </div>

      <SectionHead
        question="What is in the pipeline, and what is it costing?"
        note="Quotes yet to convert, spend with vendors, and how much of the catalogue can be costed."
      />
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 items-start">
        <QuotePipelinePanel range={range} />
        <PurchaseSummaryPanel range={range} />
        <BomCoveragePanel />
      </div>

      <SectionHead
        question="What does the working day look like right now?"
        note="The live books — receivables, order book, purchase orders, stock, receipts, production."
      />
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 items-start">
        <ArAgingPanel />
        <OpenOrdersPanel />
        <OpenPosPanel />
        <InventoryPanel />
        <GrnPanel range={range} />
        <ProductionPanel range={range} />
      </div>
    </div>
  );
}
