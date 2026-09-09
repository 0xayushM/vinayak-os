"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/utils/cn";
import { CheckCircle, XCircle, Loader2, Inbox, ShieldCheck, Send, AlertTriangle } from "lucide-react";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Payload = Record<string, any>;
interface Action {
  id: string;
  tool_name: string;
  entity_ref: string | null;
  payload: Payload;
  status: string;
  proposed_by: string;
  created_at: string | null;
  decided_at: string | null;
  result: Payload | null;
  recipient_email: string | null;
}

/** Approved by a human, but delivery did not happen (no email on file, provider
 *  unconfigured, or a transport error). These can be retried. */
function isStuck(a: Action): boolean {
  return a.status === "approved" && !(a.result?.sent);
}

export default function ApprovalsPage() {
  const [items, setItems] = useState<Action[] | null>(null);
  const [stuck, setStuck] = useState<Action[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [emails, setEmails] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([
        apiFetch("/api/be/dashboard/actions?status=proposed", { credentials: "include" }).then((r) => r.json()),
        apiFetch("/api/be/dashboard/actions?status=approved", { credentials: "include" }).then((r) => r.json()),
      ]);
      setItems(p.actions ?? []);
      setStuck(((a.actions ?? []) as Action[]).filter(isStuck));
    } catch {
      setItems([]);
      setStuck([]);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const decide = async (id: string, decision: "approve" | "reject", email?: string) => {
    setBusy(id);
    setNotice(null);
    try {
      const res = await apiFetch(`/api/be/dashboard/actions/${id}/decide`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(email ? { decision, email } : { decision }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) {
        setNotice(d.detail ?? "Could not record the decision.");
      } else if (decision === "approve" && !d.sent) {
        setNotice(
          d.need === "email"
            ? "Approved, but no email is on file for this customer — add one below to send."
            : `Approved, but not delivered: ${d.detail?.error ?? "delivery failed"}. You can retry from "Awaiting delivery".`,
        );
      }
      await load();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-3xl mx-auto w-full animate-rise space-y-5">
      <PageHeader title="Approvals" subtitle="Nothing is sent until you approve it here" />

      <div className="rounded-xl border border-[#C08457]/20 bg-[#C08457]/[0.06] px-4 py-3 flex items-start gap-3 text-sm text-[#d4a070]">
        <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" />
        <span>Every message the system drafts waits here for your review. Approve to send, reject to discard — money and outbound messages never go automatically.</span>
      </div>

      {notice && (
        <div className="rounded-xl border border-amber-400/25 bg-amber-400/[0.07] px-4 py-3 flex items-start gap-3 text-sm text-amber-200">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{notice}</span>
        </div>
      )}

      {items === null && (
        <div className="flex items-center gap-2 text-zinc-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      )}

      {items && items.length === 0 && (
        <div className="surface-card p-10 flex flex-col items-center text-center gap-2">
          <Inbox className="w-6 h-6 text-zinc-600" />
          <p className="text-sm text-zinc-400">Nothing waiting for approval.</p>
          <p className="text-xs text-zinc-600">Draft a reminder from the Finance → Collections list and it will appear here.</p>
        </div>
      )}

      {items && items.map((a) => {
        const p = a.payload ?? {};
        const amount = p.overdue || p.outstanding || 0;
        return (
          <div key={a.id} className="surface-card p-4 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[#F2DEC8] truncate">
                  {p.summary ?? a.tool_name}
                </p>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {a.entity_ref ?? "—"} · proposed by {a.proposed_by} · {p.channel ?? "email"} · {p.tone ?? "gentle"} tone
                </p>
              </div>
              {amount > 0 && (
                <span className="text-sm font-semibold text-amber-300 tabular-nums shrink-0">
                  {formatCurrency(amount, true)}
                </span>
              )}
            </div>

            {(p.subject || p.body) && (
              <div className="rounded-lg bg-black/25 border border-white/[0.06] p-3 space-y-1">
                {p.subject && <p className="text-xs font-medium text-zinc-300">{p.subject}</p>}
                {p.body && <pre className="text-[11.5px] text-zinc-400 whitespace-pre-wrap font-sans leading-relaxed">{p.body}</pre>}
              </div>
            )}

            <div className="flex items-center gap-2">
              <button
                disabled={busy === a.id}
                onClick={() => decide(a.id, "approve")}
                className="flex items-center gap-1.5 rounded-lg bg-[#C08457] text-black text-xs font-medium px-3 py-1.5 disabled:opacity-40"
              >
                {busy === a.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
                Approve
              </button>
              <button
                disabled={busy === a.id}
                onClick={() => decide(a.id, "reject")}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 text-zinc-300 text-xs px-3 py-1.5 hover:bg-white/[0.04] disabled:opacity-40"
              >
                <XCircle className="w-3.5 h-3.5" /> Reject
              </button>
            </div>
          </div>
        );
      })}

      {stuck.length > 0 && (
        <section className="space-y-3 pt-4">
          <div>
            <h2 className="text-sm font-semibold text-[#F2DEC8]">Awaiting delivery</h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              You approved these, but they could not be sent. Add or fix the recipient and retry.
            </p>
          </div>
          {stuck.map((a) => {
            const p = a.payload ?? {};
            const reason = a.result?.reason === "no_contact_email"
              ? "no email on file"
              : (a.result?.error ?? "delivery failed");
            const draft = emails[a.id] ?? a.recipient_email ?? "";
            return (
              <div key={a.id} className="surface-card p-4 space-y-3 border-amber-400/15">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-[#F2DEC8] truncate">{p.summary ?? a.tool_name}</p>
                  <p className="text-[11px] text-zinc-500 mt-0.5">
                    {a.entity_ref ?? "—"} · approved {a.decided_at ? new Date(a.decided_at).toLocaleString() : ""} · <span className="text-amber-300">{reason}</span>
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    type="email"
                    value={draft}
                    onChange={(e) => setEmails((m) => ({ ...m, [a.id]: e.target.value }))}
                    placeholder="recipient@customer.com"
                    className="flex-1 min-w-[220px] rounded-lg bg-black/25 border border-white/10 px-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-[#C08457]/60"
                  />
                  <button
                    disabled={busy === a.id || !draft.trim()}
                    onClick={() => decide(a.id, "approve", draft.trim())}
                    className="flex items-center gap-1.5 rounded-lg bg-[#C08457] text-black text-xs font-medium px-3 py-1.5 disabled:opacity-40"
                  >
                    {busy === a.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                    Send now
                  </button>
                </div>
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}
