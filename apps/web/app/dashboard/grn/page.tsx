"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { GrnPanel } from "@/components/dashboard/panels";

export default function GrnPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="GRN / Goods Received" subtitle="Goods received notes and quality inspection · last 30 days" />
      <div className="max-w-xl">
        <GrnPanel />
      </div>
    </div>
  );
}
