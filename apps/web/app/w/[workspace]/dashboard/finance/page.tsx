"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import { workspacePath } from "@/lib/api";

/** Moved: Finance is now Money in — the selling loop end to end. */
export default function MovedPage({ params }: { params: Promise<{ workspace: string }> }) {
  const { workspace } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(workspacePath(workspace, "/dashboard/money-in"));
  }, [router, workspace]);
  return (
    <div className="p-8 text-sm text-zinc-500">
      Taking you to Money in…
    </div>
  );
}
