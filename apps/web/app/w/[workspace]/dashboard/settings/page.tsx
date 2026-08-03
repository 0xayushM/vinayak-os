"use client";

import { useState } from "react";
import { Unplug, Plus, ArrowLeft } from "lucide-react";
import ConnectTranzact from "@/components/dashboard/ConnectTranzact";
import ConnectZoho from "@/components/dashboard/ConnectZoho";
import { ApiSyncPanel } from "@/components/dashboard/ApiSyncPanel";

type AddableId = "zoho";
const ADDABLE: { id: AddableId; label: string; blurb: string }[] = [
  { id: "zoho", label: "Zoho Books", blurb: "Accounting / invoicing" },
];
const COMING_SOON = ["Tally Prime", "Busy Accounting", "Odoo"];

export default function SettingsPage() {
  const [adding, setAdding] = useState<AddableId | null>(null);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-6xl mx-auto w-full animate-rise">
      <div className="mb-6">
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-zinc-50">Settings &amp; Connections</h1>
        <p className="text-[12.5px] text-zinc-500 mt-1">
          Connect your data sources or re-sync on demand.
        </p>
      </div>

      {/* Bento: sources on the left, the data-sync list on the right. */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 items-start">

        <div className="lg:col-span-2 space-y-5">
          {/* Connected source */}
          <ConnectTranzact compact />

          {/* Add a data source — the form stays hidden until a source is chosen */}
          <div className="surface-card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-[11px] font-semibold text-zinc-500 uppercase tracking-[0.1em]">
                Add a data source
              </h3>
              {adding && (
                <button onClick={() => setAdding(null)}
                  className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300">
                  <ArrowLeft className="w-3 h-3" /> Back
                </button>
              )}
            </div>

            {!adding ? (
              <div className="grid grid-cols-2 gap-3">
                {ADDABLE.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setAdding(s.id)}
                    className="rounded-xl border border-white/10 bg-white/[0.03] hover:border-[#C08457]/60 hover:bg-white/[0.06] p-4 text-left transition flex flex-col gap-2"
                  >
                    <div className="w-9 h-9 rounded-lg bg-[#C08457]/15 border border-[#C08457]/20 flex items-center justify-center">
                      <Plus className="w-4 h-4 text-[#C08457]" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-[#F2DEC8] leading-tight">{s.label}</p>
                      <p className="text-xs text-zinc-500">{s.blurb}</p>
                    </div>
                  </button>
                ))}
                {COMING_SOON.map((name) => (
                  <div key={name} className="rounded-xl border border-white/5 bg-white/[0.02] p-4 flex flex-col gap-2 opacity-50">
                    <div className="w-9 h-9 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center">
                      <Unplug className="w-4 h-4 text-zinc-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-zinc-400 leading-tight">{name}</p>
                      <p className="text-xs text-zinc-600">Coming soon</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : adding === "zoho" ? (
              <ConnectZoho onConnected={() => setAdding(null)} />
            ) : null}
          </div>
        </div>

        {/* Data sync — the per-report list */}
        <div className="lg:col-span-3">
          <ApiSyncPanel />
        </div>
      </div>
    </div>
  );
}
