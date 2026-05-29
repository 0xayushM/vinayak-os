"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { OpenOrdersPanel, OpenOrdersTablePanel } from "@/components/dashboard/panels";

export default function OrdersPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Open Sales Orders" subtitle="Live order book and status breakdown" />
      <OpenOrdersPanel />
      <OpenOrdersTablePanel />
    </div>
  );
}
