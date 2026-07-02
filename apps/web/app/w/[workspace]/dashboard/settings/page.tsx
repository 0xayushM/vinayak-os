"use client";

import { Unplug } from "lucide-react";
import ConnectTranzact from "@/components/dashboard/ConnectTranzact";
import { ApiSyncPanel } from "@/components/dashboard/ApiSyncPanel";

export default function SettingsPage() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-8 max-w-xl mx-auto w-full animate-rise">
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-zinc-50">Settings & Connections</h1>
        <p className="text-[12.5px] text-zinc-500 mt-1">
          Connect your ERP tools or re-sync data on demand.
        </p>
      </div>

      {/* TranzAct connection — save, test, and run a fresh sync */}
      <ConnectTranzact compact />

      {/* Per-API sync — run each report individually (pulls complete data) */}
      <ApiSyncPanel />

      {/* Future ERP placeholders */}
      <div className="space-y-3">
        <h3 className="text-[11px] font-semibold text-zinc-600 uppercase tracking-[0.1em]">
          Coming in Phase 3
        </h3>
        {["Tally Prime (Local Agent)", "Busy Accounting"].map((name) => (
          <div
            key={name}
            className="surface-card p-4 flex items-center gap-3 opacity-50"
          >
            <div className="w-9 h-9 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center">
              <Unplug className="w-4 h-4 text-zinc-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-400">{name}</p>
              <p className="text-xs text-zinc-600">Not yet available</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
