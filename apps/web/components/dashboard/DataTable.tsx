"use client";

import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export interface Column<T> {
  /** Stable key, also used as the default sort accessor. */
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  /** Cell renderer. */
  cell: (row: T) => React.ReactNode;
  /** Value used for sorting; defaults to no sorting for this column. */
  sortValue?: (row: T) => string | number;
  /** Tailwind classes for the <td>/<th>. */
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  pageSize?: number;
  emptyMessage?: string;
  initialSort?: { key: string; dir: "asc" | "desc" };
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  pageSize = 15,
  emptyMessage = "No data to show.",
  initialSort,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(
    initialSort ?? null,
  );
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }, [rows, sort, columns]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const clampedPage = Math.min(page, pageCount - 1);
  const pageRows = sorted.slice(clampedPage * pageSize, clampedPage * pageSize + pageSize);

  function toggleSort(col: Column<T>) {
    if (!col.sortValue) return;
    setPage(0);
    setSort((prev) => {
      if (prev?.key !== col.key) return { key: col.key, dir: "desc" };
      if (prev.dir === "desc") return { key: col.key, dir: "asc" };
      return null;
    });
  }

  const alignClass = (a?: string) =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  if (rows.length === 0) {
    return <p className="text-xs text-zinc-600 py-6 text-center">{emptyMessage}</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-xs border-separate border-spacing-0">
          <thead>
            <tr>
              {columns.map((col) => {
                const sortable = !!col.sortValue;
                const activeSort = sort?.key === col.key;
                return (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col)}
                    className={cn(
                      "sticky top-0 bg-[var(--bg-elevated)]/80 backdrop-blur-sm py-2.5 px-2 font-medium text-zinc-500 border-b border-white/[0.07] whitespace-nowrap",
                      alignClass(col.align),
                      sortable && "cursor-pointer select-none hover:text-[#F2DEC8]/75 transition-colors",
                      col.className,
                    )}
                  >
                    <span
                      className={cn(
                        "inline-flex items-center gap-1",
                        col.align === "right" && "flex-row-reverse",
                      )}
                    >
                      {col.header}
                      {sortable &&
                        (activeSort ? (
                          sort!.dir === "asc" ? (
                            <ChevronUp className="w-3 h-3 text-[#C08457]" />
                          ) : (
                            <ChevronDown className="w-3 h-3 text-[#C08457]" />
                          )
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
            {pageRows.map((row) => (
              <tr
                key={rowKey(row)}
                className="hover:bg-white/[0.02] transition-colors"
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      "py-2.5 px-2 border-b border-white/[0.04] text-[#F2DEC8]/75",
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

      {pageCount > 1 && (
        <div className="flex items-center justify-between text-[11px] text-zinc-500">
          <span className="tabular-nums">
            {clampedPage * pageSize + 1}–{Math.min((clampedPage + 1) * pageSize, sorted.length)} of{" "}
            {sorted.length}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={clampedPage === 0}
              className="p-1 rounded-md hover:bg-white/[0.05] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
              aria-label="Previous page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="tabular-nums px-1">
              {clampedPage + 1} / {pageCount}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={clampedPage >= pageCount - 1}
              className="p-1 rounded-md hover:bg-white/[0.05] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
              aria-label="Next page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
