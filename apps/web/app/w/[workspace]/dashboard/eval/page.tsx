"use client";

import { useEval } from "@/hooks/useDashboard";
import { ShieldCheck, ShieldAlert, Play, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils/cn";

function Metric({ label, value, good, hint }: { label: string; value: string; good: boolean; hint?: string }) {
  return (
    <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5">
      <p className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</p>
      <p className={cn("text-lg font-semibold tabular-nums", good ? "text-[#d4a070]" : "text-amber-400")}>{value}</p>
      {hint && <p className="text-[10px] text-zinc-600 mt-0.5">{hint}</p>}
    </div>
  );
}

export default function EvalPage() {
  const { data, error, isLoading, mutate } = useEval();
  const m = data?.metrics;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-3xl mx-auto w-full animate-rise">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {m && !m.ship_blocked ? <ShieldCheck className="w-5 h-5 text-[#d4a070]" /> : <ShieldAlert className="w-5 h-5 text-[#C08457]" />}
          <div>
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-zinc-50">Answer quality (eval)</h1>
            <p className="text-[12.5px] text-zinc-500 mt-0.5">
              The golden test set. The lethal metric is <em>unsupported-claim rate</em> — it must stay at 0.
            </p>
          </div>
        </div>
        <button onClick={() => mutate()} disabled={isLoading}
          className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg bg-[#C08457]/15 text-[#C08457] border border-[#C08457]/30 hover:bg-[#C08457]/20 disabled:opacity-60 transition-colors">
          {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          {data ? "Re-run" : "Run eval"}
        </button>
      </div>

      {error && <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error.message}</div>}
      {!data && !isLoading && <p className="text-xs text-zinc-600">Click “Run eval” to evaluate the reasoning engine against the golden set.</p>}
      {isLoading && <div className="flex items-center gap-2 text-zinc-500 text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Running cases…</div>}

      {m && (
        <>
          <div className={cn("rounded-xl border px-4 py-3 flex items-center gap-3 text-sm font-medium",
            m.ship_blocked ? "bg-red-500/10 border-red-500/20 text-red-400" : "bg-[#C08457]/10 border-[#C08457]/20 text-[#d4a070]")}>
            {m.ship_blocked ? <ShieldAlert className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
            {m.ship_blocked
              ? "SHIP BLOCKED — the engine stated something it can't support."
              : `Clean — ${m.passed}/${m.cases_run} cases passed, no unsupported claims.`}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <Metric label="Cases passed" value={`${m.passed}/${m.cases_run}`} good={m.passed === m.cases_run} />
            <Metric label="Unsupported-claim rate" value={`${(m.unsupported_claim_rate * 100).toFixed(1)}%`} good={m.unsupported_claim_rate === 0} hint="must be 0" />
            <Metric label="Correct refusals" value={`${(m.correct_refusal_rate * 100).toFixed(0)}%`} good={m.correct_refusal_rate >= 0.99} hint="said “I can’t” when it should" />
            <Metric label="Confidence accuracy" value={`${(m.bucket_accuracy * 100).toFixed(0)}%`} good={m.bucket_accuracy >= 0.9} />
            <Metric label="Intent accuracy" value={`${(m.intent_accuracy * 100).toFixed(0)}%`} good={m.intent_accuracy >= 0.9} />
            <Metric label="Forbidden phrases" value={String(m.must_not_say_violations)} good={m.must_not_say_violations === 0} />
          </div>

          <div className="surface-card overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.07] text-zinc-500">
                  <th className="text-left px-3 py-2 font-medium">Case</th>
                  <th className="text-left px-3 py-2 font-medium">Brand</th>
                  <th className="text-left px-3 py-2 font-medium">Intent</th>
                  <th className="text-left px-3 py-2 font-medium">Confidence</th>
                  <th className="text-center px-3 py-2 font-medium">Result</th>
                </tr>
              </thead>
              <tbody>
                {data!.results.map((r, i) => (
                  <tr key={i} className="border-b border-white/[0.04] last:border-0">
                    <td className="px-3 py-2 text-[#F2DEC8]/75">{r.id}</td>
                    <td className="px-3 py-2 text-zinc-500">{r.company}</td>
                    <td className="px-3 py-2 font-mono text-zinc-400">{r.intent}</td>
                    <td className="px-3 py-2 text-zinc-400">{r.confidence}</td>
                    <td className="px-3 py-2 text-center">
                      {r.passed
                        ? <CheckCircle2 className="w-3.5 h-3.5 text-[#d4a070] inline" />
                        : <XCircle className="w-3.5 h-3.5 text-red-400 inline" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
