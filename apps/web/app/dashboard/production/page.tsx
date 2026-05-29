"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { ProductionPanel } from "@/components/dashboard/panels";

export default function ProductionPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Production" subtitle="WIP, completed jobs and cycle time" />
      <div className="max-w-xl">
        <ProductionPanel />
      </div>
    </div>
  );
}
