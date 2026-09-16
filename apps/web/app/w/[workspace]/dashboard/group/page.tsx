"use client";

import { use } from "react";
import Link from "next/link";
import useSWR from "swr";
import { AlertTriangle, ArrowRight, Inbox, ShieldAlert } from "lucide-react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { apiFetch, workspacePath } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils/cn";

/**
 * The group, on one screen.
 *
 * Sandeep does not run a company; he runs nine. A dashboard scoped to one
 * brand asks him to open it nine times and hold the comparison in his head —
 * which is the thing he already does badly and the reason this was built.
 * Ranked so the company that needs him is at the top, and every row is a link
 * into that company's own Today.
 */

interface Row {
  company_id: string;
  name: string;
  error: string | null;
  outstanding?: number;
  overdue?: number;
  overdue_pct?: number;
  cash_net_30d?: number;
  week?: number;
  week_delta_pct?: number;
  drift?: number;
  drift_building?: boolean;
  inbox?: number;
  holds?: number;
  stale?: boolean;
}

interface Group {
  companies: Row[];
  count: number;
  unreadable: number;
  totals: Record<string, number>;
  totals_cover: number;
}

async function fetcher(url: string) {
  const res = await apiFetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="surface-card p-3">
      <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{label}</p>
      <p className={cn("text-xl font-semibold tabular-nums mt-1",
        tone === "warn" ? "text-amber-300" : "text-[#F2DEC8]")}>{value}</p>
    </div>
  );
}

export default function GroupPage({ params }: { params: Promise<{ workspace: string }> }) {
  const { workspace } = use(params);
  const { data, isLoading } = useSWR<Group>("/api/be/workspaces/group", fetcher);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto w-full animate-rise space-y-5">
      <PageHeader
        title="The group"
        subtitle="Every connected company, the company that needs you first"
      />

      {isLoading && <p className="text-sm text-zinc-500">Loading…</p>}

      {data && data.count === 0 && (
        <div className="surface-card p-8 text-center">
          <p className="text-sm text-zinc-300">No connected companies yet.</p>
          <p className="text-xs text-zinc-500 mt-1">
            A company appears here once a data source is connected and synced.
          </p>
        </div>
      )}

      {data && data.count > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 items-start">
            <Stat label="Owed across the group" value={formatCurrency(data.totals.outstanding ?? 0, true)} />
            <Stat label="Of that, overdue" value={formatCurrency(data.totals.overdue ?? 0, true)} tone="warn" />
            <Stat label="Waiting on you" value={String(data.totals.inbox ?? 0)} />
            <Stat label="Accounts on hold" value={String(data.totals.holds ?? 0)} />
          </div>

          {data.unreadable > 0 && (
            <p className="text-[11.5px] text-amber-400/80 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              Totals cover {data.totals_cover} of {data.count} companies — {data.unreadable} could
              not be read. They are listed below with the reason.
            </p>
          )}

          <div className="space-y-2">
            {data.companies.map((c) => (
              <Link
                key={c.company_id}
                href={workspacePath(c.company_id, "/dashboard")}
                className="surface-card surface-card-hover p-4 flex items-center justify-between gap-4 group"
              >
                <div className="min-w-0">
                  <p className="text-[14px] font-semibold text-[#F2DEC8] flex items-center gap-2">
                    {c.name}
                    {!!c.holds && (
                      <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border border-red-400/40 text-red-300">
                        <ShieldAlert className="w-3 h-3" /> {c.holds}
                      </span>
                    )}
                    {!!c.inbox && (
                      <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border border-[#C08457]/40 text-[#C08457]">
                        <Inbox className="w-3 h-3" /> {c.inbox}
                      </span>
                    )}
                    {c.stale && <span className="text-[10px] text-amber-400/70">stale</span>}
                  </p>
                  {c.error ? (
                    <p className="text-[11.5px] text-red-300/80 mt-1">
                      Could not be read — {c.error}
                    </p>
                  ) : (
                    <p className="text-[11.5px] text-zinc-500 mt-1 tabular-nums">
                      {formatCurrency(c.outstanding ?? 0, true)} owed ·{" "}
                      <span className={cn((c.overdue_pct ?? 0) >= 50 && "text-amber-300")}>
                        {c.overdue_pct}% overdue
                      </span>{" "}
                      · last week {formatCurrency(c.week ?? 0, true)}{" "}
                      <span className={cn((c.week_delta_pct ?? 0) >= 0 ? "text-emerald-300/80" : "text-amber-300/80")}>
                        ({(c.week_delta_pct ?? 0) >= 0 ? "+" : ""}{Math.round(c.week_delta_pct ?? 0)}%)
                      </span>
                      {!c.drift_building && (c.drift ?? 0) > 0 &&
                        ` · ${formatCurrency(c.drift ?? 0, true)} slipped past 60 days`}
                    </p>
                  )}
                </div>
                <ArrowRight className="w-4 h-4 text-zinc-600 group-hover:text-[#C08457] transition shrink-0" />
              </Link>
            ))}
          </div>

          <p className="text-[11px] text-zinc-600">
            Ordered by what needs attention — overdue money first, then drift, a full
            inbox, and accounts on hold. Every figure is the same one that company&rsquo;s
            own pages show; nothing is recomputed here.
          </p>
        </>
      )}
    </div>
  );
}
