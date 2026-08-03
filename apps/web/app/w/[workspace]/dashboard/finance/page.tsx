"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import {
  FinanceOverviewPanel, MonthCompareTool, CashMovementPanel,
  CollectionsPriorityPanel, CreditRiskPanel, CustomerFinancePanel,
} from "@/components/dashboard/panels";

/**
 * Finance — a dynamic workbench for the money side of the business. Every tool is
 * deterministic (no AI) and finance-specific (not duplicated from other pages).
 * These same tools are the read layer the Brain queries to answer finance questions.
 *
 * Paired rows use the grid's default `stretch` (no items-start), so the two cards
 * in a row are always equal height — no tall/short mismatch, no uneven gap. The
 * chart tools sit side by side (half width) rather than stretched full width.
 */
export default function FinancePage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1500px] mx-auto w-full animate-rise">
      <PageHeader title="Finance" subtitle="Understand the money — deterministic tools you can act on today" />

      <div className="space-y-5 mt-2">
        <FinanceOverviewPanel />

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <MonthCompareTool />
          <CashMovementPanel />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <CollectionsPriorityPanel />
          <CreditRiskPanel />
        </div>

        <CustomerFinancePanel />
      </div>
    </div>
  );
}
