"use client";

import { useEffect } from "react";
import { apiFetch } from "@/lib/api";

/**
 * SyncOnLogin
 * ───────────
 * Fires a lightweight incremental refresh (newest pages only) once per browser
 * session when the dashboard first loads. The backend endpoint is a no-op if
 * nothing's connected or a sync is already running, and it never disturbs an
 * in-progress migration. The hourly background refresh is handled server-side
 * by the scheduler.
 *
 * Renders nothing.
 */
const SESSION_KEY = "vinayak.syncedThisSession";

export function SyncOnLogin() {
  useEffect(() => {
    try {
      if (sessionStorage.getItem(SESSION_KEY)) return;
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      // sessionStorage unavailable — fall through and just fire once per mount.
    }
    apiFetch("/api/connections/tranzact/sync/refresh", {
      method: "POST",
      credentials: "include",
    }).catch(() => {
      /* best-effort; surfaced elsewhere if it matters */
    });
  }, []);

  return null;
}
