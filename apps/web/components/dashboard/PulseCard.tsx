"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils/cn";
import { workspacePath } from "@/lib/api";
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
  const [err, setErr] = useState<string | null>(null);

  const dir = card.change?.direction;
  const Arrow = dir === "good" ? ArrowUpRight : dir === "bad" ? ArrowDownRight : Minus;

  async function runAction() {
    const a = card.action;
    if (!a) return;
    setErr(null);
    try {
      if (a.kind === "open") {
        router.push(workspacePath(null, "") + (a.params.path as string));
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
        const failed = results.length - ok;
        setDone(ok ? `${ok} draft${ok > 1 ? "s" : ""} waiting in Approvals` : null);
        if (!ok && failed) setErr("Nothing to draft — those balances may already be settled.");
      } else if (a.kind === "draft_nudge") {
        // The reorder engine ships with the marketing wave; until then, logging
        // it as an experiment is what makes the nudge measurable rather than
        // just sent — and it is the same record the engine will write.
        const customers = (a.params.customers as string[]) ?? [];
        await createExperiment({
          title: `Nudge ${customers.length} regulars who are overdue to order`,
          hypothesis: `Reaching out to ${customers.slice(0, 3).join(", ")}${customers.length > 3 ? " and others" : ""} recovers orders that would otherwise be skipped.`,
          metric: "Orders recovered from nudged customers within 30 days",
          source: "manual", status: "accepted",
        });
        setDone("Logged as an experiment");
      } else if (a.kind === "experiment") {
        await createExperiment({
          title: (a.params.title as string) ?? card.title,
          metric: (a.params.metric as string) ?? undefined,
          hypothesis: card.why, source: "manual", status: "accepted",
        });
        setDone("Logged as an experiment");
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
        "surface-card p-4 flex flex-col gap-3 h-full",
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

      <p className="text-[12.5px] text-zinc-400 leading-relaxed flex-1">{card.why}</p>

      {card.items.length > 0 && (
        <div className="space-y-1">
          {card.items.slice(0, 3).map((it, i) => (
            <div key={i} className="flex items-baseline justify-between gap-3 text-[11.5px]">
              <span className="text-zinc-500 truncate">{it.label}</span>
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
            <span className="flex items-center gap-1 text-[11.5px] text-emerald-300 shrink-0">
              <Check className="w-3.5 h-3.5" /> {done}
            </span>
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
