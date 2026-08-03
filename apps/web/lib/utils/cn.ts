import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number, compact = false): string {
  if (compact) {
    // Handle the sign separately so negatives compact too (else e.g. -2074626
    // fell through every `>=` check and printed the raw number).
    const sign = value < 0 ? "-" : "";
    const a = Math.abs(value);
    if (a >= 1_00_00_000) return `${sign}₹${(a / 1_00_00_000).toFixed(1)}Cr`;
    if (a >= 1_00_000)   return `${sign}₹${(a / 1_00_000).toFixed(1)}L`;
    if (a >= 1_000)      return `${sign}₹${(a / 1_000).toFixed(1)}K`;
    return `${sign}₹${a.toFixed(0)}`;
  }
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-IN").format(n);
}

// ── Owner-friendly sync status ────────────────────────────────────────────────
// Raw pipeline errors (e.g. "HTTP 500 — {'errors': {'exception': 'OperationalError'}}")
// read like a crash to a business owner. Translate them into calm, plain language
// and never surface the raw payload in the UI.
export function friendlySyncError(raw?: string | null): string {
  const s = (raw ?? "").toLowerCase();
  if (!s) return "Sync didn’t finish. It will retry automatically.";
  if (s.includes("login") || s.includes("401") || s.includes("auth") || s.includes("credential") || s.includes("unauthor"))
    return "Couldn’t sign in to the source — please re-check the credentials.";
  if (s.includes("timeout") || s.includes("429") || s.includes("rate"))
    return "The source is busy right now — retrying shortly.";
  if (s.includes("500") || s.includes("operationalerror") || s.includes("server") || s.includes("503") || s.includes("502"))
    return "The source had a temporary problem — retrying automatically.";
  if (s.includes("network") || s.includes("connect") || s.includes("unreachable") || s.includes("dns"))
    return "Couldn’t reach the source — we’ll retry automatically.";
  return "Sync didn’t finish. It will retry automatically.";
}

const SYNC_LABELS: Record<string, string> = {
  ar_aging: "Receivables", sales_invoices: "Sales invoices", sales_orders: "Sales orders",
  purchase_invoices: "Purchase invoices", purchase_orders: "Purchase orders",
  sales_quotations: "Quotes", inventory_valuation: "Inventory", grn_qir: "Goods received",
  process_details: "Production", process_routing: "BOM / routing",
  zoho_invoices: "Sales invoices", zoho_bills: "Purchase invoices",
  zoho_items: "Inventory", zoho_contacts: "Contacts",
};
export function syncLabel(name: string): string {
  return SYNC_LABELS[name] ?? name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "Never synced";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)   return "Just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
