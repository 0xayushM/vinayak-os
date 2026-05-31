"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Building2,
  Plug,
  Loader2,
  CheckCircle,
  XCircle,
  Circle,
  AlertTriangle,
  ArrowLeft,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { apiFetch, workspacePath } from "@/lib/api";

type Step =
  | "idle"
  | "creating"
  | "saving"
  | "testing"
  | "syncing"
  | "done"
  | "error";

type PipelineStatus = "pending" | "running" | "success" | "failed";

interface PipelineProgress {
  key: string;
  label: string;
  status: PipelineStatus;
  rows: number | null;
  error: string | null;
}

interface SyncState {
  running: boolean;
  total: number;
  completed: number;
  current: string | null;
  error: string | null;
  pipelines: PipelineProgress[];
}

interface Props {
  onCancel?: () => void;
}

const STEP_LABELS: Record<Step, string> = {
  idle: "",
  creating: "Creating workspace…",
  saving: "Saving TranzAct credentials…",
  testing: "Testing TranzAct connection…",
  syncing: "Pulling your data from TranzAct…",
  done: "Setup complete — loading your dashboard…",
  error: "",
};

const CORE_PIPELINES = [
  "ar_aging",
  "sales_orders",
  "purchase_orders",
  "inventory_valuation",
];

function coreReady(state: SyncState): boolean {
  const core = state.pipelines.filter((p) => CORE_PIPELINES.includes(p.key));
  if (core.length < CORE_PIPELINES.length) return false;
  return core.every((p) => p.status === "success" || p.status === "failed");
}

function toSlug(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export default function NewWorkspaceForm({ onCancel }: Props) {
  const router = useRouter();
  const [brandName, setBrandName] = useState("");
  const [tzEmail, setTzEmail] = useState("");
  const [tzPassword, setTzPassword] = useState("");
  const [step, setStep] = useState<Step>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [sync, setSync] = useState<SyncState | null>(null);

  const slug = toSlug(brandName);
  const busy = step !== "idle" && step !== "done" && step !== "error";

  async function pollSyncUntilReady(wsSlug: string, maxSeconds = 600) {
    const start = Date.now();
    while (Date.now() - start < maxSeconds * 1000) {
      try {
        const res = await apiFetch(
          "/api/connections/tranzact/sync",
          { method: "GET" },
          wsSlug,
        );
        if (res.ok) {
          const state: SyncState = await res.json();
          setSync(state);
          const allDone =
            !state.running && state.total > 0 && state.completed >= state.total;
          if (allDone || (state.total > 0 && coreReady(state))) return;
        }
      } catch {
        /* keep polling */
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!slug) return;
    setErrorMsg("");

    try {
      // 1. Create workspace
      setStep("creating");
      const createRes = await apiFetch("/api/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: slug, name: brandName.trim() }),
      });
      if (!createRes.ok) {
        const d = await createRes.json().catch(() => ({}));
        throw new Error(d.detail ?? "Failed to create workspace");
      }

      // 2. Save TranzAct credentials (workspace now exists)
      setStep("saving");
      const saveRes = await apiFetch(
        "/api/connections/tranzact",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: tzEmail, password: tzPassword }),
        },
        slug,
      );
      if (!saveRes.ok) {
        const d = await saveRes.json().catch(() => ({}));
        throw new Error(d.detail ?? "Failed to save credentials");
      }

      // 3. Test connection
      setStep("testing");
      const testRes = await apiFetch(
        "/api/connections/tranzact/test",
        { method: "POST" },
        slug,
      );
      if (!testRes.ok) {
        const d = await testRes.json().catch(() => ({}));
        throw new Error(d.detail ?? "TranzAct connection test failed — check your credentials");
      }

      // 4. Trigger sync
      setStep("syncing");
      await apiFetch(
        "/api/connections/tranzact/sync",
        { method: "POST" },
        slug,
      );

      // 5. Poll progress
      await pollSyncUntilReady(slug);

      // 6. Navigate
      setStep("done");
      setTimeout(() => router.push(workspacePath(slug, "/dashboard")), 800);
    } catch (err) {
      setStep("error");
      setErrorMsg(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="w-full max-w-md space-y-6">
      {/* Header */}
      <div className="space-y-1">
        {onCancel && step === "idle" && (
          <button
            onClick={onCancel}
            className="flex items-center gap-1 text-xs text-zinc-500 hover:text-[#DBC3AE]/75 mb-3 transition-colors"
          >
            <ArrowLeft className="w-3 h-3" /> Back
          </button>
        )}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#C08457]/15 border border-[#C08457]/30 flex items-center justify-center shrink-0">
            <Building2 className="w-5 h-5 text-[#C08457]" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-[#DBC3AE]">
              Add a brand workspace
            </h2>
            <p className="text-xs text-zinc-500">
              Connect your TranzAct account to pull live data
            </p>
          </div>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Brand name */}
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-zinc-400">
            Brand name
          </label>
          <input
            type="text"
            value={brandName}
            onChange={(e) => setBrandName(e.target.value)}
            placeholder="e.g. KBrushes"
            required
            disabled={busy || step === "done"}
            className="w-full bg-[#292929]/60 text-[#DBC3AE]/90 text-sm rounded-lg px-3 py-2.5 border border-[#292929] focus:border-[#C08457] focus:outline-none placeholder-zinc-600 disabled:opacity-60"
          />
          {slug && (
            <p className="text-[11px] text-zinc-600">
              Workspace ID:{" "}
              <span className="font-mono text-zinc-500">{slug}</span>
            </p>
          )}
        </div>

        {/* TranzAct credentials */}
        <div className="rounded-xl border border-[#292929] bg-[#1c1b1b]/50 p-4 space-y-3">
          <div className="flex items-center gap-2 text-xs font-medium text-zinc-400">
            <Plug className="w-3.5 h-3.5 text-[#C08457]" />
            TranzAct credentials
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Email</label>
            <input
              type="email"
              value={tzEmail}
              onChange={(e) => setTzEmail(e.target.value)}
              placeholder="you@company.com"
              required
              disabled={busy || step === "done"}
              className="w-full bg-[#292929] text-[#DBC3AE]/90 text-sm rounded-lg px-3 py-2 border border-[#292929] focus:border-[#C08457] focus:outline-none placeholder-zinc-600 disabled:opacity-60"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Password</label>
            <input
              type="password"
              value={tzPassword}
              onChange={(e) => setTzPassword(e.target.value)}
              placeholder="••••••••"
              required
              disabled={busy || step === "done"}
              className="w-full bg-[#292929] text-[#DBC3AE]/90 text-sm rounded-lg px-3 py-2 border border-[#292929] focus:border-[#C08457] focus:outline-none placeholder-zinc-600 disabled:opacity-60"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={busy || step === "done" || !slug}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#C08457] hover:bg-[#C08457] text-white text-sm font-semibold rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />}
          {step === "idle" && "Create workspace & connect"}
          {step === "creating" && "Creating workspace…"}
          {step === "saving" && "Saving credentials…"}
          {step === "testing" && "Testing connection…"}
          {step === "syncing" && "Syncing data…"}
          {step === "done" && (
            <>
              <CheckCircle className="w-4 h-4" /> Done
            </>
          )}
          {step === "error" && "Retry"}
        </button>
      </form>

      {/* Status message */}
      {(busy || step === "done") && (
        <div className="flex items-center gap-2 text-xs rounded-lg px-3 py-2.5 bg-[#292929] text-zinc-400">
          {busy && <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin" />}
          {step === "done" && (
            <CheckCircle className="w-3.5 h-3.5 shrink-0 text-[#d4a070]" />
          )}
          {STEP_LABELS[step]}
        </div>
      )}

      {/* Error */}
      {step === "error" && errorMsg && (
        <div className="flex items-start gap-2 text-xs rounded-lg px-3 py-2.5 bg-red-500/10 border border-red-500/20 text-red-400">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          {errorMsg}
        </div>
      )}

      {/* Sync progress */}
      {(step === "syncing" || step === "done") && sync && sync.total > 0 && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span>Pulling reports from TranzAct</span>
              <span className="tabular-nums">
                {sync.completed}/{sync.total}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#292929]">
              <div
                className="h-full rounded-full bg-[#C08457] transition-all duration-500"
                style={{
                  width: `${Math.round((sync.completed / sync.total) * 100)}%`,
                }}
              />
            </div>
          </div>

          <ul className="space-y-1.5">
            {sync.pipelines.map((p) => (
              <li key={p.key} className="flex items-center gap-2 text-xs">
                {p.status === "success" && (
                  <CheckCircle className="w-3.5 h-3.5 shrink-0 text-[#d4a070]" />
                )}
                {p.status === "running" && (
                  <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-[#C08457]" />
                )}
                {p.status === "failed" && (
                  <XCircle className="w-3.5 h-3.5 shrink-0 text-red-400" />
                )}
                {p.status === "pending" && (
                  <Circle className="w-3.5 h-3.5 shrink-0 text-zinc-600" />
                )}
                <span
                  className={cn(
                    "flex-1",
                    p.status === "success" && "text-[#DBC3AE]/75",
                    p.status === "running" && "text-[#DBC3AE]/90",
                    p.status === "failed" && "text-red-400",
                    p.status === "pending" && "text-zinc-600",
                  )}
                >
                  {p.label}
                </span>
                {p.status === "success" && p.rows != null && (
                  <span className="tabular-nums text-zinc-600">
                    {p.rows.toLocaleString()} rows
                  </span>
                )}
                {p.status === "failed" && (
                  <span className="text-zinc-600">failed</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[11px] text-zinc-600">
        Your TranzAct credentials are encrypted (AES-256) before storage. Bearer
        tokens are never persisted.
      </p>
    </div>
  );
}
