"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { ArAgingPanel, ArBucketTablePanel } from "@/components/dashboard/panels";

export default function ArPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="AR Aging" subtitle="Outstanding receivables and overdue exposure" />
      <ArAgingPanel />
      <ArBucketTablePanel />
    </div>
  );
}
