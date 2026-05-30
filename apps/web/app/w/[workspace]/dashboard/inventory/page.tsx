"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { InventoryPanel, InventoryCategoryTablePanel } from "@/components/dashboard/panels";

export default function InventoryPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Inventory" subtitle="Stock valuation and category breakdown" />
      <InventoryPanel />
      <InventoryCategoryTablePanel />
    </div>
  );
}
