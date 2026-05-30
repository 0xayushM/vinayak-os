"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { BomCoveragePanel } from "@/components/dashboard/panels";

export default function BomPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="BOM Coverage" subtitle="Items with process routing defined" />
      <div className="max-w-md">
        <BomCoveragePanel />
      </div>
    </div>
  );
}
