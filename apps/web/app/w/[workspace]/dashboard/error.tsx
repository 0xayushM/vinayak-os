"use client";

/**
 * Fallback for anything that breaks while a dashboard page renders. Sits inside
 * the dashboard layout, so the sidebar stays and the person can move on.
 */
import { useEffect } from "react";
import { CloudOff, RefreshCw } from "lucide-react";

export default function DashboardError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.warn("[dashboard] page failed to render:", error);
  }, [error]);

  return (
    <div className="surface-card max-w-lg mx-auto mt-16 px-8 py-12 text-center" role="alert">
      <div className="w-10 h-10 rounded-full bg-amber-400/10 flex items-center justify-center mx-auto mb-4">
        <CloudOff className="w-5 h-5 text-amber-300/80" />
      </div>
      <h2 className="text-sm font-medium text-zinc-200">This page didn&apos;t load properly</h2>
      <p className="text-xs text-zinc-500 mt-1.5 leading-relaxed">
        Your data is safe. Try again, or pick another page from the menu — the rest of the app is
        working.
      </p>
      <button
        type="button"
        onClick={() => unstable_retry()}
        className="inline-flex items-center gap-1.5 mt-5 text-xs px-3.5 py-2 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/[0.05] transition"
      >
        <RefreshCw className="w-3.5 h-3.5" /> Try again
      </button>
    </div>
  );
}
