/**
 * app/api/dashboard/[panel]/route.ts
 * ────────────────────────────────────
 * BFF proxy for all dashboard panel endpoints.
 * Maps flat panel names → nested FastAPI paths, renames query params, and
 * reshapes response bodies to match the TypeScript types in hooks/useDashboard.ts.
 */
import { NextRequest, NextResponse } from "next/server";

const FASTAPI = process.env.FASTAPI_INTERNAL_URL ?? "http://localhost:8000";
const API_KEY = process.env.INTERNAL_API_KEY ?? "";

// ── Stub responses for panels with no FastAPI implementation yet ──────────────
const STUBS: Record<string, unknown> = {};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Body = Record<string, any>;

interface RouteConfig {
  path: string;
  paramMap?: Record<string, string>;
  transform?: (body: Body) => Body;
}

const ROUTES: Record<string, RouteConfig> = {
  "revenue-summary": {
    path: "/dashboard/revenue/summary",
    paramMap: { days: "period_days" },
  },

  "revenue-trend": {
    path: "/dashboard/revenue/trend",
  },

  "revenue-daily": {
    path: "/dashboard/revenue/daily",
    paramMap: { days: "period_days" },
  },

  "sales-invoices": {
    path: "/dashboard/sales/invoices",
    // passthrough: start/end/search/page/page_size/sort/direction
  },

  "ar-invoices": {
    path: "/dashboard/ar/invoices",
    // passthrough: search/bucket/overdue_only/page/page_size/sort/direction
  },

  "purchase-invoices": {
    path: "/dashboard/purchases/invoices",
  },

  "sales-orders": {
    path: "/dashboard/orders/list",
  },

  "purchase-orders": {
    path: "/dashboard/purchases/po-list",
  },

  "production-list": {
    path: "/dashboard/production/list",
  },

  "inventory-list": {
    path: "/dashboard/inventory/list",
  },

  "customer-concentration": {
    path: "/dashboard/revenue/concentration",
    paramMap: { days: "period_days" },
    transform: (body) => {
      const data: Body = body.data ?? {};
      const total: number = data.total ?? 0;
      return {
        ...body,
        data: {
          slices: (data.slices ?? []).map((s: Body) => ({
            name: s.name,
            revenue: s.value,
            pct: total > 0 ? (s.value / total) * 100 : 0,
          })),
          window_from: data.window_from ?? null,
          window_to: data.window_to ?? null,
          data_from: data.data_from ?? null,
          data_to: data.data_to ?? null,
        },
      };
    },
  },

  "top-skus": {
    path: "/dashboard/revenue/skus",
    paramMap: { days: "period_days" },
    transform: (body) => ({
      ...body,
      data: {
        skus: (body.data?.skus ?? []).map((s: Body) => ({
          sku_code: s.sku_code,
          item_name: s.sku_name,
          qty_sold: s.quantity,
          revenue: s.revenue,
        })),
        window_from: body.data?.window_from ?? null,
        window_to: body.data?.window_to ?? null,
        data_from: body.data?.data_from ?? null,
        data_to: body.data?.data_to ?? null,
      },
    }),
  },

  "purchase-summary": {
    path: "/dashboard/purchases/summary",
    paramMap: { days: "period_days" },
    transform: (body) => {
      const data: Body = body.data ?? {};
      return {
        ...body,
        data: {
          period_total: data.period_spend ?? 0,
          // Both bases (BUG 1 fix): goods = SUM(line_total), invoiced = per-invoice header.
          period_total_goods: data.period_spend_goods ?? data.period_spend ?? 0,
          period_total_invoiced: data.period_spend_invoiced ?? 0,
          invoice_count: data.invoice_count ?? 0,
          vendor_count: data.vendor_count ?? 0,
          // True trailing-12-month average computed in SQL — NOT the 30-day total.
          monthly_avg: data.monthly_avg ?? 0,
          monthly_avg_invoiced: data.monthly_avg_invoiced ?? 0,
          window_from: data.window_from ?? null,
          window_to: data.window_to ?? null,
        },
      };
    },
  },

  "top-vendors": {
    path: "/dashboard/purchases/vendors",
    paramMap: { days: "period_days" },
  },

  "quote-summary": {
    path: "/dashboard/quotes/summary",
    paramMap: { days: "period_days" },
  },

  "grn-summary": {
    path: "/dashboard/grn/summary",
    paramMap: { days: "period_days" },
  },

  "bom-coverage": {
    path: "/dashboard/bom/coverage",
  },

  "ar-summary": {
    path: "/dashboard/ar/aging",
    transform: (body) => {
      const data: Body = body.data ?? {};
      const total: number = data.total_outstanding ?? 0;
      const overdue: number = data.overdue_value ?? 0;
      return {
        ...body,
        data: {
          total_outstanding: total,
          overdue_amount: overdue,
          overdue_pct: total > 0 ? overdue / total : 0,
          buckets: (data.aging_buckets ?? []).map((b: Body) => ({
            bucket: b.bucket,
            amount: b.value,
            invoice_count: b.count,
            overdue_days_avg: 0,
          })),
        },
      };
    },
  },

  "open-orders": {
    path: "/dashboard/orders/summary",
    transform: (body) => ({
      ...body,
      data: {
        open_count: body.data?.open_order_count ?? 0,
        open_value: body.data?.open_order_value ?? 0,
        oldest_order_days: 0,
        by_status: [],
      },
    }),
  },

  "open-pos": {
    path: "/dashboard/purchases/open-pos",
    // Backend already returns open vs overdue as distinct figures plus a
    // by-vendor breakdown — pass through unchanged.
  },

  "inventory-summary": {
    path: "/dashboard/inventory/summary",
    transform: (body) => ({
      ...body,
      data: {
        total_value: body.data?.total_value ?? 0,
        total_skus: body.data?.total_skus ?? 0,
        low_stock_count: 0,
        zero_stock_count: body.data?.negative_stock_count ?? 0,
      },
    }),
  },

  "inventory-by-category": {
    path: "/dashboard/inventory/categories",
    transform: (body) => {
      const cats: Body[] = body.data?.categories ?? [];
      return {
        ...body,
        data: {
          total_value: cats.reduce((s, c) => s + (c.total_value ?? 0), 0),
          categories: cats.map((c) => ({
            category: c.category,
            value: c.total_value,
            sku_count: c.sku_count,
          })),
        },
      };
    },
  },

  "production-summary": {
    path: "/dashboard/production/summary",
    paramMap: { days: "period_days" },
    transform: (body) => ({
      ...body,
      data: {
        wip_count: body.data?.wip_count ?? 0,
        wip_value: 0,
        completed_count: body.data?.completed_count ?? 0,
        avg_cycle_days: 0,
      },
    }),
  },

  "ingest-quality": {
    path: "/dashboard/ingest/quality",
    // Raw passthrough (no envelope) — Layer-0 canonical mapping coverage.
  },

  "sync-health": {
    path: "/dashboard/sync/health",
    // FastAPI returns raw (no envelope); we reshape to SyncHealth.
    transform: (body) => {
      const pipelines: Body[] = body.pipelines ?? [];
      const stale = pipelines
        .filter((p) => p.stale)
        .map((p) => p.pipeline_name as string);
      return {
        runs: pipelines.map((p) => ({
          pipeline_name: p.pipeline_name,
          status:        p.status,
          started_at:    null,
          completed_at:  p.completed_at,
          rows_upserted: p.rows_upserted,
          error_message: p.error_message,
        })),
        stale_pipelines: stale,
        healthy: stale.length === 0,
      };
    },
  },
};

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ panel: string }> },
) {
  const { panel } = await params;

  if (panel in STUBS) {
    return NextResponse.json(STUBS[panel]);
  }

  const config = ROUTES[panel];
  if (!config) {
    return NextResponse.json({ detail: `Unknown panel: ${panel}` }, { status: 404 });
  }

  // Translate query params
  const outParams = new URLSearchParams();
  for (const [key, value] of request.nextUrl.searchParams.entries()) {
    outParams.set(config.paramMap?.[key] ?? key, value);
  }
  const qs = outParams.toString() ? `?${outParams}` : "";
  const upstream = `${FASTAPI}${config.path}${qs}`;

  try {
    const res = await fetch(upstream, {
      headers: {
        "X-Internal-Key": API_KEY,
        "X-Workspace-Id": request.headers.get("x-workspace-id") ?? "",
        Cookie: request.headers.get("cookie") ?? "",
      },
      cache: "no-store",
    });

    const body = await res.json() as Body;

    if (!res.ok) {
      return NextResponse.json(body, { status: res.status });
    }

    const out = config.transform ? config.transform(body) : body;
    return NextResponse.json(out, {
      status: 200,
      headers: {
        // Responses are workspace-scoped via the X-Workspace-Id header, which is
        // NOT part of the URL. A shared/url-keyed cache would serve one brand's
        // data for another, so we never store these responses.
        "Cache-Control": "no-store",
        Vary: "X-Workspace-Id, Cookie",
      },
    });
  } catch (err) {
    console.error(`[BFF] /api/dashboard/${panel} upstream error:`, err);
    return NextResponse.json({ detail: "Upstream service unavailable" }, { status: 503 });
  }
}
