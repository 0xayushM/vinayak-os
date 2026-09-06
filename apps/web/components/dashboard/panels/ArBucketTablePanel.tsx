"use client";

import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";
import { useArSummary } from "@/hooks/useDashboard";

export function ArBucketTablePanel() {
  const { data, error, isLoading } = useArSummary();
  const buckets = data?.data?.buckets ?? [];
  return (
    <PanelWrapper title="Aging buckets — detail" subtitle="Amount & invoice count per bucket" meta={data?.meta} loading={isLoading} error={error}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-zinc-500 border-b border-white/[0.07]">
              <th className="text-left font-medium py-2">Bucket</th>
              <th className="text-right font-medium py-2">Amount</th>
              <th className="text-right font-medium py-2">Invoices</th>
              <th className="text-right font-medium py-2">Avg days overdue</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((b) => (
              <tr key={b.bucket} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                <td className="py-2 text-[#F2DEC8]/75">{b.bucket}</td>
                <td className="py-2 text-right text-[#F2DEC8]/90 tabular-nums">{formatCurrency(b.amount, true)}</td>
                <td className="py-2 text-right text-zinc-400 tabular-nums">{formatNumber(b.invoice_count)}</td>
                <td className="py-2 text-right text-zinc-400 tabular-nums">{Math.round(b.overdue_days_avg)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PanelWrapper>
  );
}
