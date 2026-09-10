"use client";

import { Fragment } from "react";
import { ChevronRight, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils/cn";

/**
 * StageFlow — where money currently sits along one loop.
 *
 * An ERP organises screens by document type: quotes here, orders there,
 * invoices somewhere else. That tells you what exists, never where value is
 * stuck. This shows the whole loop at once — value at each stage, and the
 * amount that has stopped moving — which is the question an owner actually
 * has. Clicking a stage opens the detail for that stage only.
 */

export interface Stage {
  key: string;
  label: string;
  /** The money (or count) sitting at this stage right now. */
  value: string;
  /** What the figure is, in three or four words. */
  note?: string;
  /** Value that has stopped moving here: overdue, rejected, awaiting inspection. */
  stuck?: { label: string; value: string };
  loading?: boolean;
  /** Absent when we do not sync the data for this stage yet — said plainly. */
  missing?: string;
}

export function StageFlow({
  stages, active, onSelect,
}: {
  stages: Stage[];
  active?: string;
  onSelect?: (key: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-stretch gap-2">
      {stages.map((s, i) => (
        <Fragment key={s.key}>
          {i > 0 && (
            <div className="hidden lg:flex items-center text-zinc-700 shrink-0" aria-hidden>
              <ChevronRight className="w-4 h-4" />
            </div>
          )}
          <button
            type="button"
            onClick={() => onSelect?.(s.key)}
            disabled={!onSelect || !!s.missing}
            className={cn(
              "surface-card flex-1 min-w-[150px] p-3 text-left transition",
              onSelect && !s.missing && "hover:border-[#C08457]/40 cursor-pointer",
              active === s.key && "border-[#C08457]/60 bg-[#C08457]/[0.06]",
              s.missing && "opacity-55",
            )}
          >
            <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{s.label}</p>
            {s.missing ? (
              <>
                <p className="text-lg font-semibold text-zinc-600 mt-1">—</p>
                <p className="text-[11px] text-zinc-600 mt-0.5 leading-snug">{s.missing}</p>
              </>
            ) : (
              <>
                <p className={cn("text-xl font-semibold tabular-nums mt-1",
                  s.loading ? "text-zinc-700" : "text-[#F2DEC8]")}>
                  {s.loading ? "···" : s.value}
                </p>
                {s.note && <p className="text-[11px] text-zinc-500 mt-0.5">{s.note}</p>}
                {s.stuck && (
                  <p className="flex items-center gap-1 text-[11px] text-amber-300 mt-1.5">
                    <AlertTriangle className="w-3 h-3 shrink-0" />
                    <span className="tabular-nums">{s.stuck.value}</span>
                    <span className="text-amber-300/70">{s.stuck.label}</span>
                  </p>
                )}
              </>
            )}
          </button>
        </Fragment>
      ))}
    </div>
  );
}

/** A plain tab strip. The detail tables live behind these, one stage at a time,
 *  so a page never shows the same rows twice under different headings. */
export function Tabs({
  tabs, active, onChange,
}: {
  tabs: { key: string; label: string; count?: number }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5 border-b border-white/[0.06] pb-2">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            "text-[12px] px-3 py-1.5 rounded-lg transition",
            active === t.key
              ? "bg-[#C08457]/12 text-[#C08457] font-medium"
              : "text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.03]",
          )}
        >
          {t.label}
          {t.count != null && (
            <span className="ml-1.5 text-[10.5px] text-zinc-600 tabular-nums">{t.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

/** The one-line question a section answers, so a page reads as an argument
 *  rather than a pile of charts. */
export function SectionHead({ question, note }: { question: string; note?: string }) {
  return (
    <div className="pt-1">
      <h2 className="text-[15px] font-semibold text-[#F2DEC8]">{question}</h2>
      {note && <p className="text-[11.5px] text-zinc-500 mt-0.5">{note}</p>}
    </div>
  );
}
