"use client";

import { use } from "react";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import {
  RevenueKpiPanel, RevenueTrendPanel, CustomerConcentrationPanel, TopSkusPanel,
  QuotePipelinePanel, PurchaseSummaryPanel, BomCoveragePanel,
  ArAgingPanel, OpenOrdersPanel, OpenPosPanel, InventoryPanel, GrnPanel, ProductionPanel,
} from "@/components/dashboard/panels";

// ════════════════════════════════════════════════════════════════════════════
// Overview — strategic + operational panels at a glance
// ════════════════════════════════════════════════════════════════════════════
export default function DashboardOverview({ params }: { params: Promise<{ workspace: string }> }) {
  const { workspace } = use(params);
  const brandName = decodeURIComponent(workspace);

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-8 max-w-[1600px] mx-auto w-full animate-rise">
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-zinc-50">
          Business Overview
        </h1>
        <p className="text-[12.5px] text-zinc-500 mt-1">
          {brandName} · Powered by TranzAct · Panels refresh automatically
        </p>
      </div>

      {/* Strategic panels — daily cache */}
      <section>
        <h2 className="text-[11px] font-semibold text-zinc-600 uppercase tracking-[0.1em] mb-3">
          Strategic — Daily Refresh
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <RevenueKpiPanel />
          <RevenueTrendPanel />
          <CustomerConcentrationPanel />
          <TopSkusPanel />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mt-4">
          <QuotePipelinePanel />
          <PurchaseSummaryPanel />
          <BomCoveragePanel />
          <PanelWrapper title="Top Vendors" subtitle="See Purchases page for full breakdown">
            <p className="text-xs text-zinc-600 pt-3">
              Vendor-level analysis is available on the Purchases page.
            </p>
          </PanelWrapper>
        </div>
      </section>

      {/* Operational panels — hourly cache */}
      <section>
        <h2 className="text-[11px] font-semibold text-zinc-600 uppercase tracking-[0.1em] mb-3">
          Operational — Hourly Refresh
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <ArAgingPanel />
          <OpenOrdersPanel />
          <OpenPosPanel />
          <InventoryPanel />
          <GrnPanel />
          <ProductionPanel />
        </div>
      </section>
    </div>
  );
}
