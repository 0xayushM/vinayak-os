"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { OpenPosPanel } from "@/components/dashboard/panels";

export default function PosPage() {
  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Open Purchase Orders" subtitle="Live PO book and overdue exposure" />
      <OpenPosPanel />
    </div>
  );
}
