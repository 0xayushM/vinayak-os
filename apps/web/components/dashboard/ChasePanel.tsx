"use client";

import { useState } from "react";
import { CalendarClock, ShieldAlert, Loader2, Check } from "lucide-react";
import {
  useChaseList, useRecovery, recordPromise, setDispute, type ChaseRow,
} from "@/hooks/useCollections";
import { formatCurrency } from "@/lib/utils/cn";
import { cn } from "@/lib/utils/cn";
import { useFlags, FlagBadge } from "@/components/dashboard/CreditFlag";

/**
 * The chase list, both halves.
 *
 * Who to call, ranked by what the call is likely to recover — amount times
 * lateness weighted by how this customer actually behaves, not amount alone.
 * And underneath, who is deliberately NOT being chased and why. A collections
 * screen that shows only the first half looks like it has lost the rest.
 *
 * The two buttons are the whole point. "They promised" and "they dispute it"
 * are the facts that make the next chase right, and they take ten seconds to
 * record while the call is still fresh.
 */

const RUNG_STYLE: Record<number, string> = {
  1: "border-white/15 text-zinc-400",
  2: "border-amber-300/30 text-amber-300",
  3: "border-orange-400/40 text-orange-300",
  4: "border-red-400/40 text-red-300",
};

function PromiseButton({ customer, onDone }: { customer: string; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!when) return;
    setBusy(true);
    try { await recordPromise({ customer_ref: customer, promised_on: when }); onDone(); setOpen(false); }
    finally { setBusy(false); }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="Record a promise to pay — chasing pauses until then"
        className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-white/10 text-zinc-400 hover:text-[#C08457] hover:bg-white/[0.04] transition"
      >
        <CalendarClock className="w-3 h-3" /> Promised
      </button>
    );
  }
  return (
    <span className="flex items-center gap-1">
      <input
        type="date"
        value={when}
        onChange={(e) => setWhen(e.target.value)}
        className="bg-black/30 border border-white/10 rounded-lg px-2 py-1 text-[11px] text-zinc-200"
      />
      <button onClick={save} disabled={busy || !when}
        className="text-[11px] px-2 py-1 rounded-lg bg-[#C08457] text-black disabled:opacity-40">
        {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
      </button>
    </span>
  );
}

function Row({ r, held, onChanged }: { r: ChaseRow; held?: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const { data: flagged } = useFlags();
  async function dispute() {
    setBusy(true);
    try { await setDispute(r.customer_name, true); onChanged(); }
    finally { setBusy(false); }
  }
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-black/20 border border-white/[0.05] px-3 py-2">
      <div className="min-w-0">
        <p className="text-[12.5px] text-zinc-200 truncate flex items-center gap-2">
          {!held && r.rung > 0 && (
            <span className={cn("shrink-0 text-[10px] px-1.5 py-0.5 rounded-full border",
              RUNG_STYLE[r.rung] ?? RUNG_STYLE[1])}>R{r.rung}</span>
          )}
          {r.customer_name}
          <FlagBadge flag={flagged?.flags?.[r.customer_name]} compact />
        </p>
        <p className="text-[11px] text-zinc-500 mt-0.5 tabular-nums">
          {formatCurrency(r.outstanding, true)} · {r.days_overdue} days overdue
          {held ? ` · ${r.reason}` : r.rung_label ? ` · ${r.rung_label}` : ""}
        </p>
      </div>
      {!held && (
        <div className="flex items-center gap-1.5 shrink-0">
          <PromiseButton customer={r.customer_name} onDone={onChanged} />
          <button
            onClick={dispute}
            disabled={busy}
            title="Mark disputed — stops automatic chasing"
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-white/10 text-zinc-500 hover:text-amber-300 hover:bg-white/[0.04] transition disabled:opacity-40"
          >
            <ShieldAlert className="w-3 h-3" /> Disputed
          </button>
        </div>
      )}
    </div>
  );
}

export function ChasePanel() {
  const { data, isLoading, mutate } = useChaseList();
  const recovery = useRecovery();
  if (isLoading) return <p className="text-sm text-zinc-500">Loading…</p>;
  if (!data) return null;
  const rec = recovery.data;

  return (
    <div className="space-y-4">
      {rec && !rec.no_history && rec.measurable > 0 && (
        <div className="surface-card p-4">
          <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">
            Recovered within {rec.window_days} days of a reminder
          </p>
          <p className="text-2xl font-semibold text-[#F2DEC8] tabular-nums mt-1">
            {formatCurrency(rec.recovered, true)}
            <span className="text-[13px] text-zinc-500 font-normal ml-2">
              {rec.recovery_rate_pct}% of {formatCurrency(rec.chased_value, true)} chased
            </span>
          </p>
          <p className="text-[11px] text-zinc-600 mt-1">{rec.caveat}</p>
        </div>
      )}

      <div>
        <h3 className="text-[13px] font-semibold text-[#F2DEC8]">
          Chase these, in this order
        </h3>
        <p className="text-[11.5px] text-zinc-500 mt-0.5">
          {data.due_count} accounts · {formatCurrency(data.due_value, true)} — ranked by
          what the call is likely to recover, not by size.
        </p>
        <div className="space-y-1.5 mt-3">
          {data.due.length === 0
            ? <p className="text-[12.5px] text-zinc-600">Nobody is due a reminder today.</p>
            : data.due.map((r) => <Row key={r.customer_name} r={r} onChanged={() => mutate()} />)}
        </div>
      </div>

      {data.held_count > 0 && (
        <div>
          <h3 className="text-[13px] font-semibold text-zinc-400">
            Deliberately left alone
          </h3>
          <p className="text-[11.5px] text-zinc-500 mt-0.5">
            {data.held_count} accounts · {formatCurrency(data.held_value, true)} — promised,
            paused, disputed, or chased too recently.
          </p>
          <div className="space-y-1.5 mt-3">
            {data.held.map((r) => (
              <Row key={r.customer_name} r={r} held onChanged={() => mutate()} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
