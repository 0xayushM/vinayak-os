"use client";

import { useEffect, useState } from "react";
import { Brain, Save, RefreshCw, Trash2, Plus, AlertTriangle, CheckCircle2 } from "lucide-react";
import {
  useProfile, saveProfile, useMemory, addFact, deleteFact, revalidateMemory,
  type BusinessProfile, type MemoryFact,
} from "@/hooks/useDashboard";
import { cn } from "@/lib/utils/cn";

const VERTICALS = ["manufacturing", "trading", "retail", "services"];

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] text-zinc-500 uppercase tracking-wide">{label}</span>
      {children}
    </label>
  );
}

const inputCls =
  "bg-[var(--bg-elevated)] text-[#F2DEC8]/90 text-sm rounded-lg px-3 py-2 border border-white/[0.08] focus:border-[#C08457] focus:outline-none placeholder-zinc-600";

// ── Business profile form ─────────────────────────────────────────────────────
function ProfileForm() {
  const { data, mutate } = useProfile();
  const [form, setForm] = useState<Partial<BusinessProfile>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data?.profile) setForm(data.profile);
  }, [data]);

  const set = (k: keyof BusinessProfile, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  async function onSave() {
    setSaving(true);
    setSaved(false);
    try {
      await saveProfile(form);
      await mutate();
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="surface-card p-5 space-y-4">
      <div>
        <h2 className="text-sm font-medium text-zinc-50">Business profile</h2>
        <p className="text-[11px] text-zinc-500 mt-0.5">
          The static context the AI loads on every question. Seed it once at onboarding.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Industry">
          <input className={inputCls} value={form.industry ?? ""} placeholder="Paint-brush manufacturing"
            onChange={(e) => set("industry", e.target.value)} />
        </Field>
        <Field label="Sub-vertical">
          <select className={cn(inputCls, "[color-scheme:dark]")} value={form.sub_vertical ?? ""}
            onChange={(e) => set("sub_vertical", e.target.value)}>
            <option value="">—</option>
            {VERTICALS.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </Field>
        <Field label="Fiscal year start (MM-DD)">
          <input className={inputCls} value={form.fiscal_year_start ?? ""} placeholder="04-01"
            onChange={(e) => set("fiscal_year_start", e.target.value)} />
        </Field>
        <Field label="Base currency">
          <input className={inputCls} value={form.base_currency ?? "INR"}
            onChange={(e) => set("base_currency", e.target.value)} />
        </Field>
        <Field label="Healthy margin %">
          <input type="number" className={inputCls} value={form.healthy_margin_pct ?? ""} placeholder="18"
            onChange={(e) => set("healthy_margin_pct", e.target.value === "" ? null : Number(e.target.value))} />
        </Field>
        <Field label="GST registered">
          <select className={cn(inputCls, "[color-scheme:dark]")}
            value={form.gst_registered == null ? "" : form.gst_registered ? "yes" : "no"}
            onChange={(e) => set("gst_registered", e.target.value === "" ? null : e.target.value === "yes")}>
            <option value="">—</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </Field>
        <Field label="Known seasonality">
          <input className={inputCls} value={form.seasonality ?? ""} placeholder="Diwali spike, Q4 push"
            onChange={(e) => set("seasonality", e.target.value)} />
        </Field>
        <Field label="KPIs the owner cares about">
          <input className={inputCls} value={form.kpis ?? ""} placeholder="AR aging, dead stock, top customers"
            onChange={(e) => set("kpis", e.target.value)} />
        </Field>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={onSave} disabled={saving}
          className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg bg-[#C08457]/15 text-[#C08457] border border-[#C08457]/30 hover:bg-[#C08457]/20 disabled:opacity-60 transition-colors">
          {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          Save profile
        </button>
        {saved && <span className="text-[11px] text-[#d4a070] flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Saved</span>}
        {data?.profile?.updated_at && (
          <span className="text-[10px] text-zinc-600">Updated {new Date(data.profile.updated_at).toLocaleString("en-IN")}</span>
        )}
      </div>
    </div>
  );
}

// ── Memory facts ──────────────────────────────────────────────────────────────
function valueText(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function MemorySection() {
  const { data, mutate } = useMemory();
  const facts = data?.facts ?? [];
  const [busy, setBusy] = useState(false);
  const [decayMsg, setDecayMsg] = useState<string | null>(null);
  const [nf, setNf] = useState({ entity_type: "customer", entity_ref: "", claim_key: "", claim_value: "" });

  async function onAdd() {
    if (!nf.entity_ref || !nf.claim_key) return;
    setBusy(true);
    try {
      // Coerce numeric-looking values to numbers (e.g. payment_terms_days).
      const raw = nf.claim_value.trim();
      const val: unknown = raw !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
      await addFact({ ...nf, claim_value: val, origin: "user_confirmed" });
      setNf({ entity_type: "customer", entity_ref: "", claim_key: "", claim_value: "" });
      await mutate();
    } finally {
      setBusy(false);
    }
  }
  async function onDelete(id: string) {
    await deleteFact(id);
    await mutate();
  }
  async function onRevalidate() {
    setBusy(true);
    try {
      const r = await revalidateMemory();
      setDecayMsg(`Re-validated — ${r.time_stale} expired, ${r.contradiction_stale} contradicted by data.`);
      await mutate();
      setTimeout(() => setDecayMsg(null), 5000);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="surface-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-zinc-50">Memory</h2>
          <p className="text-[11px] text-zinc-500 mt-0.5">
            Durable facts the owner has confirmed. Stale facts are flagged for re-asking, not silently trusted.
          </p>
        </div>
        <button onClick={onRevalidate} disabled={busy}
          className="flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-lg text-zinc-400 border border-white/[0.08] hover:text-[#F2DEC8]/90 transition-colors">
          <RefreshCw className={cn("w-3.5 h-3.5", busy && "animate-spin")} /> Re-validate
        </button>
      </div>

      {decayMsg && <p className="text-[11px] text-[#d4a070]">{decayMsg}</p>}

      {/* Add fact */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        <select className={cn(inputCls, "[color-scheme:dark] text-xs")} value={nf.entity_type}
          onChange={(e) => setNf({ ...nf, entity_type: e.target.value })}>
          <option value="customer">customer</option>
          <option value="item">item</option>
          <option value="company">company</option>
        </select>
        <input className={cn(inputCls, "text-xs")} placeholder="entity (e.g. DEV COLOUR)" value={nf.entity_ref.replace(/^.*?:/, "")}
          onChange={(e) => setNf({ ...nf, entity_ref: `${nf.entity_type}:${e.target.value}` })} />
        <input className={cn(inputCls, "text-xs")} placeholder="claim (e.g. payment_terms_days)" value={nf.claim_key}
          onChange={(e) => setNf({ ...nf, claim_key: e.target.value })} />
        <input className={cn(inputCls, "text-xs")} placeholder="value (e.g. 60)" value={nf.claim_value}
          onChange={(e) => setNf({ ...nf, claim_value: e.target.value })} />
        <button onClick={onAdd} disabled={busy || !nf.entity_ref || !nf.claim_key}
          className="flex items-center justify-center gap-1 text-xs px-3 py-2 rounded-lg bg-[#C08457]/15 text-[#C08457] border border-[#C08457]/30 hover:bg-[#C08457]/20 disabled:opacity-50 transition-colors">
          <Plus className="w-3.5 h-3.5" /> Add
        </button>
      </div>

      {/* Facts list */}
      {facts.length === 0 ? (
        <p className="text-xs text-zinc-600 py-4 text-center">No facts captured yet. As the AI is corrected, facts land here.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-zinc-500 border-b border-white/[0.07]">
                <th className="text-left font-medium py-2">Entity</th>
                <th className="text-left font-medium py-2">Claim</th>
                <th className="text-left font-medium py-2">Value</th>
                <th className="text-left font-medium py-2">Origin</th>
                <th className="text-left font-medium py-2">Status</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {facts.map((f: MemoryFact) => (
                <tr key={f.id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td className="py-2 text-[#F2DEC8]/80">{f.entity_ref?.replace(/^.*?:/, "")}</td>
                  <td className="py-2 text-zinc-400 font-mono">{f.claim_key}</td>
                  <td className="py-2 text-[#F2DEC8]/90 tabular-nums">{valueText(f.claim_value)}</td>
                  <td className="py-2 text-zinc-500">{f.origin}</td>
                  <td className="py-2">
                    {f.status === "stale" ? (
                      <span title={f.stale_reason ?? ""} className="inline-flex items-center gap-1 text-amber-400">
                        <AlertTriangle className="w-3 h-3" /> stale
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[#d4a070]">
                        <CheckCircle2 className="w-3 h-3" /> active
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-right">
                    <button onClick={() => onDelete(f.id)} className="text-zinc-600 hover:text-red-400 transition-colors" title="Remove">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[10.5px] text-zinc-600">
        Stale facts are flagged when they expire or when live data contradicts them
        (e.g. stated payment terms vs. how old the open invoices actually are).
      </p>
    </div>
  );
}

export default function BrainPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-4xl mx-auto w-full animate-rise">
      <div className="flex items-center gap-2">
        <Brain className="w-5 h-5 text-[#C08457]" />
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-zinc-50">Business Brain</h1>
          <p className="text-[12.5px] text-zinc-500 mt-0.5">
            The context and memory the AI reasons from — the moat beneath the dashboard.
          </p>
        </div>
      </div>
      <ProfileForm />
      <MemorySection />
    </div>
  );
}
