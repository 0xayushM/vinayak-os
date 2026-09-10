"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils/cn";
import { getWorkspace, workspacePath } from "@/lib/api";
import { useChatDock } from "@/components/dashboard/ChatDock";
import { draftChase, createExperiment, type PulseCard as Card } from "@/hooks/usePulse";
import {
  ArrowUpRight, ArrowDownRight, Minus, Loader2, Check, AlertTriangle, ChevronRight,
} from "lucide-react";

/**
 * One Pulse card. The same five things every time, so the page reads as one
 * object: the figure, how it compares to this business's own normal, one
 * sentence of cause, what can be done about it, and how much to trust it.
 */

const CONF_LABEL: Record<string, string> = {
  CERTAIN: "Certain", PROBABLE: "Probable", UNCERTAIN: "Not enough data",
};

function Trust({ card }: { card: Card }) {
  const c = card.confidence;
  return (
    <div className="flex items-center gap-2 text-[11px] text-zinc-500">
      <span
        title={
          c === "CERTAIN" ? "Computed from complete data"
          : c === "PROBABLE" ? "Uses an assumption or a proxy — the sentence says which"
          : "Not enough data to say"
        }
        className={cn(
          "px-1.5 py-0.5 rounded-full border text-[10px] font-semibold tracking-wide",
          c === "CERTAIN" ? "border-emerald-400/30 text-emerald-300"
          : c === "PROBABLE" ? "border-amber-300/30 text-amber-300"
          : "border-white/10 text-zinc-500",
        )}
      >
        {CONF_LABEL[c] ?? c}
      </span>
      {card.stale && (
        <span className="flex items-center gap-1 text-amber-400/80" title="Last sync is over 25 hours old">
          <AlertTriangle className="w-3 h-3" /> stale
        </span>
      )}
      {card.last_synced_at && !card.stale && (
        <span>synced {timeAgo(card.last_synced_at)}</span>
      )}
    </div>
  );
}

function timeAgo(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export function PulseCardView({ card, onChanged }: { card: Card; onChanged?: () => void }) {
  const router = useRouter();
  const dock = useChatDock();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [doneHref, setDoneHref] = useState("/dashboard/approvals");
  const [err, setErr] = useState<string | null>(null);

  const dir = card.change?.direction;
  const Arrow = dir === "good" ? ArrowUpRight : dir === "bad" ? ArrowDownRight : Minus;

  async function runAction() {
    const a = card.action;
    if (!a) return;
    setErr(null);
    try {
      if (a.kind === "open") {
        // workspacePath(null, …) drops the /w/{workspace} prefix entirely, so
        // this used to push a path outside the workspace and land wherever the
        // router could resolve it. Read the slug from the URL instead.
        router.push(workspacePath(getWorkspace(), a.params.path as string));
        return;
      }
      if (a.kind === "ask") {
        dock.ask(a.params.question as string);
        return;
      }
      setBusy(true);
      if (a.kind === "draft_chase") {
        const customers = (a.params.customers as string[]) ?? [];
        const results = await Promise.allSettled(customers.map((c) => draftChase(c)));
        const ok = results.filter((r) => r.status === "fulfilled").length;
        // The commonest reason a draft is refused is that one is already
        // waiting — the idempotency guard doing its job, not a failure. Saying
        // "nothing to draft" there was wrong and made the button look broken
        // when it had actually worked the first time.
        const queued = results.filter(
          (r) => r.status === "rejected" &&
            /already exists|idempotency/i.test(String((r.reason as Error)?.message)),
        ).length;
        const other = results.length - ok - queued;
        if (ok) {
          setDone(`${ok} draft${ok > 1 ? "s" : ""} waiting in Approvals`);
        } else if (queued) {
          setDone(`Already waiting in Approvals`);
        }
        if (other) {
          const first = results.find(
            (r) => r.status === "rejected" &&
              !/already exists|idempotency/i.test(String((r.reason as Error)?.message)),
          );
          setErr(String((first as PromiseRejectedResult | undefined)?.reason?.message
                        ?? "Could not draft those reminders."));
        }
      } else if (a.kind === "draft_nudge") {
        // The reorder engine ships with the marketing wave; until then, logging
        // it as an experiment is what makes the nudge measurable rather than
        // just sent — and it is the same record the engine will write.
        const customers = (a.params.customers as string[]) ?? [];
        await createExperiment({
          title: `Nudge ${customers.length} regulars who are overdue to order`,
          hypothesis: `Reaching out to ${customers.slice(0, 3).join(", ")}${customers.length > 3 ? " and others" : ""} recovers orders that would otherwise be skipped.`,
          source: "manual", status: "accepted",
          metric_key: a.params.metric_key as string | undefined,
          entity_ref: a.params.entity_ref as string | undefined,
          window_days: a.params.window_days as number | undefined,
        });
        setDone("Logged as an experiment");
        setDoneHref("/dashboard/experiments");
      } else if (a.kind === "experiment") {
        await createExperiment({
          title: (a.params.title as string) ?? card.title,
          hypothesis: card.why, source: "manual", status: "accepted",
          metric_key: a.params.metric_key as string | undefined,
          entity_ref: a.params.entity_ref as string | undefined,
          window_days: a.params.window_days as number | undefined,
        });
        setDone("Logged as an experiment");
        setDoneHref("/dashboard/experiments");
      }
      onChanged?.();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const urgent = card.severity >= 60;

  return (
    <div
      className={cn(
        "surface-card p-4 flex flex-col gap-3 h-full overflow-hidden",
        urgent && "border-amber-400/25",
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[10.5px] uppercase tracking-[0.1em] text-zinc-500">{card.title}</p>
        {card.change && (
          <span
            className={cn(
              "flex items-center gap-1 text-[12px] font-semibold tabular-nums shrink-0",
              dir === "good" ? "text-emerald-300" : dir === "bad" ? "text-amber-300" : "text-zinc-500",
            )}
          >
            <Arrow className="w-3.5 h-3.5" />
            {card.change.display}
          </span>
        )}
      </div>

      <div>
        <p className="text-[28px] leading-none font-semibold text-[#F2DEC8] tabular-nums">
          {card.headline.display}
        </p>
        {card.change?.label && (
          <p className="text-[11px] text-zinc-500 mt-1">{card.change.label}</p>
        )}
      </div>

      {/* Clamped so nine cards form even rows rather than a ragged wall. The
          full sentence is never longer than this in practice; the clamp is
          insurance, not truncation by design. */}
      <p className="text-[12.5px] text-zinc-400 leading-relaxed flex-1 line-clamp-4">{card.why}</p>

      {card.items.length > 0 && (
        <div className="space-y-1">
          {card.items.slice(0, 3).map((it, i) => (
            <div key={i} className="flex items-baseline justify-between gap-3 text-[11.5px] overflow-hidden">
              {/* min-w-0 is what makes truncate actually truncate: without it a
                  long label grows the span past the card and spills over the
                  card beside it. */}
              <span className="text-zinc-500 truncate min-w-0">{it.label}</span>
              <span className="text-zinc-300 tabular-nums shrink-0">{it.value}</span>
            </div>
          ))}
        </div>
      )}

      {err && <p className="text-[11.5px] text-red-400">{err}</p>}

      <div className="flex items-center justify-between gap-3 pt-1 border-t border-white/[0.05]">
        <Trust card={card} />
        {card.action && (
          done ? (
            // Whatever the button did, it happened somewhere else — so say where
            // and take them there. A confirmation with no way through is why the
            // first click felt like nothing had happened.
            <Link
              href={workspacePath(getWorkspace(), doneHref)}
              className="flex items-center gap-1 text-[11.5px] text-emerald-300 shrink-0 hover:underline"
            >
              <Check className="w-3.5 h-3.5" /> {done}
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          ) : (
            <button
              onClick={runAction}
              disabled={busy}
              className={cn(
                "flex items-center gap-1 text-[11.5px] font-medium px-2.5 py-1 rounded-lg shrink-0 transition",
                urgent
                  ? "bg-[#C08457] text-black hover:bg-[#d4a070]"
                  : "border border-white/10 text-zinc-300 hover:bg-white/[0.05]",
                busy && "opacity-40",
              )}
            >
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
              {card.action.label}
              {!busy && <ChevronRight className="w-3.5 h-3.5" />}
            </button>
          )
        )}
      </div>
    </div>
  );
}
