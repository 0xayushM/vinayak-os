"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { QuotePipelinePanel } from "@/components/dashboard/panels";

export default function QuotesPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Quotes & Pipeline" subtitle="Quotation volume and conversion · last 30 days" />
      <div className="max-w-xl">
        <QuotePipelinePanel />
      </div>
    </div>
  );
}
