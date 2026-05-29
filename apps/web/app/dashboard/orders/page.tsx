"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { OpenOrdersPanel } from "@/components/dashboard/panels";

export default function OrdersPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Open Sales Orders" subtitle="Live order book and status breakdown" />
      <OpenOrdersPanel />
    </div>
  );
}
