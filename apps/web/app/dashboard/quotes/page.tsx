"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { QuotePipelinePanel } from "@/components/dashboard/panels";

export default function QuotesPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Quotes & Pipeline" subtitle="Quotation volume and conversion · last 30 days" />
      <div className="max-w-xl">
        <QuotePipelinePanel />
      </div>
    </div>
  );
}
