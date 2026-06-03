"use client";

/**
 * ToastHost
 * ─────────
 * Renders the transient toast pop-ups (bottom-right) from the notifications
 * store. Auto-dismiss is handled by the provider; users can also close early.
 */

import { CheckCircle2, XCircle, AlertTriangle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useNotifications, type NotificationLevel } from "./NotificationsProvider";

const LEVEL_ICON: Record<NotificationLevel, React.ReactNode> = {
  success: <CheckCircle2 className="w-4 h-4 text-[#d4a070]" />,
  error:   <XCircle className="w-4 h-4 text-red-400" />,
  warning: <AlertTriangle className="w-4 h-4 text-amber-400" />,
  info:    <Info className="w-4 h-4 text-[#C08457]" />,
};

const LEVEL_RING: Record<NotificationLevel, string> = {
  success: "border-[#C08457]/30",
  error:   "border-red-500/30",
  warning: "border-amber-500/30",
  info:    "border-white/[0.1]",
};

export function ToastHost() {
  const { toasts, dismissToast } = useNotifications();
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 w-[320px] max-w-[90vw]">
      {toasts.slice(0, 4).map((t) => (
        <div
          key={t.id}
          className={cn(
            "flex gap-2.5 px-3 py-2.5 rounded-xl border bg-[#0c0c0f]/95 backdrop-blur shadow-xl animate-in",
            LEVEL_RING[t.level],
          )}
          style={{ animation: "toastIn 0.2s ease-out" }}
        >
          <span className="mt-0.5 shrink-0">{LEVEL_ICON[t.level]}</span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-[#F2DEC8]/90">{t.title}</p>
            {t.body && <p className="text-[11px] text-zinc-500 mt-0.5 break-words">{t.body}</p>}
          </div>
          <button
            onClick={() => dismissToast(t.id)}
            className="shrink-0 text-zinc-600 hover:text-[#F2DEC8] transition-colors self-start"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
      <style>{`@keyframes toastIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  );
}
