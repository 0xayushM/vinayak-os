"use client";

import { useEffect, useRef, useState } from "react";
import {
  Search, ChevronUp, ChevronDown, ChevronsUpDown,
  ChevronLeft, ChevronRight, Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";

export interface ServerColumn<T> {
  /** Stable key; if `sortKey` is set the header is clickable. */
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  cell: (row: T) => React.ReactNode;
  /** Server-side sort key. Omit to make the column non-sortable. */
  sortKey?: string;
  className?: string;
}

export interface ServerSort {
  sort: string;
  direction: "asc" | "desc";
}

interface FilterableTableProps<T> {
  columns: ServerColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Current 0-based page and total page count from the server. */
  page: number;
  pageCount: number;
  /** Total matched rows (after filters) for the footer count. */
  filteredTotal: number;
  pageSize: number;
  sort: ServerSort;
  loading?: boolean;
  emptyMessage?: string;
  searchPlaceholder?: string;
  /** Live search string (controlled). */
  search: string;
  onSearchChange: (next: string) => void;
  onSortChange: (next: ServerSort) => void;
  onPageChange: (next: number) => void;
  /** Optional extra filter controls rendered in the toolbar. */
  toolbar?: React.ReactNode;
}

export function FilterableTable<T>({
  columns, rows, rowKey,
  page, pageCount, filteredTotal, pageSize, sort,
  loading, emptyMessage = "No matching rows.",
  searchPlaceholder = "Search…",
  search, onSearchChange, onSortChange, onPageChange, toolbar,
}: FilterableTableProps<T>) {
  // Debounce the search box so we don't fire a request per keystroke.
  const [local, setLocal] = useState(search);
  const first = useRef(true);
  useEffect(() => { setLocal(search); }, [search]);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    const t = setTimeout(() => { if (local !== search) onSearchChange(local); }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local]);

  function toggleSort(col: ServerColumn<T>) {
    if (!col.sortKey) return;
    if (sort.sort !== col.sortKey) {
      onSortChange({ sort: col.sortKey, direction: "desc" });
    } else {
      onSortChange({ sort: col.sortKey, direction: sort.direction === "desc" ? "asc" : "desc" });
    }
    onPageChange(0);
  }

  const alignClass = (a?: string) =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  const from = filteredTotal === 0 ? 0 : page * pageSize + 1;
  const to   = Math.min((page + 1) * pageSize, filteredTotal);

  return (
    <div className="flex flex-col gap-3">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            value={local}
            onChange={(e) => setLocal(e.target.value)}
            placeholder={searchPlaceholder}
            className="w-full bg-[var(--bg-elevated)] text-zinc-200 text-xs rounded-lg pl-8 pr-3 py-2 border border-white/[0.08] focus:border-indigo-500 focus:outline-none placeholder-zinc-600"
          />
        </div>
        {toolbar}
        {loading && <Loader2 className="w-4 h-4 text-zinc-600 animate-spin shrink-0" />}
      </div>

      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-xs border-separate border-spacing-0">
          <thead>
            <tr>
              {columns.map((col) => {
                const sortable = !!col.sortKey;
                const activeSort = sort.sort === col.sortKey;
                return (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col)}
                    className={cn(
                      "sticky top-0 bg-[var(--bg-elevated)]/80 backdrop-blur-sm py-2.5 px-2 font-medium text-zinc-500 border-b border-white/[0.07] whitespace-nowrap",
                      alignClass(col.align),
                      sortable && "cursor-pointer select-none hover:text-zinc-300 transition-colors",
                      col.className,
                    )}
                  >
                    <span className={cn("inline-flex items-center gap-1", col.align === "right" && "flex-row-reverse")}>
                      {col.header}
                      {sortable && (activeSort ? (
                        sort.direction === "asc"
                          ? <ChevronUp className="w-3 h-3 text-indigo-400" />
                          : <ChevronDown className="w-3 h-3 text-indigo-400" />
                      ) : (
                        <ChevronsUpDown className="w-3 h-3 text-zinc-700" />
                      ))}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)} className="hover:bg-white/[0.02] transition-colors">
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      "py-2.5 px-2 border-b border-white/[0.04] text-zinc-300",
                      alignClass(col.align),
                      col.align === "right" && "tabular-nums",
                      col.className,
                    )}
                  >
                    {col.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {rows.length === 0 && !loading && (
        <p className="text-xs text-zinc-600 py-6 text-center">{emptyMessage}</p>
      )}

      <div className="flex items-center justify-between text-[11px] text-zinc-500">
        <span className="tabular-nums">
          {from}–{to} of {filteredTotal.toLocaleString("en-IN")}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onPageChange(Math.max(0, page - 1))}
            disabled={page === 0}
            className="p-1 rounded-md hover:bg-white/[0.05] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
            aria-label="Previous page"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="tabular-nums px-1">{page + 1} / {Math.max(1, pageCount)}</span>
          <button
            onClick={() => onPageChange(Math.min(pageCount - 1, page + 1))}
            disabled={page >= pageCount - 1}
            className="p-1 rounded-md hover:bg-white/[0.05] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
            aria-label="Next page"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
