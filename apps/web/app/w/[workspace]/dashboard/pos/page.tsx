"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import {
  OpenPosPanel, OpenPosTablePanel, PurchaseOrdersTablePanel,
} from "@/components/dashboard/panels";
import { usePurchaseOrders } from "@/hooks/useDashboard";

export default function PosPage() {
  const [range, setRange] = useState<DateRange>({});
  const { data } = usePurchaseOrders(range.start || range.end ? { start: range.start, end: range.end } : {});
  const cov = data?.data;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Open Purchase Orders" subtitle="Live PO book and overdue exposure">
        <DateRangePicker value={range} onChange={setRange} dataFrom={cov?.data_from} dataTo={cov?.data_to} />
      </PageHeader>
      <OpenPosPanel />
      <OpenPosTablePanel />
      <PurchaseOrdersTablePanel range={range} />
    </div>
  );
}
