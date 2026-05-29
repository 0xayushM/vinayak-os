"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3, TrendingUp, Users, Package, ShoppingCart,
  CreditCard, Truck, Wrench, Activity, Settings, Zap, LogOut,
  Menu, X,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useSyncHealth } from "@/hooks/useDashboard";

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

function RailContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data: health } = useSyncHealth();

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    window.location.href = "/login";
  }

  return (
    <div className="flex flex-col h-full surface-rail">
      {/* Brand */}
      <div className="px-4 py-4 border-b border-white/[0.05]">
        <div className="flex items-center gap-2">
          <span className="grid place-items-center w-7 h-7 rounded-lg bg-indigo-500/15 border border-indigo-400/20 text-indigo-300 text-sm">
            ◆
          </span>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold tracking-tight text-zinc-100 truncate">
              Vinayak Brain OS
            </div>
            <div className="text-[10.5px] text-zinc-500 truncate">KBrushes · TranzAct</div>
          </div>
        </div>
      </div>

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
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    className={cn(
                      "relative flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[12.5px] transition-all duration-150",
                      active
                        ? "bg-white/[0.06] text-zinc-100"
                        : "text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.03]",
                    )}
                  >
                    {active && (
                      <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-indigo-400" />
                    )}
                    <Icon className={cn("w-3.5 h-3.5 shrink-0", active ? "text-indigo-300" : "")} />
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
          href="/dashboard/sync"
          onClick={onNavigate}
          className="flex items-center gap-2 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              health === undefined
                ? "bg-zinc-600"
                : health.healthy
                ? "bg-emerald-500"
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
          href="/dashboard/settings"
          onClick={onNavigate}
          className="flex items-center gap-2 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
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
          <span className="grid place-items-center w-6 h-6 rounded-md bg-indigo-500/15 border border-indigo-400/20 text-indigo-300 text-xs">
            ◆
          </span>
          <span className="text-[13px] font-semibold tracking-tight text-zinc-100">
            Vinayak Brain OS
          </span>
        </div>
        <button
          onClick={() => setOpen(true)}
          className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.05]"
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
              className="absolute right-3 top-3 z-10 p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.05]"
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
