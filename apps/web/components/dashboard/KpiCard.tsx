"use client";

import { cn } from "@/lib/utils/cn";

interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
  trend?: "up" | "down" | "neutral";
  trendLabel?: string;
  accent?: "blue" | "emerald" | "amber" | "red" | "violet";
}

/* Soft accent dot colors — restrained, indigo-leaning palette. */
const DOT_CLASSES = {
  blue:    "bg-indigo-400",
  emerald: "bg-emerald-400",
  amber:   "bg-amber-400",
  red:     "bg-red-400",
  violet:  "bg-violet-400",
};

const TREND_CLASSES = {
  up:      "text-emerald-400",
  down:    "text-red-400",
  neutral: "text-zinc-500",
};

const TREND_ARROWS = { up: "↑", down: "↓", neutral: "—" };

export function KpiCard({
  label,
  value,
  sub,
  trend,
  trendLabel,
  accent = "blue",
}: KpiCardProps) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", DOT_CLASSES[accent])} />
        <span className="text-[10.5px] font-medium text-zinc-500 uppercase tracking-[0.08em] truncate">
          {label}
        </span>
      </div>
      <span className="text-[26px] leading-none font-semibold tracking-tight tabular-nums text-zinc-50">
        {value}
      </span>
      {(sub || trendLabel) && (
        <div className="flex items-center gap-1.5 mt-1">
          {trend && trendLabel && (
            <span className={cn("text-[11px] font-medium tabular-nums", TREND_CLASSES[trend])}>
              {TREND_ARROWS[trend]} {trendLabel}
            </span>
          )}
          {sub && <span className="text-[11px] text-zinc-600">{sub}</span>}
        </div>
      )}
    </div>
  );
}
