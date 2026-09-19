"use client";

/**
 * ErrorState — the one way a failure is shown to a person.
 *
 * Plain words, a calm tone (amber, not alarm red), and a next step: "Try again"
 * when the problem may clear on its own, "Sign in" when the session ended.
 * Never shows raw server text — see lib/errors.ts.
 */
import { useState } from "react";
import { useSWRConfig } from "swr";
import { CloudOff, LogIn, RefreshCw, WifiOff, Lock, SearchX } from "lucide-react";
import { TITLES, errorKind, friendlyMessage, isRetryable } from "@/lib/errors";
import { cn } from "@/lib/utils/cn";

const ICONS = {
  offline: WifiOff,
  unreachable: CloudOff,
  session: LogIn,
  forbidden: Lock,
  not_found: SearchX,
  busy: CloudOff,
  rejected: CloudOff,
  server: CloudOff,
} as const;

interface ErrorStateProps {
  error: unknown;
  /** Custom retry. Default: re-fetch every SWR request that is currently failing. */
  onRetry?: () => unknown;
  /** Smaller layout for use inside a panel. */
  compact?: boolean;
  className?: string;
}

export function ErrorState({ error, onRetry, compact, className }: ErrorStateProps) {
  const { cache, mutate } = useSWRConfig();
  const [retrying, setRetrying] = useState(false);
  const kind = errorKind(error);
  const Icon = ICONS[kind];

  const retry = async () => {
    setRetrying(true);
    try {
      if (onRetry) {
        await onRetry();
      } else {
        // Only the requests that failed — not everything on the page.
        await mutate((key) => {
          if (typeof key !== "string") return false;
          return Boolean((cache.get(key) as { error?: unknown } | undefined)?.error);
        });
      }
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div
      role="alert"
      className={cn(
        "h-full flex items-center justify-center",
        compact ? "py-8" : "py-12",
        className,
      )}
    >
      <div className="text-center max-w-xs">
        <div className="w-9 h-9 rounded-full bg-amber-400/10 flex items-center justify-center mx-auto mb-3">
          <Icon className="w-4 h-4 text-amber-300/80" />
        </div>
        <p className={cn("font-medium text-zinc-200", compact ? "text-[13px]" : "text-sm")}>
          {TITLES[kind]}
        </p>
        <p className={cn("text-zinc-500 mt-1 leading-relaxed", compact ? "text-[11.5px]" : "text-xs")}>
          {friendlyMessage(error)}
        </p>

        {kind === "session" ? (
          <a
            href="/login"
            className="inline-flex items-center gap-1.5 mt-4 text-[11.5px] px-3 py-1.5 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/[0.05] transition"
          >
            <LogIn className="w-3.5 h-3.5" /> Sign in
          </a>
        ) : isRetryable(error) ? (
          <button
            type="button"
            onClick={retry}
            disabled={retrying}
            className="inline-flex items-center gap-1.5 mt-4 text-[11.5px] px-3 py-1.5 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/[0.05] transition disabled:opacity-50"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", retrying && "animate-spin")} />
            {retrying ? "Trying…" : "Try again"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
