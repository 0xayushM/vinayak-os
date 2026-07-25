"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface Props {
  /** Called once the Zoho connection is saved and the initial sync kicked off. */
  onConnected?: () => void;
}

type Step = "idle" | "saving" | "syncing" | "done" | "error";

/**
 * Connect a Zoho Books org. Mirrors the TranzAct flow but for Zoho's OAuth
 * refresh-token credentials:
 *   1. Save credentials → POST /api/be/zoho/connect (also verifies the org)
 *   2. Trigger initial sync → POST /api/be/zoho/sync
 *
 * The generic /api/be/<path> BFF forwarder reaches the FastAPI /zoho/* routes.
 */
export default function ConnectZoho({ onConnected }: Props) {
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [refreshToken, setRefreshToken] = useState("");
  const [orgId, setOrgId] = useState("");
  const [dc, setDc] = useState("in");
  const [step, setStep] = useState<Step>("idle");
  const [message, setMessage] = useState("");

  const busy = step === "saving" || step === "syncing";
  const canSubmit = clientId && clientSecret && refreshToken && orgId && !busy;

  async function connect() {
    setStep("saving");
    setMessage("Saving credentials and verifying the organisation…");
    try {
      const saveRes = await apiFetch("/api/be/zoho/connect", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: clientId.trim(),
          client_secret: clientSecret.trim(),
          refresh_token: refreshToken.trim(),
          organization_id: orgId.trim(),
          dc: dc.trim() || "in",
        }),
      });
      if (!saveRes.ok) {
        const b = await saveRes.json().catch(() => ({}));
        throw new Error(b.detail ?? "Could not connect. Check the credentials and organisation ID.");
      }

      setStep("syncing");
      setMessage("Connected. Pulling your Zoho Books data…");
      await apiFetch("/api/be/zoho/sync", { method: "POST", credentials: "include" });

      setStep("done");
      setMessage("Zoho Books connected.");
      onConnected?.();
    } catch (err) {
      setStep("error");
      setMessage(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  const field = (
    label: string, value: string, set: (v: string) => void,
    opts: { type?: string; placeholder?: string } = {},
  ) => (
    <label className="block">
      <span className="text-xs text-zinc-400">{label}</span>
      <input
        type={opts.type ?? "text"}
        value={value}
        onChange={(e) => set(e.target.value)}
        placeholder={opts.placeholder}
        disabled={busy}
        className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-[#C08457]/60"
      />
    </label>
  );

  return (
    <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/[0.03] p-5 space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-[#F2DEC8]">Connect Zoho Books</h2>
        <p className="text-xs text-zinc-500 mt-1">
          Paste your Zoho self-client OAuth credentials. They are encrypted before storage.
        </p>
      </div>

      <div className="space-y-3">
        {field("Client ID", clientId, setClientId, { placeholder: "1000.XXXXXXXX" })}
        {field("Client Secret", clientSecret, setClientSecret, { type: "password" })}
        {field("Refresh Token", refreshToken, setRefreshToken, { type: "password" })}
        {field("Organization ID", orgId, setOrgId, { placeholder: "60000000000" })}
        <label className="block">
          <span className="text-xs text-zinc-400">Data centre</span>
          <select
            value={dc}
            onChange={(e) => setDc(e.target.value)}
            disabled={busy}
            className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-[#C08457]/60"
          >
            <option value="in">India (.in)</option>
            <option value="com">Global (.com)</option>
            <option value="eu">Europe (.eu)</option>
            <option value="au">Australia (.au)</option>
          </select>
        </label>
      </div>

      {message && (
        <p className={`text-xs ${step === "error" ? "text-red-400" : "text-zinc-400"}`}>{message}</p>
      )}

      <button
        onClick={connect}
        disabled={!canSubmit}
        className="w-full rounded-lg bg-[#C08457] text-black font-medium text-sm py-2.5 disabled:opacity-40 flex items-center justify-center gap-2"
      >
        {busy && <Loader2 className="w-4 h-4 animate-spin" />}
        {step === "saving" ? "Connecting…" : step === "syncing" ? "Syncing…" : "Connect Zoho Books"}
      </button>
    </div>
  );
}
