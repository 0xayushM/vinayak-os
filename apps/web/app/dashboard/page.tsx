"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import {
  RevenueKpiPanel, RevenueTrendPanel, CustomerConcentrationPanel, TopSkusPanel,
  QuotePipelinePanel, PurchaseSummaryPanel, BomCoveragePanel,
  ArAgingPanel, OpenOrdersPanel, OpenPosPanel, InventoryPanel, GrnPanel, ProductionPanel,
} from "@/components/dashboard/panels";

// ════════════════════════════════════════════════════════════════════════════
// Overview — strategic + operational panels at a glance
// ════════════════════════════════════════════════════════════════════════════
export default function DashboardOverview() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-zinc-100">Business Overview</h1>
        <p className="text-xs text-zinc-500 mt-0.5">
          KBrushes · Powered by TranzAct · Panels refresh automatically
        </p>
      </div>

      {/* Strategic panels — daily cache */}
      <section>
        <h2 className="text-xs font-semibold text-zinc-600 uppercase tracking-wider mb-3">
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
        <h2 className="text-xs font-semibold text-zinc-600 uppercase tracking-wider mb-3">
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
