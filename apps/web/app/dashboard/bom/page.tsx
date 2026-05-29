"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { BomCoveragePanel } from "@/components/dashboard/panels";

export default function BomPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader title="BOM Coverage" subtitle="Items with process routing defined" />
      <div className="max-w-md">
        <BomCoveragePanel />
      </div>
    </div>
  );
}
