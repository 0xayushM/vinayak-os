"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { TopSkusPanel, TopSkusTablePanel } from "@/components/dashboard/panels";

export default function SkusPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Top SKUs" subtitle="Best-selling products by revenue · last 30 days" />
      <TopSkusPanel />
      <TopSkusTablePanel />
    </div>
  );
}
