"use client";

import { useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { cn } from "@/lib/utils/cn";
import {
  useMilestoneBoard, saveMilestoneSettings, useIncidents, createIncident, patchIncident,
  useWorkspaceUsers, type Criterion, type UsageStats, type Incident,
} from "@/hooks/useMilestones";
import { Loader2, CheckCircle2, Circle, AlertTriangle, Clock, Save } from "lucide-react";

const inputCls =
  "bg-[var(--bg-elevated)] text-[#F2DEC8]/90 text-sm rounded-lg px-3 py-2 border border-white/[0.08] focus:border-[#C08457] focus:outline-none placeholder-zinc-600";

function StatusIcon({ s }: { s: Criterion["status"] }) {
  if (s === "met") return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
  if (s === "at_risk") return <AlertTriangle className="w-4 h-4 text-red-400" />;
  if (s === "in_progress") return <Clock className="w-4 h-4 text-amber-300" />;
  return <Circle className="w-4 h-4 text-zinc-600" />;
}

function Bar({ value, target }: { value: number; target: number }) {
  const pct = Math.max(0, Math.min(100, (value / target) * 100));
  return (
    <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
      <div className={cn("h-full rounded-full", pct >= 100 ? "bg-emerald-400" : "bg-[#C08457]")} style={{ width: `${pct}%` }} />
    </div>
  );
}

function UsageWeeks({ u }: { u: UsageStats }) {
  return (
    <div className="mt-2">
      <div className="flex gap-1 flex-wrap">
        {u.weeks.map((w) => (
          <div key={w.week_start} title={`${w.week_start}: ${w.active_days} active days`}
            className={cn("w-7 h-7 rounded text-[10px] flex items-center justify-center tabular-nums border",
              w.qualifies ? "bg-emerald-400/20 border-emerald-400/40 text-emerald-200" :
              w.partial ? "border-dashed border-white/20 text-zinc-400" : "bg-red-400/10 border-red-400/30 text-red-200")}>
            {w.active_days}
          </div>
        ))}
      </div>
      <p className="text-[11px] text-zinc-500 mt-1.5">
        Each box is a week (Mon–Sun) with its active days; green = 4 or more. Current run {u.current_run_weeks} weeks · best run {u.best_run_days} days · last active {u.last_active ?? "never"}.
      </p>
    </div>
  );
}

export default function MilestonesPage() {
  const { data, error, isLoading, mutate } = useMilestoneBoard();
  const users = useWorkspaceUsers();
  const inc = useIncidents();
  const [startDate, setStartDate] = useState<string>("");
  const [tracked, setTracked] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [newInc, setNewInc] = useState({ severity: "major" as Incident["severity"], title: "", detail: "" });

  if (isLoading) return <div className="p-8 flex items-center gap-2 text-zinc-500 text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>;
  if (error) return <div className="p-8 text-sm text-zinc-400">{String(error.message)}. This page is for owners and admins.</div>;
  if (!data) return null;

  const d = data.dates;

  async function onSaveSettings() {
    setSaving(true);
    try {
      await saveMilestoneSettings({
        milestone_start_date: startDate || undefined,
        milestone_user_email: tracked || undefined,
      });
      await mutate();
    } finally { setSaving(false); }
  }

  async function onAddIncident() {
    if (!newInc.title.trim()) return;
    await createIncident(newInc);
    setNewInc({ severity: "major", title: "", detail: "" });
    await inc.mutate(); await mutate();
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto w-full animate-rise space-y-6">
      <PageHeader title="Milestone board" subtitle="Milestone 1 — the six criteria, with the live number behind each. Evidence, not assertion." />

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-center">
        {[
          ["Start", d.start], ["Month-3 demo", d.month_3_demo], ["Month-6 review", d.month_6_review],
          ["Latest (month 8)", d.month_8_latest], ["Days to month 6", String(d.days_to_month_6)],
        ].map(([l, v]) => (
          <div key={l} className="surface-card px-3 py-2.5">
            <p className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{l}</p>
            <p className="text-sm font-semibold text-[#F2DEC8] tabular-nums mt-0.5">{v}</p>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        {data.criteria.map((c) => (
          <div key={c.key} className="surface-card p-4">
            <div className="flex items-start gap-3">
              <div className="mt-0.5"><StatusIcon s={c.status} /></div>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="text-sm font-semibold text-[#F2DEC8]">{c.title}</p>
                  {c.value != null && c.target != null && (
                    <p className="text-sm tabular-nums text-zinc-300 shrink-0">{c.value} <span className="text-zinc-600">/ {c.target}</span></p>
                  )}
                </div>
                <p className="text-[11.5px] text-zinc-500 mt-0.5">{c.detail}</p>
                {c.value != null && c.target != null && c.key !== "incidents" && <div className="mt-2"><Bar value={c.value} target={c.target} /></div>}
                {c.key === "usage" && c.extra ? <UsageWeeks u={c.extra as UsageStats} /> : null}
                {c.key === "eval" && Array.isArray(c.extra) && (c.extra as { runner: string; ran_at: string; cases_run: number; passed: number; citation_compliance: number; factual_accuracy: number | null }[]).length > 0 && (
                  <div className="mt-2 text-[11.5px] text-zinc-400 space-y-0.5">
                    {(c.extra as { runner: string; ran_at: string; cases_run: number; passed: number; citation_compliance: number; factual_accuracy: number | null }[]).map((e) => (
                      <p key={e.runner}>
                        <span className="text-zinc-300">{e.runner}</span> · {e.passed}/{e.cases_run} passed · citation {Math.round(e.citation_compliance * 100)}% · factual {e.factual_accuracy == null ? "not graded yet" : `${Math.round(e.factual_accuracy * 100)}%`} · {e.ran_at.slice(0, 10)}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Settings */}
      <div className="surface-card p-4 space-y-3">
        <p className="text-sm font-medium text-zinc-50">Board settings</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-[10.5px] uppercase tracking-wide text-zinc-500">Start date</span>
            <input type="date" className={inputCls} defaultValue={d.start} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-[10.5px] uppercase tracking-wide text-zinc-500">Tracked user (the owner whose usage counts)</span>
            <select className={cn(inputCls, "[color-scheme:dark]")} defaultValue={data.tracked_user} onChange={(e) => setTracked(e.target.value)}>
              <option value="">— choose —</option>
              {(users.data?.users ?? []).map((u) => <option key={u.email} value={u.email}>{u.display_name ? `${u.display_name} · ` : ""}{u.email}</option>)}
            </select>
          </label>
        </div>
        <button onClick={onSaveSettings} disabled={saving} className="flex items-center gap-1.5 rounded-lg bg-[#C08457] text-black text-xs font-medium px-3 py-1.5 disabled:opacity-40">
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Save
        </button>
      </div>

      {/* Incidents */}
      <div className="surface-card p-4 space-y-3">
        <div>
          <p className="text-sm font-medium text-zinc-50">Incidents</p>
          <p className="text-[11px] text-zinc-500 mt-0.5">Critical = the owner could not use the product or saw a wrong number (definition in docs/INCIDENTS.md). Log everything; the board counts critical only.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-6 gap-2">
          <select className={cn(inputCls, "[color-scheme:dark]")} value={newInc.severity} onChange={(e) => setNewInc({ ...newInc, severity: e.target.value as Incident["severity"] })}>
            <option value="critical">critical</option><option value="major">major</option><option value="minor">minor</option>
          </select>
          <input className={cn(inputCls, "sm:col-span-2")} placeholder="What happened" value={newInc.title} onChange={(e) => setNewInc({ ...newInc, title: e.target.value })} />
          <input className={cn(inputCls, "sm:col-span-2")} placeholder="Detail (optional)" value={newInc.detail} onChange={(e) => setNewInc({ ...newInc, detail: e.target.value })} />
          <button onClick={onAddIncident} disabled={!newInc.title.trim()} className="rounded-lg border border-white/10 text-zinc-300 text-xs px-3 py-1.5 disabled:opacity-40">Log</button>
        </div>
        {(inc.data?.incidents ?? []).length === 0 ? (
          <p className="text-xs text-zinc-600">None recorded.</p>
        ) : (
          <div className="space-y-1.5">
            {inc.data!.incidents.map((i) => (
              <div key={i.id} className="flex items-center justify-between gap-3 text-[12px] rounded-lg bg-black/20 border border-white/[0.05] px-3 py-2">
                <div className="min-w-0">
                  <span className={cn("text-[10px] uppercase tracking-wide mr-2", i.severity === "critical" ? "text-red-300" : i.severity === "major" ? "text-amber-300" : "text-zinc-500")}>{i.severity}</span>
                  <span className="text-zinc-200">{i.title}</span>
                  <span className="text-zinc-600 ml-2">{i.started_at?.slice(0, 10)}{i.resolved_at ? ` → resolved ${i.resolved_at.slice(0, 10)}` : ""}</span>
                </div>
                {!i.resolved_at && (
                  <button onClick={async () => { await patchIncident(i.id, { resolved: true }); await inc.mutate(); }} className="text-[11px] text-zinc-400 hover:text-zinc-200 shrink-0">Mark resolved</button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
