"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import { StageFlow, Tabs, SectionHead, type Stage } from "@/components/dashboard/StageFlow";
import {
  QuotePipelinePanel, OpenOrdersTablePanel, SalesInvoicesTablePanel,
  ArInvoicesTablePanel, ArAgingPanel, CollectionsPriorityPanel,
  RevenueTrendPanel, TopSkusTablePanel,
} from "@/components/dashboard/panels";
import {
  useQuoteSummary, useOpenOrders, useRevenueSummary, useArSummary,
} from "@/hooks/useDashboard";
import { useInferredPayments } from "@/hooks/usePulse";
import { formatCurrency } from "@/lib/utils/cn";

/**
 * Money in — the selling loop, in the order money actually travels:
 * quote → order → invoice → owed → collected.
 *
 * Everything about incoming money lives here and nowhere else, so no figure
 * on this page is repeated on another. The flow at the top says where value
 * is sitting; the tabs below open the detail for one stage at a time.
 */
const TABS = [
  { key: "quotes", label: "Quotes" },
  { key: "orders", label: "Orders" },
  { key: "invoices", label: "Invoices" },
  { key: "receivables", label: "Receivables" },
  { key: "products", label: "What sells" },
];

export default function MoneyInPage() {
  const [range, setRange] = useState<DateRange>({});
  const [tab, setTab] = useState("receivables");

  const quotes = useQuoteSummary(range.start || range.end ? range : {});
  const orders = useOpenOrders();
  const revenue = useRevenueSummary(range.start || range.end ? range : {});
  const ar = useArSummary();
  const paid = useInferredPayments();

  const q = quotes.data?.data;
  const o = orders.data?.data;
  const r = revenue.data?.data;
  const a = ar.data?.data;

  const stages: Stage[] = [
    {
      key: "quotes", label: "Quoted",
      value: q ? formatCurrency(q.open_value, true) : "—",
      note: q ? `${q.open_count} open · ${q.conversion_rate}% convert` : undefined,
      loading: quotes.isLoading,
    },
    {
      key: "orders", label: "Ordered, not delivered",
      value: o ? formatCurrency(o.open_value, true) : "—",
      note: o ? `${o.open_count} open · ${Math.round(o.dispatched_pct)}% dispatched` : undefined,
      stuck: o?.overdue_count
        ? { value: String(o.overdue_count), label: "past delivery date" }
        : undefined,
      loading: orders.isLoading,
    },
    {
      key: "invoices", label: "Invoiced",
      value: r ? formatCurrency(r.period_total_goods, true) : "—",
      note: r ? `${r.invoice_count} invoices · ${r.customer_count} customers` : undefined,
      loading: revenue.isLoading,
    },
    {
      key: "receivables", label: "Owed to you",
      value: a ? formatCurrency(a.total_outstanding, true) : "—",
      note: a ? `${a.overdue_pct}% of it overdue` : undefined,
      stuck: a?.overdue_amount
        ? { value: formatCurrency(a.overdue_amount, true), label: "overdue" }
        : undefined,
      loading: ar.isLoading,
    },
    {
      key: "collected", label: "Collected",
      value: paid.data?.avg_days_to_pay != null ? `${paid.data.avg_days_to_pay} days` : "—",
      note: paid.data?.count ? `average, from ${paid.data.count} payments` : undefined,
      missing: paid.data && paid.data.history_building
        ? "Learning payment dates from the daily receivables book — a few more days"
        : undefined,
      loading: paid.isLoading,
    },
  ];

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto w-full animate-rise space-y-5">
      <PageHeader
        title="Money in"
        subtitle="Every rupee from the first quote to the day it lands — and where it is stuck"
      >
        <DateRangePicker value={range} onChange={setRange} />
      </PageHeader>

      <StageFlow stages={stages} active={tab} onSelect={setTab} />

      <SectionHead
        question="What is holding up the money you are owed?"
        note="The chase list is ranked by recovery impact — amount weighted by how late it is."
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ArAgingPanel />
        <CollectionsPriorityPanel />
      </div>

      <SectionHead question="The detail, one stage at a time" />
      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "quotes" && <QuotePipelinePanel range={range} />}
      {tab === "orders" && <OpenOrdersTablePanel />}
      {tab === "invoices" && (
        <div className="space-y-4">
          <RevenueTrendPanel range={range} />
          <SalesInvoicesTablePanel range={range} />
        </div>
      )}
      {tab === "receivables" && <ArInvoicesTablePanel />}
      {tab === "products" && <TopSkusTablePanel range={range} />}
    </div>
  );
}
