"use client";

/**
 * NotificationsProvider
 * ─────────────────────
 * Session-only (in-memory) notification store for the dashboard. Holds a list
 * of notifications shown in the bell panel, plus a short-lived toast queue for
 * pop-ups. Nothing is persisted — the list clears on reload by design.
 */

import {
  createContext, useCallback, useContext, useMemo, useRef, useState,
} from "react";

export type NotificationLevel = "success" | "error" | "warning" | "info";

export interface AppNotification {
  id: string;
  level: NotificationLevel;
  title: string;
  body?: string;
  ts: number;
  read: boolean;
}

interface NotifyInput {
  level: NotificationLevel;
  title: string;
  body?: string;
  /** Also flash a transient toast (default true). */
  toast?: boolean;
  /** Dedupe key — a repeat within this session won't be added again. */
  dedupeKey?: string;
}

interface NotificationsContextValue {
  notifications: AppNotification[];
  toasts: AppNotification[];
  unreadCount: number;
  notify: (input: NotifyInput) => void;
  markAllRead: () => void;
  remove: (id: string) => void;
  clearAll: () => void;
  dismissToast: (id: string) => void;
}

const NotificationsContext = createContext<NotificationsContextValue | null>(null);

let _seq = 0;
const nextId = () => `n${Date.now()}_${_seq++}`;

export function NotificationsProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [toasts, setToasts] = useState<AppNotification[]>([]);
  const seenKeys = useRef<Set<string>>(new Set());

  const notify = useCallback((input: NotifyInput) => {
    if (input.dedupeKey) {
      if (seenKeys.current.has(input.dedupeKey)) return;
      seenKeys.current.add(input.dedupeKey);
    }
    const item: AppNotification = {
      id: nextId(),
      level: input.level,
      title: input.title,
      body: input.body,
      ts: Date.now(),
      read: false,
    };
    setNotifications((prev) => [item, ...prev].slice(0, 100));
    if (input.toast !== false) {
      setToasts((prev) => [item, ...prev]);
      // Auto-dismiss the toast after 6s (errors linger a little longer).
      const ttl = input.level === "error" ? 9000 : 6000;
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== item.id));
      }, ttl);
    }
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);
  const remove = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);
  const clearAll = useCallback(() => setNotifications([]), []);
  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const value = useMemo(
    () => ({ notifications, toasts, unreadCount, notify, markAllRead, remove, clearAll, dismissToast }),
    [notifications, toasts, unreadCount, notify, markAllRead, remove, clearAll, dismissToast],
  );

  return (
    <NotificationsContext.Provider value={value}>
      {children}
    </NotificationsContext.Provider>
  );
}

export function useNotifications(): NotificationsContextValue {
  const ctx = useContext(NotificationsContext);
  if (!ctx) throw new Error("useNotifications must be used within NotificationsProvider");
  return ctx;
}
