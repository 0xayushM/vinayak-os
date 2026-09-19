"use client";

import { relativeTime } from "@/lib/utils/cn";
import { PanelMeta } from "@/hooks/useDashboard";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { SyncButton } from "@/components/dashboard/SyncButton";
import { ErrorState } from "@/components/ui/ErrorState";

interface PanelWrapperProps {
  title: string;
  subtitle?: string;
  meta?: PanelMeta | null;
  loading?: boolean;
  error?: Error | null;
  children: React.ReactNode;
  className?: string;
  /** Optional right-aligned actions in the header (filters, links). */
  action?: React.ReactNode;
}

export function PanelWrapper({
  title,
  subtitle,
  meta,
  loading,
  error,
  children,
  className = "",
  action,
}: PanelWrapperProps) {
  return (
    <div
      className={cn(
        "surface-card surface-card-hover flex flex-col group",
        className,
      )}
    >
      {/* Header */}
      <div className="px-5 pt-4 pb-3 flex items-start justify-between gap-3 shrink-0">
        <div className="min-w-0">
          <h3 className="text-[13px] font-semibold tracking-tight text-zinc-100 truncate">
            {title}
          </h3>
          {subtitle && (
            <p className="text-[11px] text-zinc-500 mt-0.5 truncate">{subtitle}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {action}
          {meta?.stale && <SyncButton />}
          {meta?.last_synced_at && !meta?.stale && (
            <span className="text-[10px] text-zinc-600 tabular-nums hidden sm:block">
              {relativeTime(meta.last_synced_at)}
            </span>
          )}
        </div>
      </div>

      {/* Hairline under header */}
      <div className="mx-5 h-px bg-white/[0.05] shrink-0" />

      {/* Body — a column, so a panel can let its chart or list take up the
          spare height and pin its footnote to the bottom when a grid row
          stretches every card to the same height. */}
      <div className="flex-1 px-5 py-4 min-h-0 flex flex-col">
        {loading ? (
          <div className="flex-1 flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 text-zinc-600 animate-spin" />
          </div>
        ) : error ? (
          <ErrorState error={error} compact />
        ) : (
          children
        )}
      </div>
    </div>
  );
}
