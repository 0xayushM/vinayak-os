"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { ArAgingPanel, ArBucketTablePanel } from "@/components/dashboard/panels";

export default function ArPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader title="AR Aging" subtitle="Outstanding receivables and overdue exposure" />
      <ArAgingPanel />
      <ArBucketTablePanel />
    </div>
  );
}
