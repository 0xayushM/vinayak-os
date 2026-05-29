"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { TopSkusPanel, TopSkusTablePanel } from "@/components/dashboard/panels";

export default function SkusPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Top SKUs" subtitle="Best-selling products by revenue · last 30 days" />
      <TopSkusPanel />
      <TopSkusTablePanel />
    </div>
  );
}
