"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import { GrnPanel } from "@/components/dashboard/panels";

export default function GrnPage() {
  const [range, setRange] = useState<DateRange>({});

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto w-full animate-rise">
      <PageHeader title="GRN / Goods Received" subtitle="Goods received notes and quality inspection">
        <DateRangePicker value={range} onChange={setRange} />
      </PageHeader>
      <div className="max-w-xl">
        <GrnPanel range={range} />
      </div>
    </div>
  );
}
