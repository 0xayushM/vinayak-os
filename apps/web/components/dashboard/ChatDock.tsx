"use client";

import {
  createContext, useContext, useState, useEffect, useRef, useCallback,
} from "react";
import {
  Sparkles, Send, Loader2, Plus, X, Clock, Trash2, MessageSquare, PanelRightClose,
} from "lucide-react";
import {
  askQuestion, useThreads, createThread, fetchThreadTurns, deleteThread,
  type AskResponse, type ChatThreadMeta,
} from "@/hooks/useDashboard";
import { AnswerCard } from "@/components/dashboard/ChatMessage";
import { cn } from "@/lib/utils/cn";

// ── Provider (toggle from anywhere) ───────────────────────────────────────────
interface DockCtx { open: boolean; setOpen: (v: boolean) => void; toggle: () => void; }
const Ctx = createContext<DockCtx | null>(null);
export function useChatDock() {
  const c = useContext(Ctx);
  return c ?? { open: false, setOpen: () => {}, toggle: () => {} };
}

const SUGGESTIONS = [
  "Who owes me money and who is overdue?",
  "Am I too dependent on a few customers?",
  "How much did I sell last month?",
  "What stock is just sitting there?",
];

interface Turn { q: string; a?: AskResponse; error?: string; taught?: boolean; }
interface Tab { key: string; threadId?: string; title: string; turns: Turn[]; loaded: boolean; }

let _k = 0;
const newKey = () => `tab${Date.now()}_${_k++}`;
const ws = () => (typeof window !== "undefined" ? (window.location.pathname.match(/\/w\/([^/]+)/)?.[1] ?? "") : "");
const LS = () => `chatdock_${ws()}`;

export function ChatDockProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const value: DockCtx = { open, setOpen, toggle: () => setOpen((v) => !v) };
  return (
    <Ctx.Provider value={value}>
      {children}
      <ChatDock />
    </Ctx.Provider>
  );
}

// ── The dock ──────────────────────────────────────────────────────────────────
function ChatDock() {
  const { open, setOpen } = useChatDock();
  const { data: threadsData, mutate: mutateThreads } = useThreads();
  const threads: ChatThreadMeta[] = threadsData?.threads ?? [];

  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeKey, setActiveKey] = useState<string>("");
  const [showHistory, setShowHistory] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const restored = useRef(false);

  const active = tabs.find((t) => t.key === activeKey);

  const addDraft = useCallback(() => {
    const key = newKey();
    setTabs((t) => [...t, { key, title: "New chat", turns: [], loaded: true }]);
    setActiveKey(key);
    return key;
  }, []);

  // Restore open tabs from localStorage on first open.
  useEffect(() => {
    if (!open || restored.current) return;
    restored.current = true;
    try {
      const saved = JSON.parse(localStorage.getItem(LS()) || "{}");
      const ids: string[] = saved.openThreadIds || [];
      if (ids.length) {
        setTabs(ids.map((id) => ({ key: newKey(), threadId: id, title: "…", turns: [], loaded: false })));
        setActiveKey((k) => k || "");
      }
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Ensure there's always at least one tab when open.
  useEffect(() => {
    if (open && tabs.length === 0) addDraft();
    if (open && tabs.length && !tabs.find((t) => t.key === activeKey)) setActiveKey(tabs[0].key);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, tabs.length]);

  // Lazy-load turns for the active tab when it points at a saved thread.
  useEffect(() => {
    if (!active || active.loaded || !active.threadId) return;
    fetchThreadTurns(active.threadId).then((turns) => {
      setTabs((ts) => ts.map((t) => t.key === active.key
        ? { ...t, loaded: true, turns: turns.map((x) => ({ q: x.question, a: x.answer, taught: true })),
            title: threads.find((th) => th.id === t.threadId)?.title ?? t.title }
        : t));
    }).catch(() => setTabs((ts) => ts.map((t) => t.key === active.key ? { ...t, loaded: true } : t)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.key, active?.threadId, active?.loaded]);

  // Persist open thread ids.
  useEffect(() => {
    const openThreadIds = tabs.map((t) => t.threadId).filter(Boolean);
    try { localStorage.setItem(LS(), JSON.stringify({ openThreadIds })); } catch { /* ignore */ }
  }, [tabs]);

  // Autoscroll on new content.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [active?.turns.length, loading]);

  function openThread(meta: ChatThreadMeta) {
    setShowHistory(false);
    const existing = tabs.find((t) => t.threadId === meta.id);
    if (existing) { setActiveKey(existing.key); return; }
    const key = newKey();
    setTabs((t) => [...t, { key, threadId: meta.id, title: meta.title, turns: [], loaded: false }]);
    setActiveKey(key);
  }

  function closeTab(key: string) {
    setTabs((ts) => {
      const next = ts.filter((t) => t.key !== key);
      if (key === activeKey) setActiveKey(next.length ? next[next.length - 1].key : "");
      return next;
    });
  }

  async function removeThread(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    await deleteThread(id);
    setTabs((ts) => ts.filter((t) => t.threadId !== id));
    mutateThreads();
  }

  async function send(text: string) {
    const q = text.trim();
    if (!q || loading || !active) return;
    setInput(""); setLoading(true);
    const key = active.key;
    setTabs((ts) => ts.map((t) => t.key === key ? { ...t, turns: [...t.turns, { q }] } : t));
    try {
      const a = await askQuestion(q, active.threadId);
      setTabs((ts) => ts.map((t) => {
        if (t.key !== key) return t;
        const turns = t.turns.slice();
        turns[turns.length - 1] = { q, a };
        return { ...t, threadId: t.threadId ?? a.thread_id, turns };
      }));
      mutateThreads();   // pick up the auto-generated title
    } catch (e) {
      setTabs((ts) => ts.map((t) => {
        if (t.key !== key) return t;
        const turns = t.turns.slice();
        turns[turns.length - 1] = { q, error: (e as Error).message };
        return { ...t, turns };
      }));
    } finally { setLoading(false); }
  }

  // Keep tab titles fresh from the threads list (auto-named after first message).
  useEffect(() => {
    setTabs((ts) => ts.map((t) => {
      const meta = threads.find((th) => th.id === t.threadId);
      return meta && meta.title !== t.title ? { ...t, title: meta.title } : t;
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadsData]);

  return (
    <>
      {/* Floating launcher */}
      {!open && (
        <button onClick={() => setOpen(true)}
          className="fixed bottom-5 right-5 z-40 flex items-center gap-2 px-4 py-2.5 rounded-full bg-[#C08457] text-black font-medium text-sm shadow-lg hover:bg-[#d4a070] transition-colors">
          <Sparkles className="w-4 h-4" /> Ask AI
        </button>
      )}

      {/* Right dock */}
      <aside className={cn(
        "fixed top-0 right-0 z-50 h-full w-[420px] max-w-[92vw] bg-[#0a0a0d] border-l border-white/[0.08] shadow-2xl flex flex-col transition-transform duration-300",
        open ? "translate-x-0" : "translate-x-full",
      )}>
        {/* Header + tabs */}
        <div className="border-b border-white/[0.07]">
          <div className="flex items-center justify-between px-3 py-2">
            <div className="flex items-center gap-1.5 text-sm font-medium text-[#F2DEC8]">
              <Sparkles className="w-4 h-4 text-[#C08457]" /> Ask AI
            </div>
            <div className="flex items-center gap-1">
              <button onClick={() => setShowHistory((v) => !v)} title="History"
                className={cn("p-1.5 rounded-md hover:bg-white/[0.06] transition-colors", showHistory ? "text-[#C08457]" : "text-zinc-400")}>
                <Clock className="w-4 h-4" />
              </button>
              <button onClick={addDraft} title="New chat" className="p-1.5 rounded-md text-zinc-400 hover:text-[#F2DEC8] hover:bg-white/[0.06] transition-colors">
                <Plus className="w-4 h-4" />
              </button>
              <button onClick={() => setOpen(false)} title="Close panel" className="p-1.5 rounded-md text-zinc-400 hover:text-[#F2DEC8] hover:bg-white/[0.06] transition-colors">
                <PanelRightClose className="w-4 h-4" />
              </button>
            </div>
          </div>
          {/* Tab strip */}
          <div className="flex items-center gap-1 px-2 pb-2 overflow-x-auto">
            {tabs.map((t) => (
              <div key={t.key}
                onClick={() => setActiveKey(t.key)}
                className={cn(
                  "group flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-lg text-[11px] cursor-pointer whitespace-nowrap max-w-[150px] shrink-0 border transition-colors",
                  t.key === activeKey ? "bg-[#C08457]/15 text-[#F2DEC8] border-[#C08457]/30" : "text-zinc-400 border-transparent hover:bg-white/[0.04]",
                )}>
                <MessageSquare className="w-3 h-3 shrink-0 opacity-70" />
                <span className="truncate">{t.title}</span>
                <button onClick={(e) => { e.stopPropagation(); closeTab(t.key); }}
                  className="shrink-0 opacity-0 group-hover:opacity-100 hover:text-red-400 transition-opacity" title="Close tab (chat is saved in history)">
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* History panel */}
        {showHistory && (
          <div className="absolute top-[92px] right-3 z-10 w-[300px] max-h-[60%] overflow-y-auto bg-[#0c0c0f] border border-white/[0.1] rounded-xl shadow-xl p-1.5">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wide px-2 py-1">Chat history</p>
            {threads.length === 0 && <p className="text-xs text-zinc-600 px-2 py-3">No past chats yet.</p>}
            {threads.map((th) => (
              <div key={th.id} onClick={() => openThread(th)}
                className="group flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg hover:bg-white/[0.05] cursor-pointer">
                <div className="min-w-0">
                  <p className="text-xs text-[#F2DEC8]/85 truncate">{th.title}</p>
                  <p className="text-[10px] text-zinc-600">{th.turn_count} message{th.turn_count === 1 ? "" : "s"}</p>
                </div>
                <button onClick={(e) => removeThread(th.id, e)} title="Delete chat"
                  className="shrink-0 opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 transition-opacity">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3">
          {active && active.turns.length === 0 && (
            <div className="space-y-2 pt-2">
              <p className="text-[11px] text-zinc-500">Ask anything about this brand&apos;s data. Try:</p>
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)}
                  className="block w-full text-left text-[12px] text-[#F2DEC8]/75 bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.08] rounded-lg px-3 py-2 transition-colors">
                  {s}
                </button>
              ))}
            </div>
          )}
          {active?.turns.map((turn, i) => (
            <div key={i} className="space-y-2">
              <div className="flex justify-end">
                <p className="text-[13px] bg-[#C08457]/12 text-[#F2DEC8]/90 rounded-2xl rounded-br-sm px-3 py-1.5 max-w-[88%]">{turn.q}</p>
              </div>
              {turn.error ? (
                <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{turn.error}</div>
              ) : turn.a ? (
                <AnswerCard a={turn.a} taught={turn.taught}
                  onTaught={() => setTabs((ts) => ts.map((t) => t.key === active.key
                    ? { ...t, turns: t.turns.map((x, j) => j === i ? { ...x, taught: true } : x) } : t))} />
              ) : (
                <div className="flex items-center gap-2 text-zinc-500 text-xs"><Loader2 className="w-4 h-4 animate-spin" /> Thinking…</div>
              )}
            </div>
          ))}
        </div>

        {/* Input */}
        <div className="border-t border-white/[0.07] p-2.5">
          <div className="flex gap-2">
            <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send(input)}
              placeholder="Ask about revenue, customers, stock…"
              className="flex-1 bg-[var(--bg-elevated)] text-[#F2DEC8]/90 text-sm rounded-xl px-3.5 py-2 border border-white/[0.08] focus:border-[#C08457] focus:outline-none placeholder-zinc-600" />
            <button onClick={() => send(input)} disabled={loading || !input.trim()}
              className="flex items-center justify-center w-10 rounded-xl bg-[#C08457]/15 text-[#C08457] border border-[#C08457]/30 hover:bg-[#C08457]/20 disabled:opacity-50 transition-colors">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
