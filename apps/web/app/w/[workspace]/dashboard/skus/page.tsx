"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import {
  TopSkusPanel, TopSkusTablePanel, SalesInvoicesTablePanel,
} from "@/components/dashboard/panels";
import { useTopSkus } from "@/hooks/useDashboard";

export default function SkusPage() {
  const [range, setRange] = useState<DateRange>({});
  // Reuse the SKU query just to surface the data-coverage span in the picker.
  const { data } = useTopSkus(range.start || range.end ? { start: range.start, end: range.end } : { days: 30 });
  const cov = data?.data;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Top SKUs" subtitle="Best-selling products by revenue">
        <DateRangePicker value={range} onChange={setRange} dataFrom={cov?.data_from} dataTo={cov?.data_to} />
      </PageHeader>

      <TopSkusPanel range={range} />
      <TopSkusTablePanel range={range} />
      <SalesInvoicesTablePanel range={range} />
    </div>
  );
}
