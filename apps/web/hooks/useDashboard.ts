/**
 * useDashboard.ts
 * ───────────────
 * SWR hook wrappers for every dashboard panel endpoint.
 *
 * All calls go to /api/dashboard/* (Next.js BFF routes).
 * The BFF proxies to FastAPI over a private, server-only network address.
 * The FastAPI URL is NEVER present in this file or in the browser network tab.
 */
import useSWR, { SWRConfiguration } from "swr";
import { apiFetch } from "@/lib/api";

// ── SWR fetcher ───────────────────────────────────────────────────────────────
async function fetcher<T>(url: string): Promise<T> {
  const res = await apiFetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Response envelope type ────────────────────────────────────────────────────
export interface PanelMeta {
  report_id:     number;
  last_synced_at: string | null;
  stale:          boolean;
}

export interface PanelResponse<T> {
  data: T;
  meta: PanelMeta;
}

// ── Refresh intervals ─────────────────────────────────────────────────────────
const HOURLY  = 60 * 60 * 1_000;
const DAILY   = 24 * HOURLY;

const swrHourly: SWRConfiguration = { refreshInterval: HOURLY,  revalidateOnFocus: false };
const swrDaily:  SWRConfiguration = { refreshInterval: DAILY,   revalidateOnFocus: false };

// ── Shared: data-coverage window meta ─────────────────────────────────────────
export interface WindowMeta {
  window_from: string | null;
  window_to:   string | null;
  data_from:   string | null;
  data_to:     string | null;
}

/** Build a `?start=&end=&days=` query string, omitting empty params. */
function rangeQuery(opts: { days?: number; start?: string; end?: string } = {}): string {
  const p = new URLSearchParams();
  if (opts.start) p.set("start", opts.start);
  if (opts.end)   p.set("end", opts.end);
  if (opts.days != null && !opts.start && !opts.end) p.set("days", String(opts.days));
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

export interface RangeOpts { days?: number; start?: string; end?: string; }

// ── Revenue panels ────────────────────────────────────────────────────────────
export interface RevenueSummary extends WindowMeta {
  period_days:      number;
  period_total:     number;   // goods basis (SUM line_total)
  period_total_goods:    number;
  period_total_invoiced: number;  // printed invoice grand total
  invoice_count:    number;
  customer_count:   number;
  avg_invoice_value: number;
  monthly_avg:      number;
  monthly_avg_invoiced: number;
  ytd_total:        number;
  ytd_invoiced:     number;
  ytd_year:         number;
}

export function useRevenueSummary(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<RevenueSummary>>(
    `/api/dashboard/revenue-summary${rangeQuery(opts)}`,
    fetcher,
    swrDaily,
  );
}

export interface RevenueTrendMonth { month: string; revenue: number; invoice_count: number; }
export interface RevenueTrend { months: RevenueTrendMonth[]; data_from: string | null; data_to: string | null; }

export function useRevenueTrend(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<RevenueTrend>>(
    `/api/dashboard/revenue-trend${rangeQuery(opts)}`,
    fetcher,
    swrDaily,
  );
}

export interface RevenueDailyPoint { date: string; revenue: number; invoice_count: number; }
export interface RevenueDaily extends WindowMeta { days: RevenueDailyPoint[]; }

export function useRevenueDaily(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<RevenueDaily>>(
    `/api/dashboard/revenue-daily${rangeQuery(opts)}`,
    fetcher,
    swrDaily,
  );
}

export interface CustomerSlice { name: string; revenue: number; pct: number; }
export interface CustomerConcentration extends WindowMeta { slices: CustomerSlice[]; }

export function useCustomerConcentration(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<CustomerConcentration>>(
    `/api/dashboard/customer-concentration${rangeQuery(opts)}`,
    fetcher,
    swrDaily,
  );
}

export interface TopSku { sku_code: string; item_name: string; qty_sold: number; revenue: number; }
export interface TopSkus extends WindowMeta { skus: TopSku[]; }

export function useTopSkus(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<TopSkus>>(
    `/api/dashboard/top-skus${rangeQuery(opts)}`,
    fetcher,
    swrDaily,
  );
}

export interface QuoteSummary {
  open_count: number; open_value: number;
  won_count: number; won_value: number;
  conversion_rate: number;
}

export function useQuoteSummary(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<QuoteSummary>>(
    `/api/dashboard/quote-summary${rangeQuery(opts)}`,
    fetcher,
    swrDaily,
  );
}

export interface PurchaseSummary {
  period_total: number;   // goods basis (SUM line_total)
  period_total_goods: number;
  period_total_invoiced: number;  // printed invoice grand total
  invoice_count: number; vendor_count: number;
  monthly_avg: number; monthly_avg_invoiced: number;
  window_from?: string | null; window_to?: string | null;
}

export function usePurchaseSummary(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<PurchaseSummary>>(
    `/api/dashboard/purchase-summary${rangeQuery(opts)}`,
    fetcher,
    swrDaily,
  );
}

export interface TopVendor { vendor_name: string; spend: number; invoice_count: number; }
export interface TopVendors { vendors: TopVendor[]; }

export function useTopVendors(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<TopVendors>>(
    `/api/dashboard/top-vendors${rangeQuery(opts)}`,
    fetcher,
    swrDaily,
  );
}

export interface BomCoverage {
  total_items: number; items_with_bom: number; coverage_pct: number; items_missing_bom: number;
}

export function useBomCoverage() {
  return useSWR<PanelResponse<BomCoverage>>("/api/dashboard/bom-coverage", fetcher, swrDaily);
}

// ── AR panel ──────────────────────────────────────────────────────────────────
export interface ArBucket {
  bucket: string; amount: number; invoice_count: number; overdue_days_avg: number;
}
export interface ArSummary {
  total_outstanding: number; overdue_amount: number; overdue_pct: number; buckets: ArBucket[];
}

export function useArSummary() {
  return useSWR<PanelResponse<ArSummary>>("/api/dashboard/ar-summary", fetcher, swrHourly);
}

// ── Open orders panel ─────────────────────────────────────────────────────────
export interface OpenOrderSummary {
  open_count: number; open_value: number; oldest_order_days: number;
  by_status: { status: string; count: number; value: number }[];
}

export function useOpenOrders() {
  return useSWR<PanelResponse<OpenOrderSummary>>(
    "/api/dashboard/open-orders",
    fetcher,
    swrHourly,
  );
}

// ── Purchase orders panel ─────────────────────────────────────────────────────
export interface OpenPoSummary {
  open_count: number; open_value: number; overdue_count: number;
  by_vendor: { vendor_name: string; count: number; value: number }[];
}

export function useOpenPOs() {
  return useSWR<PanelResponse<OpenPoSummary>>(
    "/api/dashboard/open-pos",
    fetcher,
    swrHourly,
  );
}

// ── Inventory panels ──────────────────────────────────────────────────────────
export interface InventorySummary {
  total_value: number; total_skus: number; low_stock_count: number; zero_stock_count: number;
}

export function useInventorySummary() {
  return useSWR<PanelResponse<InventorySummary>>(
    "/api/dashboard/inventory-summary",
    fetcher,
    swrHourly,
  );
}

export interface InventoryCategory { category: string; value: number; sku_count: number; }
export interface InventoryByCategory { categories: InventoryCategory[]; total_value: number; }

export function useInventoryByCategory() {
  return useSWR<PanelResponse<InventoryByCategory>>(
    "/api/dashboard/inventory-by-category",
    fetcher,
    swrHourly,
  );
}

// ── GRN / production panels ───────────────────────────────────────────────────
export interface GrnSummary {
  received_count: number; total_value: number; pending_qir: number; rejection_rate: number;
}

export function useGrnSummary(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<GrnSummary>>(
    `/api/dashboard/grn-summary${rangeQuery(opts)}`,
    fetcher,
    swrDaily,
  );
}

export interface ProductionSummary {
  wip_count: number; wip_value: number; completed_count: number; avg_cycle_days: number;
}

export function useProductionSummary(opts: RangeOpts = {}) {
  return useSWR<PanelResponse<ProductionSummary>>(
    `/api/dashboard/production-summary${rangeQuery(opts)}`,
    fetcher,
    swrHourly,
  );
}

// ── Row-level detail lists (server-side search / date / pagination) ───────────
export interface ListMeta extends WindowMeta {
  total_count:    number;
  filtered_total: number;
  page:           number;
  page_size:      number;
  page_count:     number;
  sort:           string;
  direction:      string;
  search:         string | null;
}

export interface SalesInvoiceRow {
  invoice_date:   string;
  invoice_number: string;
  customer_name:  string;
  sku_code:       string | null;
  sku_name:       string | null;
  quantity:       number;
  unit_price:     number;
  line_total:     number;
  invoice_total:  number;
  payment_status: string | null;
  salesperson:    string | null;
}
export interface SalesInvoicesList extends ListMeta { rows: SalesInvoiceRow[]; }

export interface SalesInvoicesQuery {
  start?: string; end?: string; search?: string;
  page?: number; page_size?: number; sort?: string; direction?: string;
}

export function useSalesInvoices(q: SalesInvoicesQuery = {}) {
  const p = new URLSearchParams();
  if (q.start)     p.set("start", q.start);
  if (q.end)       p.set("end", q.end);
  if (q.search)    p.set("search", q.search);
  if (q.page != null)      p.set("page", String(q.page));
  if (q.page_size != null) p.set("page_size", String(q.page_size));
  if (q.sort)      p.set("sort", q.sort);
  if (q.direction) p.set("direction", q.direction);
  const qs = p.toString() ? `?${p}` : "";
  return useSWR<PanelResponse<SalesInvoicesList>>(
    `/api/dashboard/sales-invoices${qs}`,
    fetcher,
    { ...swrDaily, keepPreviousData: true },
  );
}

export interface ArInvoiceRow {
  customer_name:      string;
  invoice_number:     string;
  invoice_date:       string | null;
  due_date:           string | null;
  invoice_amount:     number;
  outstanding_amount: number;
  days_overdue:       number | null;
  aging_bucket:       string | null;
}
export interface ArInvoicesList extends ListMeta { rows: ArInvoiceRow[]; }

export interface ArInvoicesQuery {
  search?: string; bucket?: string; overdue_only?: boolean;
  page?: number; page_size?: number; sort?: string; direction?: string;
}

export function useArInvoices(q: ArInvoicesQuery = {}) {
  const p = new URLSearchParams();
  if (q.search)       p.set("search", q.search);
  if (q.bucket)       p.set("bucket", q.bucket);
  if (q.overdue_only) p.set("overdue_only", "true");
  if (q.page != null)      p.set("page", String(q.page));
  if (q.page_size != null) p.set("page_size", String(q.page_size));
  if (q.sort)      p.set("sort", q.sort);
  if (q.direction) p.set("direction", q.direction);
  const qs = p.toString() ? `?${p}` : "";
  return useSWR<PanelResponse<ArInvoicesList>>(
    `/api/dashboard/ar-invoices${qs}`,
    fetcher,
    { ...swrHourly, keepPreviousData: true },
  );
}

// Generic builder for the transactional list hooks below.
function listQuery(q: Record<string, string | number | boolean | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === "" || v === false) continue;
    p.set(k, String(v));
  }
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

export interface PurchaseInvoiceRow {
  invoice_date: string | null; invoice_number: string;
  vendor_name: string; vendor_code: string | null;
  item_code: string | null; item_name: string | null;
  quantity: number; unit_price: number; line_total: number; invoice_total: number;
}
export interface PurchaseInvoicesList extends ListMeta { rows: PurchaseInvoiceRow[]; }

export function usePurchaseInvoices(q: SalesInvoicesQuery = {}) {
  return useSWR<PanelResponse<PurchaseInvoicesList>>(
    `/api/dashboard/purchase-invoices${listQuery({ ...q })}`,
    fetcher, { ...swrDaily, keepPreviousData: true },
  );
}

export interface SalesOrderRow {
  order_date: string | null; order_number: string; customer_name: string;
  sku_code: string | null; sku_name: string | null;
  ordered_qty: number; dispatched_qty: number; pending_qty: number;
  order_value: number; delivery_date: string | null; status: string | null;
}
export interface SalesOrdersList extends ListMeta { rows: SalesOrderRow[]; status: string | null; }

export interface OrderListQuery extends SalesInvoicesQuery { status?: string; }

export function useSalesOrders(q: OrderListQuery = {}) {
  return useSWR<PanelResponse<SalesOrdersList>>(
    `/api/dashboard/sales-orders${listQuery({ ...q })}`,
    fetcher, { ...swrHourly, keepPreviousData: true },
  );
}

export interface PurchaseOrderRow {
  po_date: string | null; po_number: string; vendor_name: string;
  item_code: string | null; item_name: string | null;
  ordered_qty: number; received_qty: number; pending_qty: number;
  po_value: number; expected_date: string | null; status: string | null;
}
export interface PurchaseOrdersList extends ListMeta { rows: PurchaseOrderRow[]; status: string | null; }

export function usePurchaseOrders(q: OrderListQuery = {}) {
  return useSWR<PanelResponse<PurchaseOrdersList>>(
    `/api/dashboard/purchase-orders${listQuery({ ...q })}`,
    fetcher, { ...swrHourly, keepPreviousData: true },
  );
}

export interface ProductionRow {
  production_date: string | null; work_order_number: string;
  sku_code: string | null; sku_name: string | null; process_name: string | null;
  planned_qty: number; produced_qty: number; rejected_qty: number; status: string | null;
}
export interface ProductionList extends ListMeta { rows: ProductionRow[]; status: string | null; }

export function useProductionList(q: OrderListQuery = {}) {
  return useSWR<PanelResponse<ProductionList>>(
    `/api/dashboard/production-list${listQuery({ ...q })}`,
    fetcher, { ...swrHourly, keepPreviousData: true },
  );
}

export interface InventoryRow {
  sku_code: string; sku_name: string | null; category: string | null; warehouse: string | null;
  quantity: number; unit_cost: number; total_value: number;
  is_raw_material: boolean; is_negative_stock: boolean;
}
export interface InventoryList extends ListMeta { rows: InventoryRow[]; category: string | null; }

export interface InventoryListQuery {
  search?: string; category?: string;
  page?: number; page_size?: number; sort?: string; direction?: string;
}

export function useInventoryList(q: InventoryListQuery = {}) {
  return useSWR<PanelResponse<InventoryList>>(
    `/api/dashboard/inventory-list${listQuery({ ...q })}`,
    fetcher, { ...swrHourly, keepPreviousData: true },
  );
}

// ── Sync health ───────────────────────────────────────────────────────────────
export interface SyncRun {
  pipeline_name: string; status: string; started_at: string;
  completed_at: string | null; rows_upserted: number | null; error_message: string | null;
}
export interface SyncHealth { runs: SyncRun[]; stale_pipelines: string[]; healthy: boolean; }

// ── Layer-2: business profile + memory facts ──────────────────────────────────
export interface BusinessProfile {
  industry: string | null;
  sub_vertical: string | null;
  fiscal_year_start: string | null;
  gst_registered: boolean | null;
  base_currency: string | null;
  healthy_margin_pct: number | null;
  seasonality: string | null;
  key_customers: unknown[] | null;
  kpis: string | null;
  extras: Record<string, unknown> | null;
  updated_at: string | null;
}

export interface MemoryFact {
  id: string;
  entity_type: string | null;
  entity_ref: string | null;
  claim_key: string | null;
  claim_value: unknown;
  origin: string | null;
  confidence: number | null;
  created_at: string | null;
  valid_until: string | null;
  last_validated_at: string | null;
  status: "active" | "stale" | "superseded";
  superseded_by: string | null;
  stale_reason: string | null;
}

export function useProfile() {
  return useSWR<{ profile: BusinessProfile | null }>(
    "/api/be/dashboard/profile", fetcher, { revalidateOnFocus: false },
  );
}

export async function saveProfile(body: Partial<BusinessProfile>): Promise<void> {
  const res = await apiFetch("/api/be/dashboard/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export function useMemory(entityRef?: string) {
  const qs = entityRef ? `?entity_ref=${encodeURIComponent(entityRef)}` : "";
  return useSWR<{ facts: MemoryFact[] }>(
    `/api/be/dashboard/memory${qs}`, fetcher, { revalidateOnFocus: false },
  );
}

export async function addFact(body: {
  entity_type: string; entity_ref: string; claim_key: string;
  claim_value: unknown; origin?: string; valid_until?: string | null;
}): Promise<void> {
  const res = await apiFetch("/api/be/dashboard/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function deleteFact(id: string): Promise<void> {
  const res = await apiFetch(`/api/be/dashboard/memory/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function revalidateMemory(): Promise<{ time_stale: number; contradiction_stale: number }> {
  const res = await apiFetch("/api/be/dashboard/memory/revalidate", { method: "POST" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Layer-3: AI reasoning (ask) ───────────────────────────────────────────────
export interface AskClaim {
  text: string;
  type: "computed" | "inference" | "unknown";
  evidence: string[];
  assumption: string | null;
}
export interface AskEvidence { id: string; label: string; value: unknown; display: string; }
export interface SuggestedFact { entity_type: string; entity_ref: string; claim_key: string; prompt: string; }
export interface AnswerChart {
  title: string; unit: string;
  items: { name: string; value: number; display: string }[];
}
export interface AskResponse {
  id?: string;
  thread_id?: string;
  question: string;
  intent: string;
  answer: string;
  confidence_level: "CERTAIN" | "PROBABLE" | "UNCERTAIN";
  claims: AskClaim[];
  evidence: AskEvidence[];
  assumptions: string[];
  data_used: string[];
  what_i_dont_know: string[];
  suggested_fact: SuggestedFact | null;
  gates: { data: string; rule: string; confidence: string };
  chart: AnswerChart | null;
  meta?: { routed_by: string; phrased_by: string; ai_active: boolean; model: string | null; tier: string | null };
}

export interface ChatTurn { id: string; question: string; answer: AskResponse; created_at: string | null; }
export interface ChatThreadMeta { id: string; title: string; created_at: string; updated_at: string; turn_count: number; }

async function beJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(url, init);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useThreads() {
  return useSWR<{ threads: ChatThreadMeta[] }>("/api/be/dashboard/chat/threads", fetcher, {
    revalidateOnFocus: false,
  });
}

export const createThread = (title?: string) =>
  beJson<{ thread: ChatThreadMeta }>("/api/be/dashboard/chat/threads", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title ?? null }),
  }).then((r) => r.thread);

export const fetchThreadTurns = (id: string) =>
  beJson<{ turns: ChatTurn[] }>(`/api/be/dashboard/chat/threads/${id}`).then((r) => r.turns);

export const renameThread = (id: string, title: string) =>
  beJson(`/api/be/dashboard/chat/threads/${id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });

export const deleteThread = (id: string) =>
  beJson(`/api/be/dashboard/chat/threads/${id}`, { method: "DELETE" });

export async function askQuestion(question: string, threadId?: string): Promise<AskResponse> {
  const res = await apiFetch("/api/be/dashboard/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, thread_id: threadId ?? null }),
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(e.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Layer-4: eval harness ─────────────────────────────────────────────────────
export interface EvalMetrics {
  cases_run: number;
  passed: number;
  intent_accuracy: number;
  bucket_accuracy: number;
  correct_refusal_rate: number;
  unsupported_claim_rate: number;
  must_not_say_violations: number;
  ship_blocked: boolean;
}
export interface EvalCaseResult {
  id: string; company: string; question: string; intent: string;
  confidence: string; computed_claims: number; unsupported: number;
  must_not_violations: string[]; passed: boolean;
  checks: Record<string, boolean>;
}
export interface EvalReport { metrics: EvalMetrics; results: EvalCaseResult[]; }

export function useEval() {
  return useSWR<EvalReport>("/api/be/dashboard/eval/run", fetcher, {
    revalidateOnFocus: false, revalidateOnMount: false,
  });
}

// ── Layer-0 data quality (canonical mapping coverage) ─────────────────────────
export interface IngestQuality {
  objects: { object_type: string; mapped: number }[];
  total_mapped: number;
  issue_count: number;
  coverage_pct: number;
  top_issues: { object_type: string; field: string; reason: string; count: number }[];
  checked_at: string;
}

export function useIngestQuality() {
  return useSWR<IngestQuality>("/api/dashboard/ingest-quality", fetcher, {
    refreshInterval: 5 * 60 * 1_000,
    revalidateOnFocus: false,
  });
}

export function useSyncHealth() {
  return useSWR<SyncHealth>("/api/dashboard/sync-health", fetcher, {
    refreshInterval: 5 * 60 * 1_000,
    revalidateOnFocus: true,
  });
}
