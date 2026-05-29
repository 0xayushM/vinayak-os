"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { InventoryPanel, InventoryCategoryTablePanel } from "@/components/dashboard/panels";

export default function InventoryPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Inventory" subtitle="Stock valuation and category breakdown" />
      <InventoryPanel />
      <InventoryCategoryTablePanel />
    </div>
  );
}
