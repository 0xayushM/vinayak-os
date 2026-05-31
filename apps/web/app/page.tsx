"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus, AlertTriangle, LogOut } from "lucide-react";
import { apiFetch, workspacePath } from "@/lib/api";
import NewWorkspaceForm from "@/components/dashboard/NewWorkspaceForm";

interface Workspace {
  id: string;
  name: string;
  connected: boolean;
}

type View = "loading" | "picker" | "create" | "error";

/**
 * Landing page (post-login).
 *   • No brands yet  → directly show the "Create workspace" form
 *   • One brand      → go straight into its dashboard
 *   • Many brands    → show a picker; "Add brand" opens the creation form
 */
export default function Home() {
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [view, setView] = useState<View>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch("/api/workspaces")
      .then(async (r) => {
        if (!r.ok) throw new Error("Could not load your brands.");
        return r.json();
      })
      .then((d) => {
        const list: Workspace[] = d.workspaces ?? [];
        if (list.length === 1) {
          router.replace(workspacePath(list[0].id, "/dashboard"));
        } else if (list.length === 0) {
          setView("create");
        } else {
          setWorkspaces(list);
          setView("picker");
        }
      })
      .catch((e) => {
        setError(e.message);
        setView("error");
      });
  }, [router]);

  async function handleLogout() {
    await apiFetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  if (view === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading your brands…
      </div>
    );
  }

  if (view === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 text-center">
        <div className="flex items-center gap-2 text-sm text-red-400">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      </div>
    );
  }

  if (view === "create") {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 py-12 bg-[#0E0E0E]">
        <div className="w-full max-w-md space-y-8">
          {/* Page title */}
          <div className="text-center space-y-1">
            <h1 className="text-xl font-bold text-[#DBC3AE]">
              {workspaces.length === 0
                ? "Create your first workspace"
                : "Add a brand workspace"}
            </h1>
            <p className="text-sm text-zinc-500">
              One workspace = one TranzAct account = its own isolated data.
            </p>
          </div>

          <div className="bg-[#1c1b1b] border border-[#292929] rounded-2xl p-6">
            <NewWorkspaceForm
              onCancel={
                workspaces.length > 0 ? () => setView("picker") : undefined
              }
            />
          </div>
        </div>
      </div>
    );
  }

  // ── Workspace picker ─────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-[#0E0E0E]">
      <div className="w-full max-w-sm space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-[#DBC3AE] mt-0.5">
              Choose a brand
            </h1>
            <p className="text-xs text-zinc-500 mt-0.5">
              Each tab is an independent workspace.
            </p>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="text-zinc-600 hover:text-zinc-400 transition-colors p-1"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>

        {/* Brand list */}
        <div className="space-y-2">
          {workspaces.map((w) => (
            <a
              key={w.id}
              href={workspacePath(w.id, "/dashboard")}
              className="flex items-center gap-3 px-4 py-3 rounded-xl border border-[#292929] bg-[#1c1b1b] hover:bg-[#292929]/60 transition-colors"
            >
              <span className="grid place-items-center w-8 h-8 rounded-lg bg-[#C08457]/15 border border-[#C08457]/30 text-[#C08457] text-sm shrink-0">
                ◆
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-[#DBC3AE] truncate">
                  {w.name}
                </div>
                <div className="text-[11px] text-zinc-500">
                  {w.connected ? "TranzAct connected" : "Not connected yet"}
                </div>
              </div>
            </a>
          ))}
        </div>

        {/* Add brand */}
        <button
          onClick={() => setView("create")}
          className="flex items-center justify-center gap-2 w-full text-sm text-zinc-400 hover:text-[#DBC3AE]/90 border border-white/[0.08] rounded-xl py-2.5 transition-colors"
        >
          <Plus className="w-4 h-4" /> Add a brand
        </button>
      </div>
    </div>
  );
}
