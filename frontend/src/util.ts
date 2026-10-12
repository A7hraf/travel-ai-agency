import { useEffect, useRef } from "react";
import { currentLocale, tr } from "./lang";

export const ROLE_LABELS: Record<string, string> = {
  system_admin: "System admin",
  company_admin: "Company admin",
  support: "Support",
  ticket_agent: "Ticket employee",
};

/** Same texts as the server's permission catalog (backend/app/permissions.py). */
export const PERMISSION_LABELS: Record<string, string> = {
  "packages.view": "View travel packages",
  "packages.manage": "Create, edit and delete travel packages",
  "conversations.view": "View customer conversations",
  "conversations.reply": "Reply to customers and take over from the AI",
  "tickets.view": "View booking tickets",
  "tickets.manage": "Update booking tickets (status, payment, notes)",
  "tickets.assign": "Assign tickets to other employees",
  "users.manage": "Create, edit and delete employee accounts",
  "settings.manage": "Manage company settings (AI persona, knowledge, WhatsApp)",
  "reports.view": "View the dashboard and statistics",
};

export const TICKET_STATUS_LABELS: Record<string, string> = {
  pending_payment: "Waiting for payment",
  in_progress: "In progress",
  paid: "Paid",
  confirmed: "Confirmed",
  cancelled: "Cancelled",
};

export const CONVERSATION_STATUS_LABELS: Record<string, string> = {
  ai: "AI handling",
  human: "Needs a human",
  closed: "Closed",
};

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(currentLocale(), { dateStyle: "medium", timeStyle: "short" });
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return d.toLocaleDateString(currentLocale(), { day: "numeric", month: "short", year: "numeric" });
}

export function timeAgo(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return tr("just now");
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return tr("{n} min ago", { n: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 24) return tr("{n} h ago", { n: hours });
  return shortDate(iso);
}

/** Calls `fn` now and then every `ms` milliseconds while the component is mounted. */
export function usePolling(fn: () => void, ms: number, deps: unknown[] = []) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    saved.current();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") saved.current();
    }, ms);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);
}

/** A stable gradient per destination, used as the package card background. */
export function gradientFor(text: string): string {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `linear-gradient(135deg, hsl(${h} 70% 45%), hsl(${(h + 40) % 360} 75% 35%))`;
}

export function customerLabel(c: { name: string | null; phone: string | null; email: string | null; id: number }) {
  return c.name || c.phone || c.email || tr("Visitor #{id}", { id: c.id });
}
