"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import { StageFlow, Tabs, SectionHead, type Stage } from "@/components/dashboard/StageFlow";
import {
  PurchaseOrdersTablePanel, PurchaseInvoicesTablePanel, TopVendorsPanel,
  GrnPanel, CashMovementPanel,
} from "@/components/dashboard/panels";
import { useOpenPOs, useGrnSummary, usePurchaseSummary } from "@/hooks/useDashboard";
import { formatCurrency } from "@/lib/utils/cn";

/**
 * Money out — the buying loop, mirror of Money in:
 * ordered → received → billed → owed to vendors.
 *
 * The last stage is honestly empty: vendor bills with due dates are not
 * synced yet, so payables cannot be computed. Saying that is better than
 * showing a zero that looks like a number.
 */
const TABS = [
  { key: "pos", label: "Purchase orders" },
  { key: "received", label: "Goods received" },
  { key: "bills", label: "Purchase invoices" },
  { key: "vendors", label: "Vendors" },
];

export default function MoneyOutPage() {
  const [range, setRange] = useState<DateRange>({});
  const [tab, setTab] = useState("pos");

  const pos = useOpenPOs();
  const grn = useGrnSummary(range.start || range.end ? range : {});
  const spend = usePurchaseSummary(range.start || range.end ? range : {});

  const p = pos.data?.data;
  const g = grn.data?.data;
  const s = spend.data?.data;

  const stages: Stage[] = [
    {
      key: "pos", label: "Ordered, not received",
      value: p ? formatCurrency(p.open_value, true) : "—",
      note: p ? `${p.open_count} open POs` : undefined,
      stuck: p?.overdue_count ? { value: String(p.overdue_count), label: "past expected date" } : undefined,
      loading: pos.isLoading,
    },
    {
      key: "received", label: "Received",
      value: g ? String(g.received_count) : "—",
      note: g ? `receipts in the window · ${g.rejection_rate}% rejected` : undefined,
      stuck: g?.pending_qir ? { value: String(g.pending_qir), label: "awaiting inspection" } : undefined,
      loading: grn.isLoading,
    },
    {
      key: "bills", label: "Billed by vendors",
      value: s ? formatCurrency(s.period_total_goods, true) : "—",
      note: s ? `${s.vendor_count} vendors` : undefined,
      loading: spend.isLoading,
    },
    {
      key: "payable", label: "Owed to vendors",
      value: "—",
      missing: "Vendor bills with due dates are not synced yet, so payables and DPO cannot be computed",
    },
  ];

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto w-full animate-rise space-y-5">
      <PageHeader
        title="Money out"
        subtitle="What you have committed to vendors, what has arrived, and what it cost"
      >
        <DateRangePicker value={range} onChange={setRange} />
      </PageHeader>

      <StageFlow stages={stages} active={tab} onSelect={setTab} />

      <SectionHead
        question="Is more going out than coming in?"
        note="Money in against money out, month by month — the only place these two loops meet."
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <CashMovementPanel />
        <GrnPanel range={range} />
      </div>

      <SectionHead question="The detail, one stage at a time" />
      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "pos" && <PurchaseOrdersTablePanel />}
      {tab === "received" && <GrnPanel range={range} />}
      {tab === "bills" && <PurchaseInvoicesTablePanel range={range} />}
      {tab === "vendors" && <TopVendorsPanel range={range} />}
    </div>
  );
}
