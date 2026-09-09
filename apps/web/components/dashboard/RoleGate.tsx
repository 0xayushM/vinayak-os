"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useMe, saveMe, ROLE_LAYOUTS, type Role } from "@/hooks/useMilestones";

/**
 * Asks, once, what the signed-in person does here. The answer only seeds
 * which cards their home page leads with (they can rearrange later) and is
 * recorded so the dashboard can be judged per role. Approval permissions are
 * NOT chosen here — an owner grants them in Settings → People.
 */
export default function RoleGate({ children }: { children: React.ReactNode }) {
  const { data: me, isLoading, mutate } = useMe();
  const [picked, setPicked] = useState<Role | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  if (isLoading || !me) return <>{children}</>;          // never block on a slow /me
  if (me.role_chosen) return <>{children}</>;

  async function confirm() {
    if (!picked) return;
    setBusy(true);
    try {
      await saveMe({ role: picked, display_name: name.trim() || undefined });
      await mutate();
    } finally { setBusy(false); }
  }

  const roles = Object.entries(ROLE_LAYOUTS) as [Exclude<Role, "admin">, (typeof ROLE_LAYOUTS)[Exclude<Role, "admin">]][];

  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] px-6 gap-6">
      <div className="text-center max-w-md">
        <h1 className="text-lg font-semibold text-zinc-100">What do you do here?</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Your home page will lead with what matters most for that. You can rearrange it any time.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
        {roles.map(([id, r]) => (
          <button key={id} onClick={() => setPicked(id)}
            className={`rounded-2xl border p-4 text-left transition ${
              picked === id ? "border-[#C08457] bg-[#C08457]/10" : "border-white/10 bg-white/[0.03] hover:border-[#C08457]/60 hover:bg-white/[0.06]"}`}>
            <div className="text-sm font-semibold text-[#F2DEC8]">{r.label}</div>
            <div className="text-xs text-zinc-500 mt-0.5">{r.blurb}</div>
          </button>
        ))}
      </div>
      <div className="w-full max-w-lg flex flex-col sm:flex-row gap-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name (optional)"
          className="flex-1 bg-[var(--bg-elevated)] text-[#F2DEC8]/90 text-sm rounded-lg px-3 py-2 border border-white/[0.08] focus:border-[#C08457] focus:outline-none placeholder-zinc-600" />
        <button onClick={confirm} disabled={!picked || busy}
          className="flex items-center justify-center gap-1.5 rounded-lg bg-[#C08457] text-black text-sm font-medium px-4 py-2 disabled:opacity-40">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Continue
        </button>
      </div>
    </div>
  );
}
