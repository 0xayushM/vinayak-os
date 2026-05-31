"use client";

import { useEffect, useState } from "react";
import { CheckCircle, AlertTriangle, Loader2, Plug, Circle, XCircle, RefreshCw, FlaskConical, KeyRound } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { apiFetch } from "@/lib/api";
import { relativeTime } from "@/lib/utils/cn";

type Step = "idle" | "saving" | "testing" | "syncing" | "done" | "error";

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

interface ExistingConnection {
  is_active: boolean;
  last_verified_at: string | null;
  created_at: string | null;
}

interface Props {
  /** Called once the connection is verified AND the initial sync has finished. */
  onConnected?: () => void;
  /** Compact mode for the settings page: checks existing connection first. */
  compact?: boolean;
}

/**
 * Full connect-TranzAct flow:
 *   1. Save encrypted credentials   → POST /api/connections/tranzact
 *   2. Test connection              → POST /api/connections/tranzact/test
 *   3. Trigger initial full sync    → POST /api/connections/tranzact/sync
 *   4. Poll sync health until data has landed, then onConnected().
 *
 * In compact (settings) mode: checks for an existing connection first.
 * If found, shows a status card instead of the credentials form — no risk
 * of accidentally entering the wrong email for this workspace.
 */
export default function ConnectTranzact({ onConnected, compact = false }: Props) {
  const [existing, setExisting] = useState<ExistingConnection | null>(null);
  const [checkDone, setCheckDone] = useState(!compact); // skip check when not compact
  const [showChangeForm, setShowChangeForm] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<Step>("idle");
  const [message, setMessage] = useState("");
  const [sync, setSync] = useState<SyncState | null>(null);

  // In compact (settings) mode, check for existing connection on mount.
  useEffect(() => {
    if (!compact) return;
    apiFetch("/api/connections/")
      .then(async (r) => {
        if (r.ok) {
          const data = await r.json();
          const tz: ExistingConnection | undefined = (data.connections ?? []).find(
            (c: ExistingConnection & { tool_name: string }) => c.tool_name === "tranzact",
          );
          if (tz?.is_active) setExisting(tz);
        }
      })
      .catch(() => {})
      .finally(() => setCheckDone(true));
  }, [compact]);

  const busy = step === "saving" || step === "testing" || step === "syncing";

  /**
   * Core operational reports. These feed the panels a user sees first and run
   * fast (small windows, fetched first by the backend). Once these have all
   * reached a terminal state, the dashboard is usable — the remaining,
   * slower/heavier reports keep syncing in the background and don't block
   * onboarding. This prevents one slow or failed pipeline (e.g. Sales
   * Quotations) from holding the user at the connect screen.
   */
  const CORE_PIPELINES = [
    "ar_aging",
    "sales_orders",
    "purchase_orders",
    "inventory_valuation",
  ];

  function coreReady(state: SyncState): boolean {
    const core = state.pipelines.filter((p) => CORE_PIPELINES.includes(p.key));
    // Wait until the checklist has been seeded with the core entries.
    if (core.length < CORE_PIPELINES.length) return false;
    // Terminal = succeeded or failed; either way we stop waiting on it.
    return core.every((p) => p.status === "success" || p.status === "failed");
  }

  async function pollSyncUntilReady(maxSeconds = 600) {
    const start = Date.now();
    while (Date.now() - start < maxSeconds * 1000) {
      try {
        const res = await apiFetch("/api/connections/tranzact/sync", { credentials: "include" });
        if (res.ok) {
          const state: SyncState = await res.json();
          setSync(state);
          // Enter the dashboard as soon as the core reports have landed, or
          // once the whole run has finished — whichever comes first.
          const allDone =
            !state.running && state.total > 0 && state.completed >= state.total;
          if (allDone || (state.total > 0 && coreReady(state))) {
            return true;
          }
        }
      } catch {
        /* keep polling */
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    return true; // give up waiting but let the user into the dashboard
  }

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setStep("saving");
    setMessage("Saving credentials…");

    try {
      // 1. Save
      const saveRes = await apiFetch("/api/connections/tranzact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      if (!saveRes.ok) {
        const d = await saveRes.json().catch(() => ({}));
        throw new Error(d.detail ?? "Failed to save credentials");
      }

      // 2. Test
      setStep("testing");
      setMessage("Testing TranzAct authentication…");
      const testRes = await apiFetch("/api/connections/tranzact/test", {
        method: "POST",
        credentials: "include",
      });
      if (!testRes.ok) {
        const d = await testRes.json().catch(() => ({}));
        throw new Error(d.detail ?? "Connection test failed");
      }

      // 3. Trigger full sync
      setStep("syncing");
      setMessage("Connection verified. Pulling your data from TranzAct…");
      await apiFetch("/api/connections/tranzact/sync", {
        method: "POST",
        credentials: "include",
      });

      // 4. Poll until the core reports have landed (the rest keep syncing in
      //    the background — a slow or failed pipeline won't block onboarding).
      await pollSyncUntilReady();

      setStep("done");
      setMessage("Core reports are in — loading your dashboard. Remaining reports will keep syncing in the background.");
      onConnected?.();
    } catch (err) {
      setStep("error");
      setMessage(err instanceof Error ? err.message : String(err));
    }
  }

  // ── Loading check ───────────────────────────────────────────────────────────
  if (!checkDone) {
    return (
      <div className="bg-[#141414] border border-[#1e1e1e] rounded-xl p-6 flex items-center gap-3 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Checking connection…
      </div>
    );
  }

  // ── Connected status card (compact / settings mode) ───────────────────────
  if (compact && existing && !showChangeForm) {
    return (
      <div className="bg-[#141414] border border-[#1e1e1e] rounded-xl p-6 space-y-4 max-w-xl">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#C08457]/12 border border-[#C08457]/20 flex items-center justify-center">
            <CheckCircle className="w-5 h-5 text-[#d4a070]" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-[#F2DEC8]">TranzAct connected</h2>
            <p className="text-xs text-zinc-500">
              {existing.last_verified_at
                ? `Last verified ${relativeTime(existing.last_verified_at)}`
                : "Connected · not yet verified"}
            </p>
          </div>
        </div>

        {/* Status message during re-sync / re-test */}
        {message && (
          <div className={cn(
            "flex items-start gap-2 rounded-lg px-3 py-2.5 text-xs",
            step === "done"    ? "bg-[#C08457]/10 border border-[#C08457]/20 text-[#d4a070]"
            : step === "error" ? "bg-red-500/10 border border-red-500/20 text-red-400"
            : "bg-[#1e1e1e] text-zinc-400",
          )}>
            {step === "done"  && <CheckCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
            {step === "error" && <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
            {busy             && <Loader2 className="w-3.5 h-3.5 mt-0.5 shrink-0 animate-spin" />}
            {message}
          </div>
        )}

        {/* Inline sync progress */}
        {(step === "syncing" || step === "done") && sync && sync.total > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span>Pulling reports from TranzAct</span>
              <span className="tabular-nums">{sync.completed}/{sync.total}</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#1e1e1e]">
              <div
                className="h-full rounded-full bg-[#C08457] transition-all duration-500"
                style={{ width: `${Math.round((sync.completed / sync.total) * 100)}%` }}
              />
            </div>
            <ul className="space-y-1 pt-1">
              {sync.pipelines.map((p) => (
                <li key={p.key} className="flex items-center gap-2 text-xs">
                  {p.status === "success" && <CheckCircle className="w-3 h-3 shrink-0 text-[#d4a070]" />}
                  {p.status === "running" && <Loader2 className="w-3 h-3 shrink-0 animate-spin text-[#C08457]" />}
                  {p.status === "failed"  && <XCircle className="w-3 h-3 shrink-0 text-red-400" />}
                  {p.status === "pending" && <Circle className="w-3 h-3 shrink-0 text-zinc-600" />}
                  <span className={cn(
                    "flex-1",
                    p.status === "success" && "text-[#F2DEC8]/75",
                    p.status === "running" && "text-[#F2DEC8]/90",
                    p.status === "failed"  && "text-red-400",
                    p.status === "pending" && "text-zinc-600",
                  )}>{p.label}</span>
                  {p.status === "success" && p.rows != null && (
                    <span className="tabular-nums text-zinc-600">{p.rows.toLocaleString()} rows</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            onClick={async () => {
              setStep("syncing");
              setMessage("Re-syncing your data from TranzAct…");
              setSync(null);
              try {
                await apiFetch("/api/connections/tranzact/sync", { method: "POST" });
                await pollSyncUntilReady();
                setStep("done");
                setMessage("Sync complete.");
              } catch (e) {
                setStep("error");
                setMessage(e instanceof Error ? e.message : String(e));
              }
            }}
            disabled={busy}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#C08457] hover:bg-[#C08457] text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-50"
          >
            {step === "syncing" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Re-sync data
          </button>
          <button
            onClick={async () => {
              setStep("testing");
              setMessage("Testing TranzAct connection…");
              try {
                const r = await apiFetch("/api/connections/tranzact/test", { method: "POST" });
                if (!r.ok) {
                  const d = await r.json().catch(() => ({}));
                  throw new Error(d.detail ?? "Test failed");
                }
                setStep("done");
                setMessage("Connection test passed ✓");
              } catch (e) {
                setStep("error");
                setMessage(e instanceof Error ? e.message : String(e));
              }
            }}
            disabled={busy}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-[#F2DEC8]/90 text-xs font-semibold rounded-lg transition-colors disabled:opacity-50"
          >
            {step === "testing" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FlaskConical className="w-3.5 h-3.5" />}
            Test connection
          </button>
          <button
            onClick={() => { setShowChangeForm(true); setStep("idle"); setMessage(""); }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1e1e1e] hover:bg-zinc-700 text-zinc-400 text-xs font-semibold rounded-lg transition-colors"
          >
            <KeyRound className="w-3.5 h-3.5" /> Update credentials
          </button>
        </div>
      </div>
    );
  }

  // ── Credentials form (new connection OR update) ───────────────────────────
  return (
    <div
      className={cn(
        "bg-[#141414] border border-[#1e1e1e] rounded-xl p-6 space-y-5",
        compact ? "max-w-xl" : "max-w-md w-full",
      )}
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-[#C08457]/15 border border-[#C08457]/20 flex items-center justify-center">
          <Plug className="w-5 h-5 text-[#C08457]" />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold text-[#F2DEC8]">
            {showChangeForm ? "Update TranzAct credentials" : "Connect TranzAct"}
          </h2>
          <p className="text-xs text-zinc-500">Cloud ERP · letstranzact.com</p>
        </div>
        {showChangeForm && (
          <button
            onClick={() => setShowChangeForm(false)}
            className="text-xs text-zinc-500 hover:text-[#F2DEC8]/75 transition-colors"
          >
            Cancel
          </button>
        )}
      </div>

      {!compact && !showChangeForm && (
        <p className="text-sm text-zinc-400">
          Enter your TranzAct login to start syncing your business data. We test
          the connection, then pull all reports into your dashboard automatically.
        </p>
      )}

      <form onSubmit={handleConnect} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">TranzAct Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            required
            disabled={busy || step === "done"}
            className="w-full bg-[#1e1e1e] text-[#F2DEC8]/90 text-sm rounded-lg px-3 py-2 border border-[#1e1e1e] focus:border-[#C08457] focus:outline-none placeholder-zinc-600 disabled:opacity-60"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">TranzAct Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            disabled={busy || step === "done"}
            className="w-full bg-[#1e1e1e] text-[#F2DEC8]/90 text-sm rounded-lg px-3 py-2 border border-[#1e1e1e] focus:border-[#C08457] focus:outline-none placeholder-zinc-600 disabled:opacity-60"
          />
        </div>

        <button
          type="submit"
          disabled={busy || step === "done"}
          className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 bg-[#C08457] hover:bg-[#C08457] text-white text-sm font-semibold rounded-lg transition-colors disabled:opacity-50"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />}
          {step === "saving" && "Saving…"}
          {step === "testing" && "Testing…"}
          {step === "syncing" && "Syncing data…"}
          {step === "done" && "Connected"}
          {(step === "idle" || step === "error") && "Connect & Sync"}
        </button>
      </form>

      {message && (
        <div
          className={cn(
            "flex items-start gap-2 rounded-lg px-3 py-2.5 text-xs",
            step === "done"
              ? "bg-[#C08457]/10 border border-[#C08457]/20 text-[#d4a070]"
              : step === "error"
              ? "bg-red-500/10 border border-red-500/20 text-red-400"
              : "bg-[#1e1e1e] text-zinc-400",
          )}
        >
          {step === "done" && <CheckCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
          {step === "error" && <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
          {busy && <Loader2 className="w-3.5 h-3.5 mt-0.5 shrink-0 animate-spin" />}
          {message}
        </div>
      )}

      {/* ── Sync progress tracker ──────────────────────────────────────────── */}
      {(step === "syncing" || step === "done") && sync && sync.total > 0 && (
        <div className="space-y-3">
          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span>Pulling reports from TranzAct</span>
              <span className="tabular-nums">
                {sync.completed}/{sync.total}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#1e1e1e]">
              <div
                className="h-full rounded-full bg-[#C08457] transition-all duration-500"
                style={{ width: `${Math.round((sync.completed / sync.total) * 100)}%` }}
              />
            </div>
          </div>

          {/* Per-report checklist */}
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
                    p.status === "success" && "text-[#F2DEC8]/75",
                    p.status === "running" && "text-[#F2DEC8]/90",
                    p.status === "failed" && "text-red-400",
                    p.status === "pending" && "text-zinc-600",
                  )}
                >
                  {p.label}
                </span>
                {p.status === "success" && p.rows != null && (
                  <span className="tabular-nums text-zinc-600">{p.rows} rows</span>
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
        Your credentials are encrypted (AES-256) before storage. Bearer tokens are
        never persisted — they are obtained on demand and held in memory only.
      </p>
    </div>
  );
}
