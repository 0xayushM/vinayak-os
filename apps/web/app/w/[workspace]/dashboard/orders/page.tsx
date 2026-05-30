"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import {
  OpenOrdersPanel, OpenOrdersTablePanel, SalesOrdersTablePanel,
} from "@/components/dashboard/panels";
import { useSalesOrders } from "@/hooks/useDashboard";

export default function OrdersPage() {
  const [range, setRange] = useState<DateRange>({});
  const { data } = useSalesOrders(range.start || range.end ? { start: range.start, end: range.end } : {});
  const cov = data?.data;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Open Sales Orders" subtitle="Live order book and status breakdown">
        <DateRangePicker value={range} onChange={setRange} dataFrom={cov?.data_from} dataTo={cov?.data_to} />
      </PageHeader>
      <OpenOrdersPanel />
      <OpenOrdersTablePanel />
      <SalesOrdersTablePanel range={range} />
    </div>
  );
}
