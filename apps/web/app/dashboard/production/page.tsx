"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { ProductionPanel } from "@/components/dashboard/panels";

export default function ProductionPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Production" subtitle="WIP, completed jobs and cycle time" />
      <div className="max-w-xl">
        <ProductionPanel />
      </div>
    </div>
  );
}
