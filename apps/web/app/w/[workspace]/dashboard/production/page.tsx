"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import { ProductionPanel, ProductionTablePanel } from "@/components/dashboard/panels";
import { useProductionList } from "@/hooks/useDashboard";

export default function ProductionPage() {
  const [range, setRange] = useState<DateRange>({});
  const { data } = useProductionList(range.start || range.end ? { start: range.start, end: range.end } : {});
  const cov = data?.data;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="Production" subtitle="WIP, completed jobs and cycle time">
        <DateRangePicker value={range} onChange={setRange} dataFrom={cov?.data_from} dataTo={cov?.data_to} />
      </PageHeader>
      <div className="max-w-xl">
        <ProductionPanel />
      </div>
      <ProductionTablePanel range={range} />
    </div>
  );
}
