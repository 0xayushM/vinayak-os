"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import {
  CustomerConcentrationPanel, RevenueKpiPanel, RevenueDailyPanel,
  TopSkusPanel, SalesInvoicesTablePanel,
} from "@/components/dashboard/panels";
import { useRevenueSummary } from "@/hooks/useDashboard";

export default function CustomersPage() {
  const [range, setRange] = useState<DateRange>({});
  const { data } = useRevenueSummary(range.start || range.end ? { start: range.start, end: range.end } : { days: 30 });
  const cov = data?.data;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Customer Insights" subtitle="Revenue concentration and customer activity">
        <DateRangePicker value={range} onChange={setRange} dataFrom={cov?.data_from} dataTo={cov?.data_to} />
      </PageHeader>

      <RevenueDailyPanel range={range} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <CustomerConcentrationPanel range={range} />
        <RevenueKpiPanel range={range} />
      </div>
      <TopSkusPanel range={range} />
      <SalesInvoicesTablePanel range={range} />
    </div>
  );
}
