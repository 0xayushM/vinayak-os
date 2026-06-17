"use client";

/**
 * MarkdownLite — a tiny, dependency-free renderer for the subset of Markdown the
 * AI uses: bold (**x**), inline code (`x`), bullet lists (-, •, *), numbered
 * lists, and simple pipe tables. Anything else renders as a paragraph.
 */
import React from "react";

function renderInline(text: string, keyBase: string): React.ReactNode[] {
  // Split on **bold** and `code`, keep delimiters.
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return <strong key={`${keyBase}-${i}`} className="text-[#F2DEC8] font-semibold">{p.slice(2, -2)}</strong>;
    }
    if (p.startsWith("`") && p.endsWith("`")) {
      return <code key={`${keyBase}-${i}`} className="text-[#C08457] bg-white/[0.05] rounded px-1 py-0.5 text-[11px]">{p.slice(1, -1)}</code>;
    }
    return <React.Fragment key={`${keyBase}-${i}`}>{p}</React.Fragment>;
  });
}

function isTableRow(l: string) { return l.trim().startsWith("|") && l.includes("|"); }
function isTableSep(l: string) { return /^\s*\|?[\s:|-]+\|?\s*$/.test(l) && l.includes("-"); }

export function MarkdownLite({ text }: { text: string }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Table
    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = line.split("|").slice(1, -1).map((c) => c.trim());
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && isTableRow(lines[i])) {
        rows.push(lines[i].split("|").slice(1, -1).map((c) => c.trim()));
        i++;
      }
      blocks.push(
        <div key={`t-${i}`} className="overflow-x-auto my-2">
          <table className="w-full text-[12px] border-collapse">
            <thead>
              <tr>{header.map((h, j) => (
                <th key={j} className="text-left font-medium text-zinc-500 border-b border-white/[0.1] py-1.5 pr-3">{renderInline(h, `th-${j}`)}</th>
              ))}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri} className="border-b border-white/[0.04]">
                  {r.map((c, ci) => (
                    <td key={ci} className={`py-1.5 pr-3 ${ci === 0 ? "text-[#F2DEC8]/80" : "text-[#F2DEC8]/90 tabular-nums"}`}>{renderInline(c, `td-${ri}-${ci}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    // Bullet list
    if (/^\s*[-•*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-•*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-•*]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={`ul-${i}`} className="list-disc pl-5 my-1.5 space-y-1 text-[13px] text-[#F2DEC8]/85">
          {items.map((it, j) => <li key={j}>{renderInline(it, `li-${i}-${j}`)}</li>)}
        </ul>,
      );
      continue;
    }

    // Numbered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      blocks.push(
        <ol key={`ol-${i}`} className="list-decimal pl-5 my-1.5 space-y-1 text-[13px] text-[#F2DEC8]/85">
          {items.map((it, j) => <li key={j}>{renderInline(it, `oli-${i}-${j}`)}</li>)}
        </ol>,
      );
      continue;
    }

    // Blank line
    if (line.trim() === "") { i++; continue; }

    // Paragraph
    blocks.push(
      <p key={`p-${i}`} className="text-[13px] leading-relaxed text-[#F2DEC8]/90 my-1">{renderInline(line, `p-${i}`)}</p>,
    );
    i++;
  }

  return <div className="space-y-0.5">{blocks}</div>;
}
