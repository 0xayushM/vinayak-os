"use client";

/**
 * NotificationBell + slide-in panel
 * ─────────────────────────────────
 * Fixed bell in the top-right with an unread badge. Clicking opens a right-side
 * panel listing session notifications (sync outcomes, failures, timeouts).
 */

import { useEffect, useState } from "react";
import {
  Bell, X, CheckCircle2, XCircle, AlertTriangle, Info, Clock, Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useNotifications, type NotificationLevel } from "./NotificationsProvider";
import { MigrationProgress } from "./MigrationProgress";

const LEVEL_ICON: Record<NotificationLevel, React.ReactNode> = {
  success: <CheckCircle2 className="w-4 h-4 text-[#d4a070]" />,
  error:   <XCircle className="w-4 h-4 text-red-400" />,
  warning: <AlertTriangle className="w-4 h-4 text-amber-400" />,
  info:    <Info className="w-4 h-4 text-[#C08457]" />,
};

function ago(ts: number): string {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function NotificationBell() {
  const { notifications, unreadCount, markAllRead, remove, clearAll } = useNotifications();
  const [open, setOpen] = useState(false);

  // Mark everything read once the panel is opened (in an effect, never during render).
  useEffect(() => {
    if (open) markAllRead();
  }, [open, markAllRead]);

  function toggle() {
    setOpen((v) => !v);
  }

  return (
    <>
      <button
        onClick={toggle}
        title="Notifications"
        className="fixed top-3 right-3 z-40 flex items-center justify-center w-9 h-9 rounded-full border border-white/[0.08] bg-[#0c0c0f]/80 backdrop-blur text-[#F2DEC8]/80 hover:text-[#F2DEC8] hover:border-[#C08457]/40 transition-colors"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-[#C08457] text-[9px] font-semibold text-black flex items-center justify-center">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* Backdrop */}
      {open && (
        <div className="fixed inset-0 z-40 bg-black/40" onClick={() => setOpen(false)} />
      )}

      {/* Slide-in panel */}
      <aside
        className={cn(
          "fixed top-0 right-0 z-50 h-full w-[340px] max-w-[90vw] bg-[#0a0a0d] border-l border-white/[0.08] shadow-2xl flex flex-col transition-transform duration-300",
          open ? "translate-x-0" : "translate-x-full",
        )}
        aria-hidden={!open}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.07]">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-[#C08457]" />
            <span className="text-sm font-medium text-[#F2DEC8]">Notifications</span>
          </div>
          <div className="flex items-center gap-1">
            {notifications.length > 0 && (
              <button
                onClick={clearAll}
                title="Clear all"
                className="p-1.5 rounded-md text-zinc-500 hover:text-[#F2DEC8] hover:bg-white/[0.05] transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              onClick={() => setOpen(false)}
              className="p-1.5 rounded-md text-zinc-500 hover:text-[#F2DEC8] hover:bg-white/[0.05] transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Live data-sync progress (only while a sync is running) */}
          <MigrationProgress />

          {notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-zinc-600 px-6 text-center">
              <Clock className="w-6 h-6" />
              <p className="text-xs">No notifications yet. Sync results will appear here.</p>
            </div>
          ) : (
            <ul className="divide-y divide-white/[0.05]">
              {notifications.map((n) => (
                <li key={n.id} className="group flex gap-3 px-4 py-3 hover:bg-white/[0.02]">
                  <span className="mt-0.5 shrink-0">{LEVEL_ICON[n.level]}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-[#F2DEC8]/90">{n.title}</p>
                    {n.body && <p className="text-[11px] text-zinc-500 mt-0.5 break-words">{n.body}</p>}
                    <p className="text-[10px] text-zinc-600 mt-1">{ago(n.ts)}</p>
                  </div>
                  <button
                    onClick={() => remove(n.id)}
                    className="shrink-0 opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-[#F2DEC8] transition-opacity self-start"
                    title="Dismiss"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
