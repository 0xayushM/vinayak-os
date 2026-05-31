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

/* Soft accent dot colors — edhway copper palette. */
const DOT_CLASSES = {
  blue:    "bg-[#C08457]",
  emerald: "bg-[#d4a070]",
  amber:   "bg-[#C08457]",
  red:     "bg-red-400",
  violet:  "bg-[#C4977A]",
};

const TREND_CLASSES = {
  up:      "text-[#d4a070]",
  down:    "text-red-400",
  neutral: "text-[#7a6055]",
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
    <div className="flex flex-col gap-1 h-full">
      <div className="flex items-center gap-1.5">
        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", DOT_CLASSES[accent])} />
        <span className="text-[10.5px] font-medium text-[#7a6055] uppercase tracking-[0.08em] truncate">
          {label}
        </span>
      </div>
      <span className="text-[26px] leading-none font-semibold tracking-tight tabular-nums text-[#F2DEC8]">
        {value}
      </span>
      {/* Always reserve the sub-line row so cards with and without a sub label
          keep their value baselines aligned across a row. */}
      <div className="flex items-center gap-1.5 mt-1 min-h-[16px]">
        {trend && trendLabel && (
          <span className={cn("text-[11px] font-medium tabular-nums", TREND_CLASSES[trend])}>
            {TREND_ARROWS[trend]} {trendLabel}
          </span>
        )}
        {sub && <span className="text-[11px] text-[#7a6055]">{sub}</span>}
      </div>
    </div>
  );
}
