"use client";

import { useState } from "react";
import { Loader2, Users } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useMe, useWorkspaceUsers, saveWorkspaceUser, type Role, type WorkspaceUser } from "@/hooks/useMilestones";

const ROLES: Role[] = ["owner", "finance", "accountant", "sales", "viewer", "admin"];
const selectCls =
  "bg-[var(--bg-elevated)] text-[#F2DEC8]/90 text-xs rounded-lg px-2 py-1.5 border border-white/[0.08] focus:border-[#C08457] focus:outline-none [color-scheme:dark]";

/**
 * Who can open this workspace, what they do, and what they may approve.
 * Visible to owners and admins only; everyone else sees nothing here.
 */
export function PeoplePanel() {
  const { data: me } = useMe();
  const { data, error, mutate } = useWorkspaceUsers();
  const [busy, setBusy] = useState<string | null>(null);

  if (!me || !["owner", "admin"].includes(me.role ?? "")) return null;

  async function change(u: WorkspaceUser, patch: Partial<Pick<WorkspaceUser, "role" | "may_approve_messages" | "may_approve_money">>) {
    setBusy(u.email);
    try { await saveWorkspaceUser({ email: u.email, ...patch } as Parameters<typeof saveWorkspaceUser>[0]); await mutate(); }
    finally { setBusy(null); }
  }

  return (
    <div className="surface-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Users className="w-4 h-4 text-[#C08457]" />
        <div>
          <h3 className="text-[11px] font-semibold text-zinc-500 uppercase tracking-[0.1em]">People &amp; approvals</h3>
          <p className="text-[11px] text-zinc-500">Roles shape the home page. The two switches decide who may approve messages and who may approve anything that moves money.</p>
        </div>
      </div>
      {error && <p className="text-xs text-zinc-500">Only owners and admins can see this.</p>}
      <div className="space-y-2">
        {(data?.users ?? []).map((u) => (
          <div key={u.email} className="grid grid-cols-1 sm:grid-cols-[1fr_auto_auto_auto] items-center gap-2 rounded-lg bg-black/20 border border-white/[0.05] px-3 py-2">
            <div className="min-w-0">
              <p className="text-[12.5px] text-zinc-200 truncate">{u.display_name ? `${u.display_name} · ` : ""}{u.email}</p>
              {u.global_admin && <p className="text-[10.5px] text-zinc-600">global admin (all workspaces)</p>}
            </div>
            <select className={selectCls} value={u.role ?? "admin"} disabled={busy === u.email}
              onChange={(e) => change(u, { role: e.target.value as Role })}>
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <label className={cn("flex items-center gap-1.5 text-[11px]", u.may_approve_messages ? "text-[#F2DEC8]" : "text-zinc-500")}>
              <input type="checkbox" checked={u.may_approve_messages} disabled={busy === u.email}
                onChange={(e) => change(u, { may_approve_messages: e.target.checked })} /> messages
            </label>
            <label className={cn("flex items-center gap-1.5 text-[11px]", u.may_approve_money ? "text-[#F2DEC8]" : "text-zinc-500")}>
              <input type="checkbox" checked={u.may_approve_money} disabled={busy === u.email}
                onChange={(e) => change(u, { may_approve_money: e.target.checked })} /> money
              {busy === u.email && <Loader2 className="w-3 h-3 animate-spin" />}
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}
