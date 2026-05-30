"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { CustomerConcentrationPanel, RevenueKpiPanel, TopSkusPanel } from "@/components/dashboard/panels";

export default function CustomersPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Customer Insights" subtitle="Revenue concentration and customer activity · last 30 days" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <CustomerConcentrationPanel />
        <RevenueKpiPanel />
      </div>
      <TopSkusPanel />
    </div>
  );
}
