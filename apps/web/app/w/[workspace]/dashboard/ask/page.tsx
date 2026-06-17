"use client";

import { useEffect } from "react";
import { Sparkles } from "lucide-react";
import { useChatDock } from "@/components/dashboard/ChatDock";

/**
 * The AI chat now lives in the right-docked panel (Windsurf-style, with tabs and
 * history). This route just opens the dock and points the user to it, so any old
 * link or bookmark to /dashboard/ask still works.
 */
export default function AskRedirectPage() {
  const dock = useChatDock();
  useEffect(() => { dock.setOpen(true); /* eslint-disable-next-line */ }, []);
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center gap-3 px-6">
      <Sparkles className="w-8 h-8 text-[#C08457]" />
      <h1 className="text-lg font-semibold text-zinc-50">Ask AI is in the side panel</h1>
      <p className="text-sm text-zinc-500 max-w-sm">
        The assistant opens on the right. Use the tabs to keep several conversations going, and the
        clock icon to reopen past chats.
      </p>
      <button onClick={() => dock.setOpen(true)}
        className="mt-1 flex items-center gap-2 px-4 py-2 rounded-full bg-[#C08457] text-black text-sm font-medium hover:bg-[#d4a070] transition-colors">
        <Sparkles className="w-4 h-4" /> Open Ask AI
      </button>
    </div>
  );
}
