"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import ConnectTranzact from "./ConnectTranzact";
import ConnectZoho from "./ConnectZoho";
import { apiFetch } from "@/lib/api";

interface Connection {
  tool_name: string;
  is_active: boolean;
  last_verified_at: string | null;
}

/** Data sources a brand can connect. TranzAct + Zoho are live; more to come. */
type SourceId = "tranzact" | "zoho" | "busy" | "tally";
const SOURCES: { id: SourceId; label: string; blurb: string; available: boolean }[] = [
  { id: "tranzact", label: "TranzAct", blurb: "Manufacturing ERP", available: true },
  { id: "zoho", label: "Zoho Books", blurb: "Accounting / invoicing", available: true },
  { id: "busy", label: "Busy", blurb: "Coming soon", available: false },
  { id: "tally", label: "Tally", blurb: "Coming soon", available: false },
];
// tool_connections.tool_name values that count as "connected".
const ACTIVE_TOOL_NAMES = ["tranzact", "zoho_books"];

/**
 * Gates the dashboard behind a verified TranzAct connection.
 *
 *   not connected  → show the Connect TranzAct onboarding flow
 *   connected       → render the dashboard (children)
 *
 * This replaces the old dismissible banner: connecting TranzAct is now the
 * first thing a freshly-logged-in user does.
 */
export default function OnboardingGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"loading" | "connected" | "disconnected">("loading");
  const [chosen, setChosen] = useState<SourceId | null>(null);

  const check = useCallback(async () => {
    try {
      const res = await apiFetch("/api/connections/", { credentials: "include" });
      if (!res.ok) {
        setState("disconnected");
        return;
      }
      const data = await res.json();
      const conns: Connection[] = data.connections ?? [];
      // Connected if ANY supported source is active (TranzAct or Zoho today).
      const active = conns.some(
        (c) => ACTIVE_TOOL_NAMES.includes(c.tool_name) && c.is_active,
      );
      setState(active ? "connected" : "disconnected");
    } catch {
      setState("disconnected");
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  if (state === "loading") {
    return (
      <div className="flex items-center justify-center min-h-[60vh] text-zinc-500 text-sm gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Checking your connection…
      </div>
    );
  }

  if (state === "disconnected") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] px-6 gap-6">
        <div className="text-center">
          <h1 className="text-lg font-semibold text-zinc-100">Welcome to Brain OS</h1>
          <p className="text-sm text-zinc-500 mt-1">
            {chosen
              ? "Enter your credentials to bring your business data into the dashboard."
              : "Choose the system your business runs on to get started."}
          </p>
        </div>

        {!chosen && (
          <div className="grid grid-cols-2 gap-3 w-full max-w-md">
            {SOURCES.map((s) => (
              <button
                key={s.id}
                disabled={!s.available}
                onClick={() => s.available && setChosen(s.id)}
                className={`rounded-2xl border p-4 text-left transition ${
                  s.available
                    ? "border-white/10 bg-white/[0.03] hover:border-[#C08457]/60 hover:bg-white/[0.06]"
                    : "border-white/5 bg-white/[0.02] opacity-50 cursor-not-allowed"
                }`}
              >
                <div className="text-sm font-semibold text-[#F2DEC8]">{s.label}</div>
                <div className="text-xs text-zinc-500 mt-0.5">{s.blurb}</div>
              </button>
            ))}
          </div>
        )}

        {chosen === "tranzact" && <ConnectTranzact onConnected={check} />}
        {chosen === "zoho" && <ConnectZoho onConnected={check} />}

        {chosen && (
          <button
            onClick={() => setChosen(null)}
            className="text-xs text-zinc-500 hover:text-zinc-300"
          >
            ← Choose a different source
          </button>
        )}
      </div>
    );
  }

  return <>{children}</>;
}
