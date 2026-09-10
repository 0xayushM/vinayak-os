"use client";

import { use } from "react";
import Link from "next/link";
import { Loader2, Inbox, Plug, RefreshCw, ArrowRight } from "lucide-react";
import { workspacePath } from "@/lib/api";
import { usePulse } from "@/hooks/usePulse";
import { useMe } from "@/hooks/useMilestones";
import { PulseCardView } from "@/components/dashboard/PulseCard";

/**
 * Today — the landing page.
 *
 * A card is here only if it names a delta, a cause or a decision. Everything
 * that is merely a number lives one click down, under Explore. The order is
 * the reader's role, with anything urgent lifted to the top.
 */
export default function TodayPage({ params }: { params: Promise<{ workspace: string }> }) {
  const { workspace } = use(params);
  const { data, error, isLoading, mutate, isValidating } = usePulse();
  const { data: me } = useMe();

  const greeting = (() => {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  })();
  const who = me?.display_name ? `, ${me.display_name.split(" ")[0]}` : "";

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto w-full animate-rise space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-zinc-50">
            {greeting}{who}
          </h1>
          <p className="text-[12.5px] text-zinc-500 mt-1">
            {decodeURIComponent(workspace)} ·{" "}
            {data?.no_data
              ? "waiting for your first sync"
              : data?.needs_attention
              ? `${data.needs_attention} thing${data.needs_attention > 1 ? "s" : ""} need your attention`
              : "nothing urgent today"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={workspacePath(workspace, "/dashboard/approvals")}
            className="flex items-center gap-1.5 text-[11.5px] px-2.5 py-1.5 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/[0.05] transition"
          >
            <Inbox className="w-3.5 h-3.5" /> Approvals
          </Link>
          <button
            onClick={() => mutate()}
            disabled={isValidating}
            className="flex items-center gap-1.5 text-[11.5px] px-2.5 py-1.5 rounded-lg border border-white/10 text-zinc-400 hover:bg-white/[0.05] transition disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isValidating ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-zinc-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" /> Reading your business…
        </div>
      )}

      {error && (
        <div className="surface-card p-6 text-sm text-zinc-400">
          Could not load the Pulse: {String(error.message)}
        </div>
      )}

      {data?.no_data && (
        <div className="surface-card p-10 flex flex-col items-center text-center gap-3">
          <Plug className="w-6 h-6 text-zinc-600" />
          <p className="text-sm text-zinc-300">Nothing to show yet.</p>
          <p className="text-xs text-zinc-500 max-w-sm">
            Connect a data source and run the first sync. The cards fill in as pages land, and the
            morning brief starts the next day.
          </p>
          <Link
            href={workspacePath(workspace, "/dashboard/settings")}
            className="mt-1 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#C08457] text-black text-xs font-medium"
          >
            Connect a source <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}

      {data && !data.no_data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {data.cards.map((c) => (
              <PulseCardView key={c.key} card={c} onChanged={() => mutate()} />
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <p className="text-[11.5px] text-zinc-600">
              Compared against this business&rsquo;s own history, not a calendar period.
              Every figure traces to a synced source.
            </p>
            <Link
              href={workspacePath(workspace, "/dashboard/overview")}
              className="flex items-center gap-1 text-[11.5px] text-zinc-400 hover:text-[#F2DEC8] transition"
            >
              Explore the detail <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {data.failed.length > 0 && (
            <p className="text-[11px] text-amber-400/70">
              {data.failed.length} card{data.failed.length > 1 ? "s" : ""} could not be built
              ({data.failed.join(", ")}) — the rest are unaffected.
            </p>
          )}
        </>
      )}
    </div>
  );
}
