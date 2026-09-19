"use client";

/** Last-resort fallback when the root layout itself fails. Must render <html>. */
import { useEffect } from "react";

export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.warn("[app] failed to render:", error);
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0, minHeight: "100vh", display: "grid", placeItems: "center", background: "#0b0908", color: "#e4e4e7", fontFamily: "system-ui, sans-serif" }}>
        <div style={{ textAlign: "center", maxWidth: 380, padding: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 500, margin: 0 }}>Something didn&apos;t load properly</h2>
          <p style={{ fontSize: 13, color: "#a1a1aa", marginTop: 8, lineHeight: 1.5 }}>
            Your data is safe. Please try again — if it keeps happening, refresh the page in a minute.
          </p>
          <button
            type="button"
            onClick={() => unstable_retry()}
            style={{ marginTop: 18, fontSize: 13, padding: "8px 14px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.12)", background: "transparent", color: "#e4e4e7", cursor: "pointer" }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
