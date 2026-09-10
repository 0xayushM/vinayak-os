"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import { workspacePath } from "@/lib/api";

/** Moved: Production is now part of Stock & making. */
export default function MovedPage({ params }: { params: Promise<{ workspace: string }> }) {
  const { workspace } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(workspacePath(workspace, "/dashboard/operations"));
  }, [router, workspace]);
  return (
    <div className="p-8 text-sm text-zinc-500">
      Taking you to Stock & making…
    </div>
  );
}
