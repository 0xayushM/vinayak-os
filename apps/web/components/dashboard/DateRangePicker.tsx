"use client";

import { Calendar, X } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export interface DateRange {
  start?: string; // YYYY-MM-DD
  end?: string;   // YYYY-MM-DD
}

interface DateRangePickerProps {
  value: DateRange;
  onChange: (next: DateRange) => void;
  /** Latest date present in the data — used to label the "latest" default. */
  dataFrom?: string | null;
  dataTo?: string | null;
  className?: string;
}

/** Format an ISO date (YYYY-MM-DD) for display, tolerant of nulls. */
function pretty(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

const inputCls =
  "bg-[var(--bg-elevated)] text-zinc-200 text-xs rounded-lg px-2.5 py-1.5 border border-white/[0.08] focus:border-indigo-500 focus:outline-none [color-scheme:dark]";

export function DateRangePicker({
  value,
  onChange,
  dataFrom,
  dataTo,
  className,
}: DateRangePickerProps) {
  const active = !!(value.start || value.end);

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-center gap-2 flex-wrap">
        <Calendar className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
        <input
          type="date"
          value={value.start ?? ""}
          max={value.end ?? dataTo ?? undefined}
          onChange={(e) => onChange({ ...value, start: e.target.value || undefined })}
          className={inputCls}
          aria-label="Start date"
        />
        <span className="text-zinc-600 text-xs">→</span>
        <input
          type="date"
          value={value.end ?? ""}
          min={value.start ?? dataFrom ?? undefined}
          onChange={(e) => onChange({ ...value, end: e.target.value || undefined })}
          className={inputCls}
          aria-label="End date"
        />
        {active && (
          <button
            onClick={() => onChange({})}
            className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 border border-white/[0.08] rounded-lg px-2 py-1.5 transition-colors"
            title="Clear range — show latest available data"
          >
            <X className="w-3 h-3" /> Latest
          </button>
        )}
      </div>
      {(dataFrom || dataTo) && (
        <p className="text-[10.5px] text-zinc-600">
          {active
            ? `Showing ${pretty(value.start)} – ${pretty(value.end)}`
            : `Showing latest available · data spans ${pretty(dataFrom)} – ${pretty(dataTo)}`}
        </p>
      )}
    </div>
  );
}
