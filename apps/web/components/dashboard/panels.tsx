"use client";

/**
 * components/dashboard/panels.tsx
 * ────────────────────────────────
 * Every dashboard panel as a self-contained, exported component.
 *
 * Each panel owns its own data hook + loading/error state via PanelWrapper, so
 * panels can be composed freely on the overview page and on the per-domain
 * sidebar pages without any prop wiring.
 */

import { useState } from "react";
import {
  BarChart, Bar, PieChart, Pie, Cell, Area, AreaChart,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { PanelWrapper } from "@/components/dashboard/PanelWrapper";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { DataTable } from "@/components/dashboard/DataTable";
import { FilterableTable, ServerColumn, ServerSort } from "@/components/dashboard/FilterableTable";
import type { DateRange } from "@/components/dashboard/DateRangePicker";
import {
  useRevenueSummary, useRevenueTrend, useRevenueDaily, useCustomerConcentration,
  useTopSkus, useArSummary, useOpenOrders, useInventorySummary,
  useInventoryByCategory, useProductionSummary, usePurchaseSummary,
  useGrnSummary, useOpenPOs, useQuoteSummary, useBomCoverage,
  useTopVendors, useSalesInvoices, useArInvoices,
  usePurchaseInvoices, useSalesOrders, usePurchaseOrders,
  useProductionList, useInventoryList,
  type RangeOpts, type SalesInvoiceRow, type ArInvoiceRow,
  type PurchaseInvoiceRow, type SalesOrderRow, type PurchaseOrderRow,
  type ProductionRow, type InventoryRow,
} from "@/hooks/useDashboard";
import { formatCurrency, formatNumber } from "@/lib/utils/cn";

// ── Shared helpers ────────────────────────────────────────────────────────────
/** A page-level date range (start/end) → the hook's RangeOpts shape. */
function toRangeOpts(range: DateRange | undefined, days: number): RangeOpts {
  if (range?.start || range?.end) return { start: range.start, end: range.end };
  return { days };
}

/** Pretty-print an ISO date (YYYY-MM-DD or full ISO) → "12 Apr 2026". */
function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function CoverageNote({ from, to }: { from?: string | null; to?: string | null }) {
  if (!from && !to) return null;
  return (
    <p className="text-[10.5px] text-zinc-600 pt-2">
      Data in view: {fmtDate(from)} – {fmtDate(to)}
    </p>
  );
}

// ── Chart palette (dark theme) ────────────────────────────────────────────────
export const COLORS = ["#C08457", "#d4a070", "#C4977A", "#F2DEC8", "#8a6050", "#e0c8b0"];
const BLUE  = "#C08457";
const GREEN = "#d4a070";
const AMBER = "#C08457";

const tooltipStyle = {
  contentStyle: {
    background: "rgba(14,14,18,0.95)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    boxShadow: "0 12px 32px -16px rgba(0,0,0,0.8)",
    fontSize: 12,
  },
  labelStyle: { color: "#C4977A" },
  itemStyle: { color: "#F2DEC8" },
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fmt(label: string): (v: any) => [string, string] {
  return (v) => [formatCurrency(Number(v ?? 0)), label];
}

// ── Revenue ─────────────────────────────────────────────────────────────────
export function RevenueKpiPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useRevenueSummary(toRangeOpts(range, 30));
  const d = data?.data;
  const ranged = !!(range?.start || range?.end);
  return (
    <PanelWrapper
      title="Revenue Overview"
      subtitle={ranged ? "Selected range" : "Latest 30 days of data"}
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <div className="grid grid-cols-2 gap-4 pt-2">
        <KpiCard label="Revenue · goods value" value={formatCurrency(d?.period_total_goods ?? d?.period_total ?? 0, true)} accent="blue" sub={`${formatNumber(d?.invoice_count ?? 0)} invoices`} />
        <KpiCard label="Revenue · invoice total" value={formatCurrency(d?.period_total_invoiced ?? 0, true)} accent="emerald" sub="incl. tax / freight" />
        <KpiCard label="Avg / Invoice" value={formatCurrency(d?.avg_invoice_value ?? 0, true)} accent="violet" />
        <KpiCard label="Monthly Avg (12mo)" value={formatCurrency(d?.monthly_avg ?? 0, true)} accent="amber" sub={`invoiced ${formatCurrency(d?.monthly_avg_invoiced ?? 0, true)}`} />
        <KpiCard label={`YTD ${d?.ytd_year ?? ""} · goods`} value={formatCurrency(d?.ytd_total ?? 0, true)} accent="blue" sub={`${formatNumber(d?.customer_count ?? 0)} customers`} />
        <KpiCard label={`YTD ${d?.ytd_year ?? ""} · invoiced`} value={formatCurrency(d?.ytd_invoiced ?? 0, true)} accent="emerald" />
      </div>
      <p className="text-[10.5px] text-zinc-600 pt-2">
        Goods value = sum of line items (ex-tax). Invoice total = printed invoice grand total (incl. tax/freight).
      </p>
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Daily revenue line/area chart — the analytics centerpiece.
export function RevenueDailyPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useRevenueDaily(toRangeOpts(range, 90));
  const days = data?.data?.days ?? [];
  const ranged = !!(range?.start || range?.end);
  return (
    <PanelWrapper
      title="Daily Revenue"
      subtitle={ranged ? "Selected range" : "Latest 90 days of data"}
      meta={data?.meta}
      loading={isLoading}
      error={error}
    >
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={days} margin={{ top: 6, right: 8, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#C08457" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#C08457" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(192,132,87,0.08)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} minTickGap={32}
            tickFormatter={(v) => { const d = new Date(v + "T00:00:00"); return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }); }} />
          <YAxis tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
          <Tooltip {...tooltipStyle} formatter={fmt("Revenue")} labelFormatter={(l) => fmtDate(String(l))} />
          <Area type="monotone" dataKey="revenue" stroke={BLUE} strokeWidth={2} fill="url(#revFill)" />
        </AreaChart>
      </ResponsiveContainer>
      <CoverageNote from={data?.data?.window_from} to={data?.data?.window_to} />
    </PanelWrapper>
  );
}

export function RevenueTrendPanel() {
  const { data, error, isLoading } = useRevenueTrend(6);
  const months = data?.data?.months ?? [];
  return (
    <PanelWrapper title="Revenue Trend" subtitle="6-month bar chart" meta={data?.meta} loading={isLoading} error={error}>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={months} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(192,132,87,0.08)" vertical={false} />
          <XAxis dataKey="month" tick={{ fill: "#C4977A", fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#C4977A", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
          <Tooltip {...tooltipStyle} formatter={fmt("Revenue")} />
          <Bar dataKey="revenue" fill={BLUE} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </PanelWrapper>
  );
}

export function CustomerConcentrationPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useCustomerConcentration(toRangeOpts(range, 30));
  const slices = data?.data?.slices ?? [];
  return (
    <PanelWrapper title="Customer Concentration" subtitle="Top 5 + Others" meta={data?.meta} loading={isLoading} error={error}>
      <div className="flex items-center gap-4">
        <ResponsiveContainer width={120} height={120}>
          <PieChart>
            <Pie data={slices} dataKey="revenue" cx="50%" cy="50%" innerRadius={30} outerRadius={52} paddingAngle={2}>
              {slices.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="transparent" />
              ))}
            </Pie>
            <Tooltip {...tooltipStyle} formatter={fmt("Revenue")} />
          </PieChart>
        </ResponsiveContainer>
        <div className="flex-1 space-y-1.5">
          {slices.map((s, i) => (
            <div key={s.name} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                <span title={s.name} className="text-[#F2DEC8]/75 truncate max-w-[150px]">{s.name}</span>
              </div>
              <span className="text-zinc-500 tabular-nums">{s.pct.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
    </PanelWrapper>
  );
}

export function TopSkusPanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useTopSkus(toRangeOpts(range, 30));
  const skus = data?.data?.skus ?? [];
  const max  = skus[0]?.revenue ?? 1;
  const ranged = !!(range?.start || range?.end);
  return (
    <PanelWrapper title="Top SKUs by Revenue" subtitle={ranged ? "Selected range" : "Latest 30 days of data"} meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-2 pt-1">
        {skus.slice(0, 8).map((s) => (
          <div key={s.sku_code} className="flex items-center gap-2 text-xs">
            <span title={s.sku_code} className="text-zinc-500 font-mono w-24 shrink-0 truncate">{s.sku_code}</span>
            <div className="flex-1 bg-white/[0.06] rounded-full h-1.5 overflow-hidden">
              <div className="h-full rounded-full bg-[#C08457]" style={{ width: `${(s.revenue / max) * 100}%` }} />
            </div>
            <span className="text-[#F2DEC8]/75 tabular-nums w-16 text-right shrink-0">{formatCurrency(s.revenue, true)}</span>
          </div>
        ))}
        {skus.length === 0 && <p className="text-xs text-zinc-600 pt-3">No SKU sales in this period.</p>}
      </div>
      <CoverageNote from={data?.data?.window_from} to={data?.data?.window_to} />
    </PanelWrapper>
  );
}

// Detailed Top-SKU table (used on the SKUs page) — sortable + paginated.
export function TopSkusTablePanel({ range }: { range?: DateRange } = {}) {
  const { data, error, isLoading } = useTopSkus(toRangeOpts(range, 30));
  const skus = data?.data?.skus ?? [];
  type Sku = (typeof skus)[number];
  return (
    <PanelWrapper title="Top SKUs — detail" subtitle="Quantity & revenue" meta={data?.meta} loading={isLoading} error={error}>
      <DataTable<Sku>
        rows={skus}
        rowKey={(s) => s.sku_code}
        emptyMessage="No SKU sales in this period."
        initialSort={{ key: "revenue", dir: "desc" }}
        columns={[
          { key: "sku_code", header: "SKU", sortValue: (s) => s.sku_code,
            cell: (s) => <span className="font-mono text-zinc-400">{s.sku_code}</span> },
          { key: "item_name", header: "Name", sortValue: (s) => s.item_name ?? "",
            cell: (s) => <span className="block truncate max-w-[260px]">{s.item_name}</span> },
          { key: "qty_sold", header: "Qty sold", align: "right", sortValue: (s) => s.qty_sold,
            cell: (s) => formatNumber(s.qty_sold) },
          { key: "revenue", header: "Revenue", align: "right", sortValue: (s) => s.revenue,
            cell: (s) => <span className="text-[#F2DEC8]/90">{formatCurrency(s.revenue, true)}</span> },
        ]}
      />
    </PanelWrapper>
  );
}

export function QuotePipelinePanel() {
  const { data, error, isLoading } = useQuoteSummary(30);
  const d = data?.data;
  return (
    <PanelWrapper title="Quote Pipeline" subtitle="Last 30 days" meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-3 gap-4 pt-2">
        <KpiCard label="Open Quotes" value={formatNumber(d?.open_count ?? 0)} accent="blue" sub={formatCurrency(d?.open_value ?? 0, true)} />
        <KpiCard label="Won" value={formatNumber(d?.won_count ?? 0)} accent="emerald" sub={formatCurrency(d?.won_value ?? 0, true)} />
        <KpiCard label="Conversion Rate" value={`${((d?.conversion_rate ?? 0) * 100).toFixed(1)}%`} accent="violet" />
      </div>
    </PanelWrapper>
  );
}

export function PurchaseSummaryPanel() {
  const { data, error, isLoading } = usePurchaseSummary(30);
  const d = data?.data;
  return (
    <PanelWrapper title="Purchases" subtitle="Last 30 days" meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-2 gap-4 pt-2">
        <KpiCard label="Spend · goods value" value={formatCurrency(d?.period_total_goods ?? d?.period_total ?? 0, true)} accent="amber" sub={`${d?.invoice_count ?? 0} invoices`} />
        <KpiCard label="Spend · invoice total" value={formatCurrency(d?.period_total_invoiced ?? 0, true)} accent="emerald" sub="incl. tax / freight" />
        <KpiCard label="Monthly Avg" value={formatCurrency(d?.monthly_avg ?? 0, true)} accent="blue" sub={`invoiced ${formatCurrency(d?.monthly_avg_invoiced ?? 0, true)}`} />
        <KpiCard label="Active Vendors" value={formatNumber(d?.vendor_count ?? 0)} accent="violet" />
      </div>
      <p className="text-[10.5px] text-zinc-600 pt-2">
        Goods value = sum of line items (ex-tax). Invoice total = printed grand total (incl. tax/freight).
      </p>
    </PanelWrapper>
  );
}

export function TopVendorsPanel() {
  const { data, error, isLoading } = useTopVendors(30);
  const vendors = data?.data?.vendors ?? [];
  const max = vendors[0]?.spend ?? 1;
  return (
    <PanelWrapper title="Top Vendors by Spend" subtitle="Last 30 days" meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-2 pt-1">
        {vendors.slice(0, 8).map((v) => (
          <div key={v.vendor_name} className="flex items-center gap-2 text-xs">
            <span title={v.vendor_name} className="text-zinc-400 w-40 shrink-0 truncate">{v.vendor_name}</span>
            <div className="flex-1 bg-white/[0.06] rounded-full h-1.5 overflow-hidden">
              <div className="h-full rounded-full bg-amber-500" style={{ width: `${(v.spend / max) * 100}%` }} />
            </div>
            <span className="text-[#F2DEC8]/75 tabular-nums w-16 text-right shrink-0">{formatCurrency(v.spend, true)}</span>
          </div>
        ))}
        {vendors.length === 0 && <p className="text-xs text-zinc-600 pt-3">No vendor spend in this period.</p>}
      </div>
    </PanelWrapper>
  );
}

export function BomCoveragePanel() {
  const { data, error, isLoading } = useBomCoverage();
  const d = data?.data;
  const pct = d?.coverage_pct ?? 0;
  return (
    <PanelWrapper title="BOM Coverage" subtitle="Items with routing" meta={data?.meta} loading={isLoading} error={error}>
      <div className="pt-2 space-y-3">
        <div className="flex items-end justify-between">
          <span className="text-3xl font-semibold tracking-tight text-[#C08457] tabular-nums">{pct.toFixed(1)}%</span>
          <span className="text-xs text-zinc-500">{d?.items_with_bom}/{d?.total_items} items</span>
        </div>
        <div className="w-full bg-white/[0.06] rounded-full h-2 overflow-hidden">
          <div className="h-full rounded-full bg-[#C08457] transition-all" style={{ width: `${pct}%` }} />
        </div>
        {(d?.items_missing_bom ?? 0) > 0 && (
          <p className="text-xs text-amber-400">{d?.items_missing_bom} items missing BOM</p>
        )}
      </div>
    </PanelWrapper>
  );
}

export function ArAgingPanel() {
  const { data, error, isLoading } = useArSummary();
  const d = data?.data;
  const buckets = d?.buckets ?? [];
  return (
    <PanelWrapper title="AR Aging" subtitle="Outstanding receivables" meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-3 pt-1">
        <div className="grid grid-cols-2 gap-4">
          <KpiCard label="Total Outstanding" value={formatCurrency(d?.total_outstanding ?? 0, true)} accent="blue" />
          <KpiCard label="Overdue" value={formatCurrency(d?.overdue_amount ?? 0, true)} accent="red" sub={`${((d?.overdue_pct ?? 0) * 100).toFixed(1)}% of total`} />
        </div>
        <ResponsiveContainer width="100%" height={120}>
          <BarChart data={buckets} layout="vertical" margin={{ left: 0, right: 8, top: 0, bottom: 0 }}>
            <XAxis type="number" tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
            <YAxis type="category" dataKey="bucket" tick={{ fill: "#C4977A", fontSize: 10 }} axisLine={false} tickLine={false} width={60} />
            <Tooltip {...tooltipStyle} formatter={fmt("Amount")} />
            <Bar dataKey="amount" fill={AMBER} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </PanelWrapper>
  );
}

// AR aging bucket breakdown table (AR page).
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

export function OpenOrdersPanel() {
  const { data, error, isLoading } = useOpenOrders();
  const d = data?.data;
  const byStatus = d?.by_status ?? [];
  return (
    <PanelWrapper title="Open Sales Orders" subtitle="Live order book" meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-3 pt-1">
        <div className="flex gap-4">
          <KpiCard label="Open Orders" value={formatNumber(d?.open_count ?? 0)} accent="blue" />
          <KpiCard label="Open Value" value={formatCurrency(d?.open_value ?? 0, true)} accent="emerald" />
          <KpiCard label="Oldest Order" value={`${d?.oldest_order_days ?? 0}d`} accent="amber" />
        </div>
        <div className="space-y-1">
          {byStatus.map((s) => (
            <div key={s.status} className="flex justify-between text-xs">
              <span className="text-zinc-400">{s.status}</span>
              <div className="flex gap-3">
                <span className="text-zinc-500">{s.count} orders</span>
                <span className="text-[#F2DEC8]/75 tabular-nums">{formatCurrency(s.value, true)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </PanelWrapper>
  );
}

// Open orders by-status detail table (Orders page).
export function OpenOrdersTablePanel() {
  const { data, error, isLoading } = useOpenOrders();
  const rows = data?.data?.by_status ?? [];
  type Row = (typeof rows)[number];
  return (
    <PanelWrapper title="Orders by status — detail" subtitle="Count & value per status" meta={data?.meta} loading={isLoading} error={error}>
      <DataTable<Row>
        rows={rows}
        rowKey={(r) => r.status}
        emptyMessage="No open orders."
        initialSort={{ key: "value", dir: "desc" }}
        columns={[
          { key: "status", header: "Status", sortValue: (r) => r.status, cell: (r) => r.status },
          { key: "count", header: "Orders", align: "right", sortValue: (r) => r.count, cell: (r) => formatNumber(r.count) },
          { key: "value", header: "Value", align: "right", sortValue: (r) => r.value,
            cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.value, true)}</span> },
        ]}
      />
    </PanelWrapper>
  );
}

// Open POs by-vendor detail table (POs page).
export function OpenPosTablePanel() {
  const { data, error, isLoading } = useOpenPOs();
  const rows = data?.data?.by_vendor ?? [];
  type Row = (typeof rows)[number];
  return (
    <PanelWrapper title="Open POs by vendor — detail" subtitle="Outstanding PO value per vendor" meta={data?.meta} loading={isLoading} error={error}>
      <DataTable<Row>
        rows={rows}
        rowKey={(r) => r.vendor_name}
        emptyMessage="No open purchase orders."
        initialSort={{ key: "value", dir: "desc" }}
        columns={[
          { key: "vendor_name", header: "Vendor", sortValue: (r) => r.vendor_name ?? "",
            cell: (r) => <span className="block truncate max-w-[280px]">{r.vendor_name}</span> },
          { key: "value", header: "Open value", align: "right", sortValue: (r) => r.value,
            cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.value, true)}</span> },
        ]}
      />
    </PanelWrapper>
  );
}

export function OpenPosPanel() {
  const { data, error, isLoading } = useOpenPOs();
  const d = data?.data;
  return (
    <PanelWrapper title="Open Purchase Orders" subtitle="Live PO book" meta={data?.meta} loading={isLoading} error={error}>
      <div className="space-y-3 pt-1">
        <div className="grid grid-cols-3 gap-4">
          <KpiCard label="Open POs" value={formatNumber(d?.open_count ?? 0)} accent="blue" />
          <KpiCard label="Open Value" value={formatCurrency(d?.open_value ?? 0, true)} accent="amber" />
          <KpiCard label="Overdue POs" value={formatNumber(d?.overdue_count ?? 0)} accent="red" />
        </div>
        <div className="space-y-1">
          {(d?.by_vendor ?? []).slice(0, 5).map((v) => (
            <div key={v.vendor_name} className="flex justify-between text-xs gap-2">
              <span title={v.vendor_name} className="text-zinc-400 truncate max-w-[180px]">{v.vendor_name}</span>
              <span className="text-[#F2DEC8]/75 tabular-nums">{formatCurrency(v.value, true)}</span>
            </div>
          ))}
        </div>
      </div>
    </PanelWrapper>
  );
}

export function InventoryPanel() {
  const { data: sumData, error: sumError, isLoading: sumLoading } = useInventorySummary();
  const { data: catData } = useInventoryByCategory();
  const d          = sumData?.data;
  const categories = catData?.data?.categories ?? [];
  return (
    <PanelWrapper title="Inventory" subtitle="Stock valuation" meta={sumData?.meta} loading={sumLoading} error={sumError}>
      <div className="space-y-3 pt-1">
        <div className="grid grid-cols-2 gap-3">
          <KpiCard label="Total Value" value={formatCurrency(d?.total_value ?? 0, true)} accent="blue" />
          <KpiCard label="SKUs Tracked" value={formatNumber(d?.total_skus ?? 0)} accent="emerald" />
          <KpiCard label="Low Stock" value={formatNumber(d?.low_stock_count ?? 0)} accent="amber" />
          <KpiCard label="Zero Stock" value={formatNumber(d?.zero_stock_count ?? 0)} accent="red" />
        </div>
        {categories.length > 0 && (
          <ResponsiveContainer width="100%" height={90}>
            <BarChart data={categories.slice(0, 6)} margin={{ top: 0, right: 4, left: -20, bottom: 0 }}>
              <XAxis dataKey="category" tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#C4977A", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCurrency(v, true)} />
              <Tooltip {...tooltipStyle} formatter={fmt("Value")} />
              <Bar dataKey="value" fill={GREEN} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </PanelWrapper>
  );
}

// Inventory category breakdown table (Inventory page).
export function InventoryCategoryTablePanel() {
  const { data, error, isLoading } = useInventoryByCategory();
  const cats = data?.data?.categories ?? [];
  return (
    <PanelWrapper title="Inventory by category — detail" subtitle="Value & SKU count per category" meta={data?.meta} loading={isLoading} error={error}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-zinc-500 border-b border-white/[0.07]">
              <th className="text-left font-medium py-2">Category</th>
              <th className="text-right font-medium py-2">Value</th>
              <th className="text-right font-medium py-2">SKUs</th>
            </tr>
          </thead>
          <tbody>
            {cats.map((c) => (
              <tr key={c.category} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                <td className="py-2 text-[#F2DEC8]/75">{c.category}</td>
                <td className="py-2 text-right text-[#F2DEC8]/90 tabular-nums">{formatCurrency(c.value, true)}</td>
                <td className="py-2 text-right text-zinc-400 tabular-nums">{formatNumber(c.sku_count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {cats.length === 0 && <p className="text-xs text-zinc-600 pt-3">No inventory categories yet.</p>}
      </div>
    </PanelWrapper>
  );
}

export function GrnPanel() {
  const { data, error, isLoading } = useGrnSummary(30);
  const d = data?.data;
  return (
    <PanelWrapper title="GRN / Goods Received" subtitle="Last 30 days" meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-3 gap-4 pt-2">
        <KpiCard label="GRNs Received" value={formatNumber(d?.received_count ?? 0)} accent="blue" sub={formatCurrency(d?.total_value ?? 0, true)} />
        <KpiCard label="Pending QIR" value={formatNumber(d?.pending_qir ?? 0)} accent="amber" />
        <KpiCard label="Rejection Rate" value={`${((d?.rejection_rate ?? 0) * 100).toFixed(1)}%`} accent={(d?.rejection_rate ?? 0) > 0.05 ? "red" : "emerald"} />
      </div>
    </PanelWrapper>
  );
}

export function ProductionPanel() {
  const { data, error, isLoading } = useProductionSummary();
  const d = data?.data;
  return (
    <PanelWrapper title="Production" subtitle="WIP & completed jobs" meta={data?.meta} loading={isLoading} error={error}>
      <div className="grid grid-cols-3 gap-4 pt-2">
        <KpiCard label="WIP Jobs" value={formatNumber(d?.wip_count ?? 0)} accent="blue" sub={formatCurrency(d?.wip_value ?? 0, true)} />
        <KpiCard label="Completed" value={formatNumber(d?.completed_count ?? 0)} accent="emerald" />
        <KpiCard label="Avg Cycle Time" value={`${(d?.avg_cycle_days ?? 0).toFixed(1)}d`} accent="amber" />
      </div>
    </PanelWrapper>
  );
}

// ── Row-level detail tables (server-side search / date filter / pagination) ───

const PAGE_SIZE = 25;

const statusPill: Record<string, string> = {
  paid:    "bg-[#C08457]/10 text-[#d4a070] border-[#C08457]/20",
  unpaid:  "bg-amber-500/10 text-amber-300 border-amber-500/20",
  partial: "bg-[#C08457]/15 text-[#C08457] border-[#C08457]/20",
};

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-zinc-600">—</span>;
  const cls = statusPill[status.toLowerCase()] ?? "bg-white/[0.05] text-zinc-400 border-white/[0.08]";
  return <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${cls}`}>{status}</span>;
}

// Sales invoice line items — searchable, date-filterable, server-paginated.
export function SalesInvoicesTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "invoice_date", direction: "desc" });

  const { data, error, isLoading } = useSalesInvoices({
    start: range?.start, end: range?.end, search: search || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const rows = d?.rows ?? [];

  const columns: ServerColumn<SalesInvoiceRow>[] = [
    { key: "invoice_date", header: "Date", sortKey: "invoice_date",
      cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.invoice_date)}</span> },
    { key: "invoice_number", header: "Invoice #",
      cell: (r) => <span className="font-mono text-zinc-400">{r.invoice_number}</span> },
    { key: "customer_name", header: "Customer", sortKey: "customer_name",
      cell: (r) => <span className="block truncate max-w-[180px]">{r.customer_name}</span> },
    { key: "sku", header: "SKU",
      cell: (r) => <span className="block truncate max-w-[160px]"><span className="font-mono text-zinc-500">{r.sku_code}</span>{r.sku_name ? ` · ${r.sku_name}` : ""}</span> },
    { key: "quantity", header: "Qty", align: "right", sortKey: "quantity",
      cell: (r) => formatNumber(r.quantity) },
    { key: "line_total", header: "Line total", align: "right", sortKey: "line_total",
      cell: (r) => formatCurrency(r.line_total, true) },
    { key: "invoice_total", header: "Invoice total", align: "right", sortKey: "invoice_total",
      cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.invoice_total, true)}</span> },
    { key: "payment_status", header: "Status", align: "center",
      cell: (r) => <StatusBadge status={r.payment_status} /> },
  ];

  return (
    <PanelWrapper title="Sales invoices — line items" subtitle="Search, sort and page through every invoice line" meta={data?.meta} error={error}>
      <FilterableTable<SalesInvoiceRow>
        columns={columns}
        rows={rows}
        rowKey={(r) => `${r.invoice_number}-${r.sku_code ?? ""}-${r.line_total}`}
        page={d?.page ?? 0}
        pageCount={d?.page_count ?? 1}
        filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE}
        sort={sort}
        loading={isLoading}
        search={search}
        onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort}
        onPageChange={setPage}
        searchPlaceholder="Search customer, invoice #, SKU…"
        emptyMessage="No invoices match these filters."
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// AR invoice line items — searchable, bucket/overdue filterable, server-paginated.
export function ArInvoicesTablePanel() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [sort, setSort] = useState<ServerSort>({ sort: "outstanding_amount", direction: "desc" });

  const { data, error, isLoading } = useArInvoices({
    search: search || undefined, overdue_only: overdueOnly,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const rows = d?.rows ?? [];

  const columns: ServerColumn<ArInvoiceRow>[] = [
    { key: "customer_name", header: "Customer", sortKey: "customer_name",
      cell: (r) => <span className="block truncate max-w-[200px]">{r.customer_name}</span> },
    { key: "invoice_number", header: "Invoice #",
      cell: (r) => <span className="font-mono text-zinc-400">{r.invoice_number}</span> },
    { key: "invoice_date", header: "Invoiced", sortKey: "invoice_date",
      cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.invoice_date)}</span> },
    { key: "due_date", header: "Due", sortKey: "due_date",
      cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.due_date)}</span> },
    { key: "invoice_amount", header: "Amount", align: "right", sortKey: "invoice_amount",
      cell: (r) => formatCurrency(r.invoice_amount, true) },
    { key: "outstanding_amount", header: "Outstanding", align: "right", sortKey: "outstanding_amount",
      cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.outstanding_amount, true)}</span> },
    { key: "days_overdue", header: "Overdue", align: "right", sortKey: "days_overdue",
      cell: (r) => r.days_overdue == null ? "—" : <span className={r.days_overdue > 0 ? "text-amber-300" : "text-zinc-400"}>{r.days_overdue}d</span> },
    { key: "aging_bucket", header: "Bucket", align: "center",
      cell: (r) => <span className="text-zinc-400">{r.aging_bucket ?? "—"}</span> },
  ];

  return (
    <PanelWrapper title="AR invoices — line items" subtitle="Outstanding receivables, invoice by invoice" meta={data?.meta} error={error}>
      <FilterableTable<ArInvoiceRow>
        columns={columns}
        rows={rows}
        rowKey={(r) => `${r.invoice_number}-${r.customer_name}`}
        page={d?.page ?? 0}
        pageCount={d?.page_count ?? 1}
        filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE}
        sort={sort}
        loading={isLoading}
        search={search}
        onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort}
        onPageChange={setPage}
        searchPlaceholder="Search customer or invoice #…"
        emptyMessage="No receivables match these filters."
        toolbar={
          <button
            onClick={() => { setOverdueOnly((v) => !v); setPage(0); }}
            className={`text-[11px] rounded-lg px-2.5 py-2 border transition-colors shrink-0 ${
              overdueOnly
                ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
                : "text-zinc-400 border-white/[0.08] hover:text-[#F2DEC8]/90"
            }`}
          >
            Overdue only
          </button>
        }
      />
    </PanelWrapper>
  );
}

// Status-filter dropdown shared by order/PO/production tables.
function StatusFilter({ value, options, onChange }: {
  value: string; options: string[]; onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-[var(--bg-elevated)] text-[#F2DEC8]/75 text-[11px] rounded-lg px-2 py-2 border border-white/[0.08] focus:border-[#C08457] focus:outline-none shrink-0 [color-scheme:dark]"
    >
      <option value="">All statuses</option>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

// Purchase invoice line items.
export function PurchaseInvoicesTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "invoice_date", direction: "desc" });
  const { data, error, isLoading } = usePurchaseInvoices({
    start: range?.start, end: range?.end, search: search || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<PurchaseInvoiceRow>[] = [
    { key: "invoice_date", header: "Date", sortKey: "invoice_date",
      cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.invoice_date)}</span> },
    { key: "invoice_number", header: "Invoice #", cell: (r) => <span className="font-mono text-zinc-400">{r.invoice_number}</span> },
    { key: "vendor_name", header: "Vendor", sortKey: "vendor_name", cell: (r) => <span className="block truncate max-w-[180px]">{r.vendor_name}</span> },
    { key: "item", header: "Item", cell: (r) => <span className="block truncate max-w-[160px]"><span className="font-mono text-zinc-500">{r.item_code}</span>{r.item_name ? ` · ${r.item_name}` : ""}</span> },
    { key: "quantity", header: "Qty", align: "right", sortKey: "quantity", cell: (r) => formatNumber(r.quantity) },
    { key: "line_total", header: "Line total", align: "right", sortKey: "line_total", cell: (r) => formatCurrency(r.line_total, true) },
    { key: "invoice_total", header: "Invoice total", align: "right", sortKey: "invoice_total", cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.invoice_total, true)}</span> },
  ];
  return (
    <PanelWrapper title="Purchase invoices — line items" subtitle="Search, sort and page through every purchase line" meta={data?.meta} error={error}>
      <FilterableTable<PurchaseInvoiceRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.invoice_number}-${r.item_code ?? ""}-${r.line_total}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search vendor, invoice #, item…" emptyMessage="No purchase invoices match these filters."
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Sales order line items.
export function SalesOrdersTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "order_date", direction: "desc" });
  const { data, error, isLoading } = useSalesOrders({
    start: range?.start, end: range?.end, search: search || undefined, status: status || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<SalesOrderRow>[] = [
    { key: "order_date", header: "Ordered", sortKey: "order_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.order_date)}</span> },
    { key: "order_number", header: "Order #", cell: (r) => <span className="font-mono text-zinc-400">{r.order_number}</span> },
    { key: "customer_name", header: "Customer", sortKey: "customer_name", cell: (r) => <span className="block truncate max-w-[160px]">{r.customer_name}</span> },
    { key: "sku", header: "SKU", cell: (r) => <span className="block truncate max-w-[150px]"><span className="font-mono text-zinc-500">{r.sku_code}</span>{r.sku_name ? ` · ${r.sku_name}` : ""}</span> },
    { key: "pending_qty", header: "Pending", align: "right", sortKey: "pending_qty", cell: (r) => formatNumber(r.pending_qty) },
    { key: "order_value", header: "Value", align: "right", sortKey: "order_value", cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.order_value, true)}</span> },
    { key: "delivery_date", header: "Delivery", sortKey: "delivery_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.delivery_date)}</span> },
    { key: "status", header: "Status", align: "center", cell: (r) => <StatusBadge status={r.status} /> },
  ];
  return (
    <PanelWrapper title="Sales orders — line items" subtitle="Open and historical order book" meta={data?.meta} error={error}>
      <FilterableTable<SalesOrderRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.order_number}-${r.sku_code ?? ""}-${r.order_value}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search customer, order #, SKU…" emptyMessage="No sales orders match these filters."
        toolbar={<StatusFilter value={status} options={["Open", "Partial", "Closed", "Cancelled"]} onChange={(v) => { setStatus(v); setPage(0); }} />}
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Purchase order line items.
export function PurchaseOrdersTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "po_date", direction: "desc" });
  const { data, error, isLoading } = usePurchaseOrders({
    start: range?.start, end: range?.end, search: search || undefined, status: status || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<PurchaseOrderRow>[] = [
    { key: "po_date", header: "PO date", sortKey: "po_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.po_date)}</span> },
    { key: "po_number", header: "PO #", cell: (r) => <span className="font-mono text-zinc-400">{r.po_number}</span> },
    { key: "vendor_name", header: "Vendor", sortKey: "vendor_name", cell: (r) => <span className="block truncate max-w-[160px]">{r.vendor_name}</span> },
    { key: "item", header: "Item", cell: (r) => <span className="block truncate max-w-[150px]"><span className="font-mono text-zinc-500">{r.item_code}</span>{r.item_name ? ` · ${r.item_name}` : ""}</span> },
    { key: "pending_qty", header: "Pending", align: "right", sortKey: "pending_qty", cell: (r) => formatNumber(r.pending_qty) },
    { key: "po_value", header: "Value", align: "right", sortKey: "po_value", cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.po_value, true)}</span> },
    { key: "expected_date", header: "Expected", sortKey: "expected_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.expected_date)}</span> },
    { key: "status", header: "Status", align: "center", cell: (r) => <StatusBadge status={r.status} /> },
  ];
  return (
    <PanelWrapper title="Purchase orders — line items" subtitle="Open and historical PO book" meta={data?.meta} error={error}>
      <FilterableTable<PurchaseOrderRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.po_number}-${r.item_code ?? ""}-${r.po_value}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search vendor, PO #, item…" emptyMessage="No purchase orders match these filters."
        toolbar={<StatusFilter value={status} options={["Open", "Partial", "Closed", "Cancelled"]} onChange={(v) => { setStatus(v); setPage(0); }} />}
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Production process records.
export function ProductionTablePanel({ range }: { range?: DateRange } = {}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "production_date", direction: "desc" });
  const { data, error, isLoading } = useProductionList({
    start: range?.start, end: range?.end, search: search || undefined, status: status || undefined,
    page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<ProductionRow>[] = [
    { key: "production_date", header: "Date", sortKey: "production_date", cell: (r) => <span className="text-zinc-400 whitespace-nowrap">{fmtDate(r.production_date)}</span> },
    { key: "work_order_number", header: "Work order", sortKey: "work_order_number", cell: (r) => <span className="font-mono text-zinc-400">{r.work_order_number}</span> },
    { key: "sku", header: "SKU", cell: (r) => <span className="block truncate max-w-[150px]"><span className="font-mono text-zinc-500">{r.sku_code}</span>{r.sku_name ? ` · ${r.sku_name}` : ""}</span> },
    { key: "process_name", header: "Process", cell: (r) => <span className="block truncate max-w-[130px]">{r.process_name}</span> },
    { key: "planned_qty", header: "Planned", align: "right", sortKey: "planned_qty", cell: (r) => formatNumber(r.planned_qty) },
    { key: "produced_qty", header: "Produced", align: "right", sortKey: "produced_qty", cell: (r) => <span className="text-[#F2DEC8]/90">{formatNumber(r.produced_qty)}</span> },
    { key: "rejected_qty", header: "Rejected", align: "right", sortKey: "rejected_qty", cell: (r) => <span className={r.rejected_qty > 0 ? "text-amber-300" : "text-zinc-400"}>{formatNumber(r.rejected_qty)}</span> },
    { key: "status", header: "Status", align: "center", cell: (r) => <StatusBadge status={r.status} /> },
  ];
  return (
    <PanelWrapper title="Production — process records" subtitle="Work orders, output and rejects" meta={data?.meta} error={error}>
      <FilterableTable<ProductionRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.work_order_number}-${r.process_name ?? ""}-${r.produced_qty}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search work order, SKU, process…" emptyMessage="No production records match these filters."
        toolbar={<StatusFilter value={status} options={["Planned", "In Progress", "Completed", "On Hold"]} onChange={(v) => { setStatus(v); setPage(0); }} />}
      />
      <CoverageNote from={d?.window_from} to={d?.window_to} />
    </PanelWrapper>
  );
}

// Inventory valuation rows (snapshot — no date window).
export function InventoryTablePanel() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<ServerSort>({ sort: "total_value", direction: "desc" });
  const { data, error, isLoading } = useInventoryList({
    search: search || undefined, page, page_size: PAGE_SIZE, sort: sort.sort, direction: sort.direction,
  });
  const d = data?.data;
  const columns: ServerColumn<InventoryRow>[] = [
    { key: "sku_code", header: "SKU", cell: (r) => <span className="font-mono text-zinc-400">{r.sku_code}</span> },
    { key: "sku_name", header: "Name", sortKey: "sku_name", cell: (r) => <span className="block truncate max-w-[200px]">{r.sku_name}</span> },
    { key: "category", header: "Category", sortKey: "category", cell: (r) => <span className="text-zinc-400">{r.category ?? "—"}</span> },
    { key: "warehouse", header: "Warehouse", cell: (r) => <span className="text-zinc-400 truncate max-w-[120px] block">{r.warehouse ?? "—"}</span> },
    { key: "quantity", header: "Qty", align: "right", sortKey: "quantity", cell: (r) => <span className={r.is_negative_stock ? "text-red-400" : ""}>{formatNumber(r.quantity)}</span> },
    { key: "unit_cost", header: "Unit cost", align: "right", sortKey: "unit_cost", cell: (r) => formatCurrency(r.unit_cost, true) },
    { key: "total_value", header: "Value", align: "right", sortKey: "total_value", cell: (r) => <span className="text-[#F2DEC8]/90">{formatCurrency(r.total_value, true)}</span> },
  ];
  return (
    <PanelWrapper title="Inventory — valuation detail" subtitle="Every SKU, searchable and sortable" meta={data?.meta} error={error}>
      <FilterableTable<InventoryRow>
        columns={columns} rows={d?.rows ?? []}
        rowKey={(r) => `${r.sku_code}-${r.warehouse ?? ""}`}
        page={d?.page ?? 0} pageCount={d?.page_count ?? 1} filteredTotal={d?.total_count ?? 0}
        pageSize={d?.page_size ?? PAGE_SIZE} sort={sort} loading={isLoading}
        search={search} onSearchChange={(s) => { setSearch(s); setPage(0); }}
        onSortChange={setSort} onPageChange={setPage}
        searchPlaceholder="Search SKU, name, category, warehouse…" emptyMessage="No stock rows match these filters."
      />
    </PanelWrapper>
  );
}
