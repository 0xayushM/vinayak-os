"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import { workspacePath } from "@/lib/api";

/** Moved: AR Aging is the receivables stage of Money in. */
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
