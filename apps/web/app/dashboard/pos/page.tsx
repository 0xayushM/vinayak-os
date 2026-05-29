"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { OpenPosPanel, OpenPosTablePanel } from "@/components/dashboard/panels";

export default function PosPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Open Purchase Orders" subtitle="Live PO book and overdue exposure" />
      <OpenPosPanel />
      <OpenPosTablePanel />
    </div>
  );
}
