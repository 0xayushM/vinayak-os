"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { cn } from "@/lib/utils/cn";
import {
  useExperiments, createExperiment, patchExperiment,
  type Experiment, type ExperimentStatus,
} from "@/hooks/useMilestones";
import { FlaskConical, Plus, Loader2, Sparkles, CheckCircle, XCircle, Play, Lock } from "lucide-react";

const inputCls =
  "bg-[var(--bg-elevated)] text-[#F2DEC8]/90 text-sm rounded-lg px-3 py-2 border border-white/[0.08] focus:border-[#C08457] focus:outline-none placeholder-zinc-600";

const STATUS_LABEL: Record<ExperimentStatus, string> = {
  proposed: "Proposed", accepted: "Accepted", running: "Running", closed: "Closed", rejected: "Rejected",
};
const STATUS_CLS: Record<ExperimentStatus, string> = {
  proposed: "text-zinc-400 border-white/10",
  accepted: "text-sky-300 border-sky-300/30",
  running:  "text-amber-300 border-amber-300/30",
  closed:   "text-emerald-300 border-emerald-300/30",
  rejected: "text-zinc-500 border-white/5",
};

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="surface-card px-4 py-3">
      <p className="text-[10.5px] uppercase tracking-[0.1em] text-zinc-500">{label}</p>
      <p className="text-2xl font-semibold text-[#F2DEC8] tabular-nums mt-0.5">{value}</p>
      {hint && <p className="text-[11px] text-zinc-500 mt-0.5">{hint}</p>}
    </div>
  );
}

export default function ExperimentsPage() {
  const [filter, setFilter] = useState<ExperimentStatus | undefined>(undefined);
  const { data, mutate, isLoading } = useExperiments(filter);
  const [busy, setBusy] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [nf, setNf] = useState({ title: "", hypothesis: "", metric: "", baseline: "", target: "", ends_at: "" });
  const [closing, setClosing] = useState<{ id: string; result: string; outcome: Experiment["outcome"]; notes: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const counts = data?.counts;
  const items = data?.experiments ?? [];

  async function onCreate() {
    if (!nf.title.trim()) return;
    setBusy("new"); setErr(null);
    try {
      await createExperiment({
        title: nf.title, hypothesis: nf.hypothesis || undefined, metric: nf.metric || undefined,
        baseline: nf.baseline !== "" ? Number(nf.baseline) : undefined,
        target: nf.target !== "" ? Number(nf.target) : undefined,
        ends_at: nf.ends_at || undefined, source: "manual", status: "accepted",
      } as Partial<Experiment> & { title: string });
      setNf({ title: "", hypothesis: "", metric: "", baseline: "", target: "", ends_at: "" });
      setShowNew(false);
      await mutate();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  }

  async function transition(id: string, status: ExperimentStatus) {
    setBusy(id); setErr(null);
    try { await patchExperiment(id, { status }); await mutate(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  }

  async function onClose() {
    if (!closing || !closing.outcome) return;
    setBusy(closing.id); setErr(null);
    try {
      await patchExperiment(closing.id, {
        status: "closed", outcome: closing.outcome,
        result: closing.result !== "" ? Number(closing.result) : undefined,
        outcome_notes: closing.notes || undefined,
      });
      setClosing(null); await mutate();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto w-full animate-rise space-y-5">
      <PageHeader title="Experiments" subtitle="Every change you try on the business, with the number it moved. Suggestions from the brain land here too.">
        <button onClick={() => setShowNew((v) => !v)}
          className="flex items-center gap-1.5 rounded-lg bg-[#C08457] text-black text-xs font-medium px-3 py-1.5">
          <Plus className="w-3.5 h-3.5" /> New experiment
        </button>
      </PageHeader>

      {counts && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Logged" value={counts.logged} />
          <Stat label="With outcomes" value={counts.with_outcomes} hint="Milestone 1 needs 30" />
          <Stat label="Running" value={counts.running} />
          <Stat label="AI-suggested" value={`${counts.ai_suggested_acted_on} / ${counts.ai_suggested}`} hint="acted on / suggested" />
        </div>
      )}

      {err && <p className="text-xs text-red-400">{err}</p>}

      {showNew && (
        <div className="surface-card p-4 space-y-3">
          <p className="text-sm font-medium text-zinc-50">New experiment</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input className={cn(inputCls, "sm:col-span-2")} placeholder="Title — e.g. Firm-tone reminders for 30+ day overdue customers" value={nf.title} onChange={(e) => setNf({ ...nf, title: e.target.value })} />
            <input className={cn(inputCls, "sm:col-span-2")} placeholder="Hypothesis — what you expect to happen and why" value={nf.hypothesis} onChange={(e) => setNf({ ...nf, hypothesis: e.target.value })} />
            <input className={inputCls} placeholder="Metric — e.g. ₹ recovered within 14 days" value={nf.metric} onChange={(e) => setNf({ ...nf, metric: e.target.value })} />
            <input className={inputCls} type="date" value={nf.ends_at} onChange={(e) => setNf({ ...nf, ends_at: e.target.value })} title="When the metric is read" />
            <input className={inputCls} placeholder="Baseline (number)" value={nf.baseline} onChange={(e) => setNf({ ...nf, baseline: e.target.value })} />
            <input className={inputCls} placeholder="Target (number)" value={nf.target} onChange={(e) => setNf({ ...nf, target: e.target.value })} />
          </div>
          <div className="flex gap-2">
            <button onClick={onCreate} disabled={busy === "new" || !nf.title.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-[#C08457] text-black text-xs font-medium px-3 py-1.5 disabled:opacity-40">
              {busy === "new" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />} Log it
            </button>
            <button onClick={() => setShowNew(false)} className="text-xs text-zinc-500 px-2">Cancel</button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        {([undefined, "proposed", "accepted", "running", "closed", "rejected"] as (ExperimentStatus | undefined)[]).map((s) => (
          <button key={s ?? "all"} onClick={() => setFilter(s)}
            className={cn("text-[11px] px-2.5 py-1 rounded-full border transition",
              filter === s ? "border-[#C08457]/60 text-[#C08457] bg-[#C08457]/10" : "border-white/10 text-zinc-500 hover:text-zinc-300")}>
            {s ? STATUS_LABEL[s] : "All"}
          </button>
        ))}
      </div>

      {isLoading && <div className="flex items-center gap-2 text-zinc-500 text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>}

      {!isLoading && items.length === 0 && (
        <div className="surface-card p-10 flex flex-col items-center text-center gap-2">
          <FlaskConical className="w-6 h-6 text-zinc-600" />
          <p className="text-sm text-zinc-400">No experiments yet.</p>
          <p className="text-xs text-zinc-600">Log the first one, or wait for the brain's weekly suggestions.</p>
        </div>
      )}

      <div className="space-y-3">
        {items.map((x) => (
          <div key={x.id} className="surface-card p-4 space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  {x.source === "ai_suggested" && <Sparkles className="w-3.5 h-3.5 text-[#C08457]" />}
                  <p className="text-sm font-semibold text-[#F2DEC8]">{x.title}</p>
                  <span className={cn("text-[10.5px] px-2 py-0.5 rounded-full border", STATUS_CLS[x.status])}>{STATUS_LABEL[x.status]}</span>
                  {x.outcome && (
                    <span className={cn("text-[10.5px] px-2 py-0.5 rounded-full border",
                      x.outcome === "positive" ? "text-emerald-300 border-emerald-300/30" :
                      x.outcome === "negative" ? "text-red-300 border-red-300/30" : "text-zinc-400 border-white/10")}>
                      {x.outcome}
                    </span>
                  )}
                </div>
                {x.hypothesis && <p className="text-[12.5px] text-zinc-400 mt-1">{x.hypothesis}</p>}
                <p className="text-[11px] text-zinc-500 mt-1">
                  {x.metric ?? "no metric"}{x.baseline != null && ` · baseline ${x.baseline}`}{x.target != null && ` · target ${x.target}`}{x.result != null && ` · result ${x.result}`}
                  {x.ends_at && ` · read on ${x.ends_at}`} · by {x.proposed_by ?? "—"}
                </p>
                {x.outcome_notes && <p className="text-[11.5px] text-zinc-400 mt-1 italic">{x.outcome_notes}</p>}
              </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {x.status === "proposed" && (<>
                <button disabled={busy === x.id} onClick={() => transition(x.id, "accepted")} className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-[#C08457]/15 text-[#C08457] border border-[#C08457]/30"><CheckCircle className="w-3.5 h-3.5" /> Accept</button>
                <button disabled={busy === x.id} onClick={() => transition(x.id, "rejected")} className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-white/10 text-zinc-400"><XCircle className="w-3.5 h-3.5" /> Reject</button>
              </>)}
              {x.status === "accepted" && (
                <button disabled={busy === x.id} onClick={() => transition(x.id, "running")} className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-[#C08457]/15 text-[#C08457] border border-[#C08457]/30"><Play className="w-3.5 h-3.5" /> Start</button>
              )}
              {(x.status === "running" || x.status === "accepted") && closing?.id !== x.id && (
                <button disabled={busy === x.id} onClick={() => setClosing({ id: x.id, result: "", outcome: null, notes: "" })} className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-white/10 text-zinc-300"><Lock className="w-3.5 h-3.5" /> Record outcome</button>
              )}
            </div>
            {closing?.id === x.id && (
              <div className="rounded-lg bg-black/25 border border-white/[0.06] p-3 grid grid-cols-1 sm:grid-cols-4 gap-2">
                <input className={inputCls} placeholder="Result (number)" value={closing.result} onChange={(e) => setClosing({ ...closing, result: e.target.value })} />
                <select className={cn(inputCls, "[color-scheme:dark]")} value={closing.outcome ?? ""} onChange={(e) => setClosing({ ...closing, outcome: (e.target.value || null) as Experiment["outcome"] })}>
                  <option value="">Outcome…</option><option value="positive">Positive</option><option value="negative">Negative</option><option value="inconclusive">Inconclusive</option>
                </select>
                <input className={cn(inputCls, "sm:col-span-2")} placeholder="What happened, in a sentence" value={closing.notes} onChange={(e) => setClosing({ ...closing, notes: e.target.value })} />
                <div className="sm:col-span-4 flex gap-2">
                  <button onClick={onClose} disabled={!closing.outcome || busy === x.id} className="rounded-lg bg-[#C08457] text-black text-xs font-medium px-3 py-1.5 disabled:opacity-40">Close experiment</button>
                  <button onClick={() => setClosing(null)} className="text-xs text-zinc-500 px-2">Cancel</button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
