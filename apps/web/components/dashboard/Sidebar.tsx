"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  BarChart3, TrendingUp, Users, Package, ShoppingCart,
  CreditCard, Truck, Wrench, Activity, Settings, Zap, LogOut,
  Menu, X, ChevronsUpDown, Plus, ExternalLink, Check, Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useSyncHealth } from "@/hooks/useDashboard";
import { apiFetch, workspacePath } from "@/lib/api";

const NAV = [
  {
    section: "Revenue",
    items: [
      { label: "Revenue Overview",      href: "/dashboard",            icon: TrendingUp },
      { label: "Customer Insights",     href: "/dashboard/customers",  icon: Users      },
      { label: "Top SKUs",              href: "/dashboard/skus",       icon: Package    },
      { label: "Quotes & Pipeline",     href: "/dashboard/quotes",     icon: Zap        },
    ],
  },
  {
    section: "Receivables",
    items: [
      { label: "AR Aging",              href: "/dashboard/ar",         icon: CreditCard },
      { label: "Open Sales Orders",     href: "/dashboard/orders",     icon: ShoppingCart },
    ],
  },
  {
    section: "Procurement",
    items: [
      { label: "Purchases",             href: "/dashboard/purchases",  icon: Truck      },
      { label: "Open POs",              href: "/dashboard/pos",        icon: ShoppingCart },
      { label: "GRN / Goods Received",  href: "/dashboard/grn",        icon: Truck      },
    ],
  },
  {
    section: "Operations",
    items: [
      { label: "Inventory",             href: "/dashboard/inventory",  icon: BarChart3  },
      { label: "Production",            href: "/dashboard/production", icon: Wrench     },
      { label: "BOM Coverage",          href: "/dashboard/bom",        icon: Activity   },
    ],
  },
];

interface Workspace {
  id: string;
  name: string;
  connected: boolean;
}

/**
 * Brand picker. Lists every brand the owner can open. Selecting one is a full
 * navigation (so SWR caches reset and the new tab's X-Workspace-Id takes over);
 * "open in new tab" lets the owner view two brands side by side.
 */
function WorkspaceSwitcher({ ws, onNavigate }: { ws: string | null; onNavigate?: () => void }) {
  const [open, setOpen] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    apiFetch("/api/workspaces")
      .then((r) => (r.ok ? r.json() : { workspaces: [] }))
      .then((d) => setWorkspaces(d.workspaces ?? []))
      .catch(() => setWorkspaces([]));
  }, []);

  const current = workspaces?.find((w) => w.id === ws) ?? null;
  const label = current?.name ?? ws ?? "Select brand";

  async function handleCreate() {
    const name = window.prompt("New brand name (e.g. Protegere)");
    if (!name) return;
    const id = name.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
    if (!id) return;
    setCreating(true);
    try {
      const res = await apiFetch("/api/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, name: name.trim() }),
      });
      if (res.ok) {
        window.location.href = workspacePath(id, "/dashboard");
      } else {
        const e = await res.json().catch(() => ({}));
        window.alert(e.detail ?? "Could not create brand.");
      }
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="relative px-4 py-4 border-b border-white/[0.05]">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 w-full text-left"
      >
        <Image src="/logo.png" alt="Logo" width={28} height={28} className="rounded-lg shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold tracking-tight text-[#F2DEC8] truncate archimoto">
            {label}
          </div>
          <div className="text-[10.5px] text-[#7a6055] truncate">TranzAct</div>
        </div>
        <ChevronsUpDown className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute left-3 right-3 top-[calc(100%-4px)] z-20 rounded-xl bg-[var(--bg-elevated)] border border-white/[0.08] shadow-2xl py-1.5 max-h-80 overflow-y-auto">
            <div className="px-3 pb-1 text-[10px] font-semibold text-zinc-600 uppercase tracking-[0.1em]">
              Brands
            </div>
            {workspaces === null && (
              <div className="flex items-center gap-2 px-3 py-2 text-[11.5px] text-zinc-500">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
              </div>
            )}
            {workspaces?.length === 0 && (
              <div className="px-3 py-2 text-[11.5px] text-zinc-500">No brands yet.</div>
            )}
            {workspaces?.map((w) => {
              const active = w.id === ws;
              return (
                <div key={w.id} className="flex items-center group">
                  <Link
                    href={workspacePath(w.id, "/dashboard")}
                    onClick={() => { setOpen(false); onNavigate?.(); }}
                    className={cn(
                      "flex items-center gap-2 flex-1 min-w-0 px-3 py-2 text-[12.5px] transition-colors",
                      active ? "text-[#F2DEC8]" : "text-zinc-400 hover:text-[#F2DEC8]/90",
                    )}
                  >
                    <span className="truncate flex-1">{w.name}</span>
                    {!w.connected && (
                      <span className="text-[9.5px] text-amber-400/80 shrink-0">not connected</span>
                    )}
                    {active && <Check className="w-3.5 h-3.5 text-[#C08457] shrink-0" />}
                  </Link>
                  <a
                    href={workspacePath(w.id, "/dashboard")}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Open in new tab"
                    className="px-2.5 py-2 text-zinc-600 hover:text-[#F2DEC8]/75 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
              );
            })}
            <div className="mt-1 border-t border-white/[0.05] pt-1">
              <button
                onClick={handleCreate}
                disabled={creating}
                className="flex items-center gap-2 w-full px-3 py-2 text-[12.5px] text-zinc-400 hover:text-[#F2DEC8]/90 transition-colors disabled:opacity-60"
              >
                {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                Add brand
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function RailContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data: health } = useSyncHealth();
  const ws = pathname.match(/^\/w\/([^/]+)/)?.[1] ?? null;
  const link = (suffix: string) => workspacePath(ws, suffix);

  async function handleLogout() {
    await apiFetch("/api/auth/logout", { method: "POST", credentials: "include" });
    window.location.href = "/login";
  }

  return (
    <div className="flex flex-col h-full surface-rail">
      {/* Brand switcher */}
      <WorkspaceSwitcher ws={ws} onNavigate={onNavigate} />

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 space-y-5">
        {NAV.map((section) => (
          <div key={section.section}>
            <div className="px-4 pb-1.5 text-[10px] font-semibold text-zinc-600 uppercase tracking-[0.1em]">
              {section.section}
            </div>
            <div className="px-2 space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                const href = link(item.href);
                const active = pathname === href;
                return (
                  <Link
                    key={item.href}
                    href={href}
                    onClick={onNavigate}
                    className={cn(
                      "relative flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[12.5px] transition-all duration-150",
                      active
                        ? "bg-white/[0.06] text-[#F2DEC8]"
                        : "text-zinc-400 hover:text-[#F2DEC8]/90 hover:bg-white/[0.03]",
                    )}
                  >
                    {active && (
                      <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-[#C08457]" />
                    )}
                    <Icon className={cn("w-3.5 h-3.5 shrink-0", active ? "text-[#C08457]" : "")} />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Sync health indicator */}
      <div className="px-4 py-3 border-t border-white/[0.05]">
        <Link
          href={link("/dashboard/sync")}
          onClick={onNavigate}
          className="flex items-center gap-2 text-[11px] text-zinc-500 hover:text-[#F2DEC8]/75 transition-colors"
        >
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              health === undefined
                ? "bg-zinc-600"
                : health.healthy
                ? "bg-[#C08457]"
                : "bg-amber-500 animate-pulse",
            )}
          />
          {health === undefined
            ? "Checking sync…"
            : health.healthy
            ? "All pipelines healthy"
            : `${health.stale_pipelines.length} stale pipeline${health.stale_pipelines.length > 1 ? "s" : ""}`}
        </Link>
      </div>

      {/* Settings + Logout */}
      <div className="px-4 py-3 border-t border-white/[0.05] space-y-2">
        <Link
          href={link("/dashboard/settings")}
          onClick={onNavigate}
          className="flex items-center gap-2 text-[11px] text-zinc-500 hover:text-[#F2DEC8]/75 transition-colors"
        >
          <Settings className="w-3.5 h-3.5" />
          Settings & Connections
        </Link>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 text-[11px] text-zinc-600 hover:text-red-400 transition-colors w-full text-left"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign out
        </button>
      </div>
    </div>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Close drawer on route change.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <>
      {/* Desktop rail */}
      <aside className="hidden lg:flex w-60 shrink-0 border-r border-white/[0.05] relative z-10">
        <RailContent />
      </aside>

      {/* Mobile top bar */}
      <div className="lg:hidden fixed top-0 inset-x-0 z-30 h-12 flex items-center justify-between px-4 surface-rail border-b border-white/[0.05] backdrop-blur-md">
        <div className="flex items-center gap-2">
          <Image src="/logo.png" alt="Logo" width={24} height={24} className="rounded-md shrink-0" />
          <span className="text-[13px] font-semibold tracking-tight text-[#F2DEC8] archimoto">
            Brain OS
          </span>
        </div>
        <button
          onClick={() => setOpen(true)}
          className="p-1.5 rounded-md text-zinc-400 hover:text-[#F2DEC8] hover:bg-white/[0.05]"
          aria-label="Open menu"
        >
          <Menu className="w-5 h-5" />
        </button>
      </div>

      {/* Mobile drawer */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-rise"
            onClick={() => setOpen(false)}
          />
          <div className="absolute left-0 top-0 bottom-0 w-72 max-w-[80%] bg-[var(--bg-elevated)] border-r border-white/[0.06] shadow-2xl">
            <button
              onClick={() => setOpen(false)}
              className="absolute right-3 top-3 z-10 p-1.5 rounded-md text-zinc-400 hover:text-[#F2DEC8] hover:bg-white/[0.05]"
              aria-label="Close menu"
            >
              <X className="w-4 h-4" />
            </button>
            <RailContent onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
