"use client";

import { useMemo, useRef, useState } from "react";
import { Download, Loader2, Upload, X, AtSign } from "lucide-react";
import {
  useContactsCoverage, previewContactsImport, commitContactsImport,
  type ContactsCoverage, type ImportPreview, type ImportPreviewRow, type ImportStatus,
} from "@/hooks/useCollections";
import { cn, formatCurrency } from "@/lib/utils/cn";

/**
 * Who a reminder can reach — and the thirty-minute job that fixes the rest.
 *
 * A chase list is a list of letters with nowhere to go until each customer
 * has an email on file. This panel says how many do, names the ones that
 * don't (largest balance first), hands the accountant a CSV already filled
 * with those names, and reads it back.
 *
 * Reading back is a preview, not an import. Every row shows what it matched —
 * and, when it matched only after ignoring "Pvt Ltd", to whom — and nothing
 * is written until the rows are ticked. Replacing an email already on file is
 * shown side by side and never pre-ticked: a stale sheet quietly overwriting a
 * working address is how reminders stop arriving without anyone noticing.
 */

const MAX_FILE_BYTES = 2_000_000;

const STATUS: Record<ImportStatus, { label: string; cls: string }> = {
  matched:   { label: "Matched",       cls: "border-emerald-400/30 text-emerald-300" },
  fuzzy:     { label: "Close match",   cls: "border-sky-400/30 text-sky-300" },
  ambiguous: { label: "Which one?",    cls: "border-amber-300/30 text-amber-300" },
  unmatched: { label: "No customer",   cls: "border-white/15 text-zinc-400" },
  invalid:   { label: "Can't use",     cls: "border-red-400/30 text-red-300" },
  duplicate: { label: "Repeat",        cls: "border-white/15 text-zinc-500" },
  unchanged: { label: "Already saved", cls: "border-white/10 text-zinc-500" },
};

const COUNT_ORDER: ImportStatus[] = [
  "matched", "fuzzy", "ambiguous", "unmatched", "invalid", "duplicate", "unchanged",
];

/** Excel reads a cell starting with = + - @ as a formula; a leading quote
 *  keeps it text. The importer's loose match ignores the quote. */
function csvCell(v: string | null | undefined): string {
  let s = v ?? "";
  if (/^[=+\-@]/.test(s)) s = `'${s}`;
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadTemplate(cov: ContactsCoverage) {
  const lines = ["Customer Name,Email,Mobile"];
  for (const u of cov.unreachable) lines.push([csvCell(u.customer_name), "", csvCell(u.phone)].join(","));
  const blob = new Blob([lines.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "customer-contacts-to-fill.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Excel on Windows often saves "CSV" as Windows-1252, not UTF-8. */
async function readFileText(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buf);
  } catch {
    return new TextDecoder("windows-1252").decode(buf);
  }
}

/** Only a row that resolves to one customer and changes something can be saved. */
function canInclude(r: ImportPreviewRow, picked: string | undefined): boolean {
  if (r.status === "matched" || r.status === "fuzzy") return true;
  return r.status === "ambiguous" && !!picked;
}

function RowNote({ r }: { r: ImportPreviewRow }) {
  const notes: string[] = [];
  if (r.status === "fuzzy" && r.customer_ref) notes.push(`matched to “${r.customer_ref}”`);
  if (r.status === "unmatched") notes.push("no customer by this name in the receivables book");
  if (r.status === "duplicate" && r.duplicate_of) notes.push(`same customer as row ${r.duplicate_of}`);
  if (r.status === "unchanged") notes.push("already on file");
  if (r.overwrites.includes("email")) notes.push(`replaces ${r.existing_email}`);
  if (r.overwrites.includes("phone")) notes.push(`replaces phone ${r.existing_phone}`);
  notes.push(...r.problems);
  return (
    <span className={cn("text-[11px]", r.overwrites.length ? "text-amber-300/90" : "text-zinc-500")}>
      {notes.join(" · ")}
    </span>
  );
}

function PreviewTable({
  preview, onDone, onCancel,
}: { preview: ImportPreview; onDone: (msg: string) => void; onCancel: () => void }) {
  const [ticked, setTicked] = useState<Record<number, boolean>>(
    () => Object.fromEntries(preview.rows.map((r) => [r.line, r.include])),
  );
  const [picked, setPicked] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const selected = preview.rows.filter((r) => ticked[r.line] && canInclude(r, picked[r.line]));
  // Rows that can't be saved are still shown — hiding them is how an import
  // "loses" customers — but after the ones that need a decision.
  const visible = useMemo(() => {
    const rank = (r: ImportPreviewRow) =>
      r.overwrites.length ? 0 : r.status === "ambiguous" ? 1 : canInclude(r, "x") ? 2 : 3;
    const sorted = [...preview.rows].sort((a, b) => rank(a) - rank(b) || a.line - b.line);
    return showAll ? sorted : sorted.slice(0, 60);
  }, [preview.rows, showAll]);

  async function commit() {
    // Two sheet rows resolving to one customer through a picked candidate
    // would race; the server takes the first and reports the second.
    const rows = selected.map((r) => ({
      customer_ref: (r.status === "ambiguous" ? picked[r.line] : r.customer_ref) as string,
      email: r.email, phone: r.phone,
    }));
    setBusy(true);
    setError(null);
    try {
      const res = await commitContactsImport(rows);
      const rej = res.rejected.length ? ` · ${res.rejected.length} not saved (${res.rejected[0].reason})` : "";
      onDone(`Saved ${res.saved} contact${res.saved === 1 ? "" : "s"}${rej}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11.5px] text-zinc-400 mr-1">
          {preview.filename ?? "File"} · {preview.total} rows
        </span>
        {COUNT_ORDER.filter((s) => preview.counts[s]).map((s) => (
          <span key={s} className={cn("text-[10.5px] px-1.5 py-0.5 rounded-full border", STATUS[s].cls)}>
            {preview.counts[s]} {STATUS[s].label.toLowerCase()}
          </span>
        ))}
        {preview.overwrites > 0 && (
          <span className="text-[10.5px] px-1.5 py-0.5 rounded-full border border-amber-300/40 text-amber-300">
            {preview.overwrites} would replace what’s on file
          </span>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-white/[0.05]">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-[0.08em] text-zinc-500 bg-black/20">
              <th className="px-2 py-2 w-8" />
              <th className="px-2 py-2">Row</th>
              <th className="px-2 py-2">Name in the sheet</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2">Email</th>
              <th className="px-2 py-2">Phone</th>
              <th className="px-2 py-2">Note</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => {
              const includable = canInclude(r, picked[r.line]);
              return (
                <tr key={r.line} className="border-t border-white/[0.04] align-top">
                  <td className="px-2 py-1.5">
                    <input
                      type="checkbox"
                      aria-label={`Include row ${r.line}`}
                      disabled={!includable || busy}
                      checked={includable && !!ticked[r.line]}
                      onChange={(e) => setTicked((t) => ({ ...t, [r.line]: e.target.checked }))}
                    />
                  </td>
                  <td className="px-2 py-1.5 text-zinc-500 tabular-nums">{r.line}</td>
                  <td className="px-2 py-1.5 text-zinc-200">{r.name || <span className="text-zinc-600">—</span>}</td>
                  <td className="px-2 py-1.5">
                    <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full border whitespace-nowrap", STATUS[r.status].cls)}>
                      {STATUS[r.status].label}
                    </span>
                    {r.status === "ambiguous" && (
                      <select
                        className="mt-1 block max-w-[220px] bg-black/30 border border-white/10 rounded-lg px-1.5 py-1 text-[11px] text-zinc-200 [color-scheme:dark]"
                        value={picked[r.line] ?? ""}
                        onChange={(e) => {
                          const v = e.target.value;
                          setPicked((p) => ({ ...p, [r.line]: v }));
                          setTicked((t) => ({ ...t, [r.line]: !!v }));
                        }}
                      >
                        <option value="">Choose the customer…</option>
                        {r.candidates.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-zinc-300 break-all">{r.email ?? ""}</td>
                  <td className="px-2 py-1.5 text-zinc-300 whitespace-nowrap">{r.phone ?? ""}</td>
                  <td className="px-2 py-1.5"><RowNote r={r} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!showAll && preview.rows.length > visible.length && (
        <button onClick={() => setShowAll(true)} className="text-[11px] text-zinc-400 hover:text-[#C08457]">
          Show all {preview.rows.length} rows
        </button>
      )}

      {error && <p className="text-[11.5px] text-red-300">{error}</p>}
      <div className="flex items-center gap-2">
        <button
          onClick={commit}
          disabled={busy || selected.length === 0}
          className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg bg-[#C08457] text-black disabled:opacity-40"
        >
          {busy && <Loader2 className="w-3 h-3 animate-spin" />}
          Save {selected.length} contact{selected.length === 1 ? "" : "s"}
        </button>
        <button onClick={onCancel} disabled={busy}
          className="text-[12px] px-3 py-1.5 rounded-lg border border-white/10 text-zinc-400 hover:bg-white/[0.04]">
          Discard
        </button>
        <span className="text-[11px] text-zinc-600">
          Empty cells never erase what’s on file.
        </span>
      </div>
    </div>
  );
}

export function ContactsImportPanel() {
  const { data: cov, isLoading, mutate } = useContactsCoverage();
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    setNotice(null);
    if (file.size > MAX_FILE_BYTES) {
      setError("That file is too large for a contact list (limit 2 MB).");
      return;
    }
    setReading(true);
    try {
      const text = await readFileText(file);
      setPreview(await previewContactsImport(text, file.name));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read the file");
    } finally {
      setReading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  if (isLoading) return <div className="surface-card p-4 text-sm text-zinc-500">Loading…</div>;
  if (!cov) return null;
  // Nobody is overdue and nothing is being imported: nothing to say.
  if (cov.overdue_customers === 0 && !preview) return null;

  const top = cov.unreachable.slice(0, 6);

  return (
    <div className="surface-card p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <AtSign className="w-4 h-4 text-[#C08457] mt-0.5 shrink-0" />
          <div>
            <h3 className="text-[13px] font-semibold text-[#F2DEC8]">
              {cov.with_email} of {cov.overdue_customers} overdue customers can be reached
            </h3>
            <p className="text-[11.5px] text-zinc-500 mt-0.5">
              {cov.unreachable_count > 0
                ? <>Reminders go by email. {cov.unreachable_count} without one owe {formatCurrency(cov.unreachable_value, true)}
                    {cov.with_phone > 0 ? ` · ${cov.with_phone} have a phone on file` : ""}.</>
                : "Every overdue customer has an email on file."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {cov.unreachable_count > 0 && (
            <button
              onClick={() => downloadTemplate(cov)}
              title="A CSV with the unreachable customers' names, ready for emails and mobiles"
              className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-white/10 text-zinc-400 hover:text-[#C08457] hover:bg-white/[0.04] transition"
            >
              <Download className="w-3 h-3" /> Template ({cov.unreachable_count})
            </button>
          )}
          <button
            onClick={() => fileRef.current?.click()}
            disabled={reading}
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg border border-white/10 text-zinc-300 hover:text-[#C08457] hover:bg-white/[0.04] transition disabled:opacity-40"
          >
            {reading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
            Upload contacts CSV
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv,text/plain"
            className="hidden"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
        </div>
      </div>

      {error && (
        <p className="flex items-center gap-1.5 text-[11.5px] text-red-300">
          <X className="w-3 h-3" /> {error}
        </p>
      )}
      {notice && <p className="text-[11.5px] text-emerald-300">{notice}</p>}

      {preview ? (
        <PreviewTable
          key={`${preview.filename}-${preview.total}`}
          preview={preview}
          onCancel={() => setPreview(null)}
          onDone={(msg) => { setPreview(null); setNotice(msg); mutate(); }}
        />
      ) : top.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1.5">
          {top.map((u) => (
            <div key={u.customer_name}
              className="rounded-lg bg-black/20 border border-white/[0.05] px-3 py-2 min-w-0">
              <p className="text-[12px] text-zinc-200 truncate">{u.customer_name}</p>
              <p className="text-[11px] text-zinc-500 tabular-nums">
                {formatCurrency(u.outstanding, true)} · {u.days_overdue} days
                {u.phone ? ` · ${u.phone}` : ""}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
