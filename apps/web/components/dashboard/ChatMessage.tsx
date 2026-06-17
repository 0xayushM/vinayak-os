"use client";

import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  Sparkles, CheckCircle2, AlertTriangle, HelpCircle, Database, Lightbulb, Loader2, Check,
} from "lucide-react";
import { addFact, type AskResponse, type AnswerChart } from "@/hooks/useDashboard";
import { MarkdownLite } from "@/components/dashboard/MarkdownLite";
import { cn } from "@/lib/utils/cn";

const CONF = {
  CERTAIN:   { cls: "bg-[#C08457]/15 text-[#d4a070] border-[#C08457]/30", icon: CheckCircle2, label: "Certain" },
  PROBABLE:  { cls: "bg-amber-500/10 text-amber-300 border-amber-500/25", icon: AlertTriangle, label: "Probable" },
  UNCERTAIN: { cls: "bg-zinc-500/10 text-zinc-300 border-zinc-500/25", icon: HelpCircle, label: "Uncertain" },
} as const;

const BAR_COLORS = ["#C08457", "#d4a070", "#C4977A", "#8a6050", "#e0c8b0", "#a87a55"];

export function ChartBlock({ chart }: { chart: AnswerChart }) {
  const data = chart.items.filter((d) => typeof d.value === "number" && d.value > 0).slice(0, 6);
  if (data.length < 2) return null;
  return (
    <div className="mt-3 border-t border-white/[0.06] pt-3">
      <p className="text-[10px] text-zinc-500 uppercase tracking-wide mb-1">{chart.title}</p>
      <ResponsiveContainer width="100%" height={Math.max(90, data.length * 26)}>
        <BarChart data={data} layout="vertical" margin={{ left: 0, right: 12, top: 0, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={120} tick={{ fill: "#C4977A", fontSize: 10 }}
            axisLine={false} tickLine={false}
            tickFormatter={(v: string) => (v.length > 16 ? v.slice(0, 15) + "…" : v)} />
          <Tooltip
            contentStyle={{ background: "rgba(14,14,18,0.95)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#C4977A" }}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            formatter={(v: any, _n: any, p: any) => [p?.payload?.display ?? v, ""]} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {data.map((_, i) => <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function TeachCard({ resp, onTaught }: { resp: AskResponse; onTaught: () => void }) {
  const sf = resp.suggested_fact!;
  const [val, setVal] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  async function save() {
    if (!val.trim()) return;
    setSaving(true);
    try {
      const raw = val.trim();
      const claim_value: unknown = !Number.isNaN(Number(raw)) ? Number(raw) : raw;
      await addFact({ entity_type: sf.entity_type, entity_ref: sf.entity_ref, claim_key: sf.claim_key, claim_value, origin: "user_confirmed" });
      setDone(true); onTaught();
    } finally { setSaving(false); }
  }
  if (done) return <div className="mt-3 flex items-center gap-1.5 text-[11px] text-[#d4a070]"><Check className="w-3.5 h-3.5" /> Got it — I&apos;ll remember that.</div>;
  return (
    <div className="mt-3 rounded-lg border border-[#C08457]/25 bg-[#C08457]/[0.06] p-3">
      <div className="flex items-center gap-1.5 text-[11px] text-[#C08457] mb-2"><Lightbulb className="w-3.5 h-3.5" /> Teach me: {sf.prompt}</div>
      <div className="flex gap-2">
        <input value={val} onChange={(e) => setVal(e.target.value)} onKeyDown={(e) => e.key === "Enter" && save()}
          placeholder="your answer"
          className="flex-1 bg-[var(--bg-elevated)] text-[#F2DEC8]/90 text-xs rounded-lg px-3 py-1.5 border border-white/[0.08] focus:border-[#C08457] focus:outline-none" />
        <button onClick={save} disabled={saving || !val.trim()}
          className="text-xs px-3 py-1.5 rounded-lg bg-[#C08457]/15 text-[#C08457] border border-[#C08457]/30 hover:bg-[#C08457]/20 disabled:opacity-50 transition-colors">
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Save"}
        </button>
      </div>
    </div>
  );
}

export function AnswerCard({ a, taught, onTaught }: { a: AskResponse; taught?: boolean; onTaught: () => void }) {
  const conf = CONF[a.confidence_level];
  const ConfIcon = conf.icon;
  return (
    <div className="surface-card p-3.5 space-y-2">
      {/* Full-width answer */}
      <MarkdownLite text={a.answer} />

      {a.chart && <ChartBlock chart={a.chart} />}

      {a.what_i_dont_know.length > 0 && (
        <div className="text-[11px] text-zinc-500 border-t border-white/[0.06] pt-2">
          <span className="text-zinc-400">What I don&apos;t know: </span>{a.what_i_dont_know.join(" ")}
        </div>
      )}

      {a.suggested_fact && !taught && <TeachCard resp={a} onTaught={onTaught} />}

      {/* Footer: data source on the left, tags on a single row to the right */}
      <div className="flex items-center justify-between gap-2 flex-wrap border-t border-white/[0.06] pt-2">
        <div className="flex items-center gap-1.5 text-[10px] text-zinc-600 min-w-0">
          {a.data_used.length > 0 && (
            <><Database className="w-3 h-3 shrink-0" /> <span className="truncate">from: {a.data_used.join(", ")}</span></>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {a.meta?.phrased_by === "claude" && (
            <span className="inline-flex items-center gap-1 text-[10px] text-[#C08457] border border-[#C08457]/25 rounded-full px-1.5 py-0.5"
              title={`Worded by Claude (${a.meta.tier === "smart" ? "Sonnet" : "Haiku"}) from validated numbers`}>
              <Sparkles className="w-2.5 h-2.5" /> {a.meta.tier === "smart" ? "Sonnet" : "Haiku"}
            </span>
          )}
          <span className={cn("inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border", conf.cls)}>
            <ConfIcon className="w-3 h-3" /> {conf.label}
          </span>
        </div>
      </div>
    </div>
  );
}
