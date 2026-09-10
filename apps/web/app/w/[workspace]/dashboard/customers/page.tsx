"use client";

import { use, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { DateRangePicker, DateRange } from "@/components/dashboard/DateRangePicker";
import { Tabs, SectionHead } from "@/components/dashboard/StageFlow";
import {
  CustomerFinancePanel, CustomerConcentrationPanel, CreditRiskPanel,
} from "@/components/dashboard/panels";
import { usePulse } from "@/hooks/usePulse";
import { workspacePath } from "@/lib/api";
import { AlertTriangle, Clock } from "lucide-react";

/**
 * Customers — the customer axis of the business, in one place.
 *
 * Everything the system knows about a customer converges here: what they buy,
 * what they owe, whether they pay on time, and whether they have quietly
 * stopped ordering. Revenue charts do NOT live here — they belong to Money in.
 * This page is about people, not periods.
 */
const TABS = [
  { key: "all", label: "Every customer" },
  { key: "risk", label: "Credit risk" },
  { key: "quiet", label: "Gone quiet" },
];

function QuietCustomers({ workspace }: { workspace: string }) {
  const { data, isLoading } = usePulse();
  const card = data?.cards.find((c) => c.key === "reorder_radar");

  if (isLoading) return <p className="text-sm text-zinc-500">Loading…</p>;
  if (!card || card.items.length === 0) {
    return (
      <div className="surface-card p-8 text-center">
        <p className="text-sm text-zinc-400">Every regular buyer is inside their usual rhythm.</p>
        <p className="text-xs text-zinc-600 mt-1">
          A customer appears here once they pass 1.5× their own median gap between orders.
        </p>
      </div>
    );
  }
  return (
    <div className="surface-card p-4 space-y-3">
      <p className="text-[12.5px] text-zinc-400">{card.why}</p>
      <div className="space-y-1.5">
        {card.items.map((it, i) => (
          <div key={i} className="flex items-center justify-between gap-3 rounded-lg bg-black/20 border border-white/[0.05] px-3 py-2">
            <span className="flex items-center gap-2 text-[12.5px] text-zinc-200 truncate">
              <Clock className="w-3.5 h-3.5 text-amber-300 shrink-0" />
              {it.label}
            </span>
            <span className="text-[11.5px] text-zinc-400 tabular-nums shrink-0">
              {it.value} <span className="text-zinc-600">silent / usual</span>
            </span>
          </div>
        ))}
      </div>
      <Link
        href={workspacePath(workspace, "/dashboard")}
        className="inline-block text-[11.5px] text-[#C08457] hover:underline"
      >
        Draft nudges from Today →
      </Link>
    </div>
  );
}

export default function CustomersPage({ params }: { params: Promise<{ workspace: string }> }) {
  const { workspace } = use(params);
  const [range, setRange] = useState<DateRange>({});
  const [tab, setTab] = useState("all");
  const { data } = usePulse();
  const conc = data?.cards.find((c) => c.key === "concentration");

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto w-full animate-rise space-y-5">
      <PageHeader
        title="Customers"
        subtitle="What each customer buys, owes, and whether they still order — one row each"
      >
        <DateRangePicker value={range} onChange={setRange} />
      </PageHeader>

      {conc && (
        <div className="surface-card p-4 flex items-start gap-3">
          <AlertTriangle className={`w-4 h-4 shrink-0 mt-0.5 ${conc.severity >= 45 ? "text-amber-300" : "text-zinc-600"}`} />
          <div>
            <p className="text-[13px] text-zinc-200">{conc.why}</p>
            <p className="text-[11px] text-zinc-500 mt-0.5">
              Concentration is the risk that one relationship ending changes the business.
            </p>
          </div>
        </div>
      )}

      <SectionHead
        question="Who matters, and who is a risk?"
        note="Share of revenue on the left; who is over-exposed or stretching terms on the right."
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <CustomerConcentrationPanel range={range} />
        <CreditRiskPanel />
      </div>

      <SectionHead question="Every customer, with everything we know" />
      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "all" && <CustomerFinancePanel />}
      {tab === "risk" && <CreditRiskPanel />}
      {tab === "quiet" && <QuietCustomers workspace={workspace} />}
    </div>
  );
}
