import { FormEvent, useEffect, useId, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { get, patch } from "../api";
import { useAuth } from "../auth";
import { Binoculars, ChatsCircle, Check, CheckCircle, MagnifyingGlass, WarningCircle } from "../components/Icon";
import { Money, moneyText } from "../components/Money";
import { ConfirmRequest, ConfirmSheet, PushPanel } from "../components/staff/Sheet";
import { useStaff } from "../components/staff/StaffContext";
import { ErrorBox, Field } from "../components/ui";
import { trServer, useI18n } from "../lang";
import type { Ticket, TicketEvent, TicketStatus, User } from "../types";
import {
  customerLabel, dateTime, NEEDS_PAYMENT_REFERENCE, NEXT_TICKET_STATUSES, shortDate, TICKET_STATUS_LABELS,
  travelersText, usePolling,
} from "../util";

type Filter = "open" | "paid" | "confirmed" | "all";
const OPEN = ["pending_payment", "in_progress"];
const FILTERS: { value: Filter; label: string; match: (s: string) => boolean }[] = [
  { value: "open", label: "Open", match: (s) => OPEN.includes(s) },
  { value: "paid", label: "Paid", match: (s) => s === "paid" },
  { value: "confirmed", label: "Confirmed", match: (s) => s === "confirmed" },
  { value: "all", label: "All", match: () => true },
];

/** Status colours of the design (always shown with a text label). */
const STATUS_COLOR: Record<string, string> = {
  pending_payment: "var(--st-waiting)",
  in_progress: "var(--st-progress)",
  paid: "var(--st-paid)",
  confirmed: "var(--st-confirmed)",
  cancelled: "var(--st-cancelled)",
};

// Tickets this browser has opened: new ones keep a cyan glow until someone looks at them.
const SEEN_KEY = "travel_seen_tickets";
function readSeen(): Set<number> {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) ?? "[]") as number[]);
  } catch {
    return new Set();
  }
}
function markSeen(id: number) {
  try {
    const seen = readSeen();
    seen.add(id);
    localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-300)));
  } catch {
    /* storage unavailable */
  }
}
const isNew = (tk: Ticket, seen: Set<number>) =>
  tk.status === "pending_payment" && !seen.has(tk.id) && Date.now() - new Date(tk.created_at).getTime() < 24 * 3600 * 1000;

export default function Tickets() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>("open");
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState("");
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [seen, setSeen] = useState(readSeen);
  const openId = params.get("open");

  const load = () => {
    const q = new URLSearchParams({ limit: "1000" });
    if (mine) q.set("mine", "true");
    if (search.trim()) q.set("q", search.trim());
    get<Ticket[]>(`/api/tickets?${q}`).then(setTickets).catch(() => {});
  };
  usePolling(load, 10000, [mine, search]);

  useEffect(() => {
    if (!openId) return;
    markSeen(Number(openId));
    setSeen(readSeen());
  }, [openId]);

  const shown = tickets?.filter((tk) => FILTERS.find((f) => f.value === filter)!.match(tk.status)) ?? null;
  // Amount still to collect, per currency (other currencies are never added to OMR).
  const toCollect = new Map<string, number>();
  tickets?.filter((tk) => OPEN.includes(tk.status)).forEach((tk) => toCollect.set(tk.currency, (toCollect.get(tk.currency) ?? 0) + tk.total_price));

  return (
    <div className="tk-page">
      <div className="tk-head">
        <h1 className="screen-title">{t("Tickets")}</h1>
        {toCollect.size > 0 && (
          <div className="tk-collect">
            {[...toCollect].map(([cur, v], i) => (
              <span key={cur}>{i > 0 && " · "}<Money value={v} currency={cur} /> {t("to collect")}</span>
            ))}
          </div>
        )}
      </div>
      <div className="tk-tools">
        <div className="chips scroll" role="group" aria-label={t("Status")}>
          {FILTERS.map((f) => (
            <button key={f.value} type="button" className={`chip-btn tk-chip ${filter === f.value ? "active" : ""}`}
              aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}>
              {t(f.label)} <span className="tk-chip-n">{tickets?.filter((tk) => f.match(tk.status)).length ?? 0}</span>
            </button>
          ))}
          <button type="button" className={`chip-btn tk-chip ${mine ? "active" : ""}`} aria-pressed={mine} onClick={() => setMine(!mine)}>
            {t("Assigned to me")}
          </button>
        </div>
        <label className="search-field">
          <MagnifyingGlass aria-hidden="true" />
          <input type="search" placeholder={t("Reference, name or phone")} aria-label={t("Reference, name or phone")} value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </label>
      </div>

      {shown === null ? (
        <div className="tk-grid">{[0, 1, 2].map((i) => <div key={i} className="skeleton tk-skel" />)}</div>
      ) : shown.length === 0 ? (
        <div className="empty">
          <Binoculars className="empty-icon" aria-hidden="true" />
          {tickets && tickets.length === 0 && !mine && !search.trim() ? (
            t("No tickets yet. They appear here when the AI closes a booking.")
          ) : (
            <>
              <strong>{t("No tickets match")}</strong>
              {t("Try another status, or clear the search.")}
            </>
          )}
        </div>
      ) : (
        <div className="tk-grid">
          {shown.map((tk) => (
            <Link key={tk.id} to={`/app/tickets?open=${tk.id}`} className={`tk-card ${isNew(tk, seen) ? "new" : ""}`}>
              <span className="tk-card-top">
                <bdi dir="ltr" className="tk-ref">{tk.reference}</bdi>
                <span className={`pill st-${tk.status}`}>{t(TICKET_STATUS_LABELS[tk.status])}</span>
              </span>
              <span className="tk-who"><bdi>{tk.lead_traveler_name || customerLabel(tk.customer)}</bdi> · {tk.package_title}</span>
              <span className="tk-card-foot">
                <span>{shortDate(tk.departure_date)} · {travelersText(tk.adults, tk.children)}</span>
                <span className="tk-total"><Money value={tk.total_price} currency={tk.currency} /></span>
              </span>
              <span className="tk-assignee">{tk.assigned_to ? tk.assigned_to.full_name : t("Unassigned")}</span>
            </Link>
          ))}
        </div>
      )}

      {openId && <TicketPanel id={Number(openId)} onClose={() => setParams({})} onSaved={load} />}
    </div>
  );
}

type TicketForm = { assigned: string; payment_reference: string; internal_notes: string; total_price: string };

function formFrom(tk: Ticket): TicketForm {
  return {
    assigned: tk.assigned_to ? String(tk.assigned_to.id) : "",
    payment_reference: tk.payment_reference ?? "",
    internal_notes: tk.internal_notes,
    total_price: String(tk.total_price),
  };
}

const STEPS: TicketStatus[] = ["pending_payment", "in_progress", "paid", "confirmed"];

/** Button text for a move to a status. */
function actionLabel(from: string, to: string): string {
  if (to === "in_progress") return "Start working on it";
  if (to === "paid") return "Mark as paid";
  if (to === "confirmed") return "Confirm the trip";
  if (to === "cancelled") return "Cancel booking";
  return from === "cancelled" ? "Reopen booking" : "Back to waiting for payment";
}

function TicketPanel({ id, onClose, onSaved }: { id: number; onClose: () => void; onSaved: () => void }) {
  const { user, can } = useAuth();
  const { t, lang } = useI18n();
  const { agentName, toast, refreshCounts } = useStaff();
  const titleId = useId();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [team, setTeam] = useState<User[]>([]);
  const [events, setEvents] = useState<TicketEvent[] | null>(null);
  const [form, setForm] = useState<TicketForm>({ assigned: "", payment_reference: "", internal_notes: "", total_price: "" });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refError, setRefError] = useState(0);
  const [confirmReq, setConfirmReq] = useState<ConfirmRequest | null>(null);
  const [grown, setGrown] = useState(false);

  const loadEvents = () => get<TicketEvent[]>(`/api/tickets/${id}/events`).then(setEvents).catch(() => setEvents([]));

  useEffect(() => {
    get<Ticket>(`/api/tickets/${id}`).then((tk) => {
      setTicket(tk);
      setForm(formFrom(tk));
    }).catch((e) => setError(e.message));
    get<User[]>("/api/team").then(setTeam).catch(() => {});
    loadEvents();
    // The stepper line grows in once the ticket is shown.
    const timer = window.setTimeout(() => setGrown(true), 120);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const canManage = can("tickets.manage");
  const canAssign = can("tickets.assign");
  const isAdmin = user?.role === "company_admin";
  const dirty = !!ticket && JSON.stringify(form) !== JSON.stringify(formFrom(ticket));

  const requestClose = () => {
    if (!dirty) return onClose();
    setConfirmReq({
      title: t("Discard your changes?"),
      okLabel: t("Discard"),
      onConfirm: onClose,
    });
  };

  // Only the changes the server accepts from the current status (a cancelled booking: admins only).
  const nexts = ticket
    ? (NEXT_TICKET_STATUSES[ticket.status] ?? []).filter(() => ticket.status !== "cancelled" || isAdmin)
    : [];
  // Mark as paid comes first when waiting for payment; Cancel always last.
  const actions = [...nexts].sort((a, b) => {
    const rank = (s: string) => (s === "cancelled" ? 9 : s === "paid" ? 0 : s === "confirmed" ? 0 : s === "in_progress" ? 1 : 2);
    return rank(a) - rank(b);
  });

  // Without tickets.assign an employee can only take a ticket nobody has, or let go of their own.
  const currentAssignee = ticket?.assigned_to ? String(ticket.assigned_to.id) : "";
  const mineOrFree = !currentAssignee || currentAssignee === String(user?.id);
  const assignOptions = canAssign
    ? team
    : team.filter((u) => String(u.id) === currentAssignee || (mineOrFree && u.id === user?.id));
  const canChangeAssignee = canManage && (canAssign || mineOrFree);

  const after = (tk: Ticket, keepEdits: boolean) => {
    setTicket(tk);
    setForm((f) => (keepEdits ? { ...formFrom(tk), assigned: f.assigned === currentAssignee ? formFrom(tk).assigned : f.assigned,
      internal_notes: f.internal_notes, total_price: f.total_price } : formFrom(tk)));
    onSaved();
    refreshCounts();
    loadEvents();
  };

  const move = async (to: string) => {
    if (!ticket || busy) return;
    setError(null);
    setSaved(false);
    const ref = form.payment_reference.trim();
    if (NEEDS_PAYMENT_REFERENCE.includes(to) && !ref) {
      setRefError((n) => n + 1);
      document.getElementById(`payref-${id}`)?.focus();
      return;
    }
    const body: Record<string, unknown> = { status: to as TicketStatus };
    if (ref !== (ticket.payment_reference ?? "")) body.payment_reference = ref;
    setBusy(true);
    try {
      const tk = await patch<Ticket>(`/api/tickets/${id}`, body);
      after(tk, true);
      toast({
        tone: "teal",
        icon: <CheckCircle weight="duotone" />,
        title: t("Saved"),
        text: t("{reference} is now {status}", { reference: tk.reference, status: t(TICKET_STATUS_LABELS[tk.status]).toLowerCase() }),
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onAction = (to: string) => {
    if (to === "cancelled") {
      setConfirmReq({
        title: t("Cancel this booking?"),
        text: t("The seats go back to the package. Only a company admin can reopen it."),
        okLabel: t("Cancel booking"),
        onConfirm: () => move(to),
      });
    } else {
      move(to);
    }
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!ticket || busy) return;
    setError(null);
    setSaved(false);
    const body: Record<string, unknown> = {};
    if (form.payment_reference.trim() !== (ticket.payment_reference ?? "")) {
      if (NEEDS_PAYMENT_REFERENCE.includes(ticket.status) && !form.payment_reference.trim()) {
        setRefError((n) => n + 1);
        return;
      }
      body.payment_reference = form.payment_reference.trim();
    }
    if (form.internal_notes !== ticket.internal_notes) body.internal_notes = form.internal_notes;
    // Only an admin may change the price; an empty field never means "0".
    if (isAdmin && form.total_price.trim() !== "" && Number(form.total_price) !== ticket.total_price) {
      body.total_price = Number(form.total_price);
    }
    if (form.assigned !== currentAssignee) {
      if (form.assigned) body.assigned_to_id = Number(form.assigned);
      else body.unassign = true;
    }
    if (Object.keys(body).length === 0) {
      setSaved(true);
      return;
    }
    setBusy(true);
    try {
      const tk = await patch<Ticket>(`/api/tickets/${id}`, body);
      after(tk, false);
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const idx = ticket ? STEPS.indexOf(ticket.status) : -1;
  const cancelled = ticket?.status === "cancelled";
  const statusColor = ticket ? STATUS_COLOR[ticket.status] : undefined;
  const showRefInput = !!ticket && canManage && !cancelled;
  const agent = agentName || t("AI agent");

  return (
    <PushPanel backLabel={t("Tickets")} onClose={requestClose} labelledBy={titleId}>
      {!ticket ? (error ? <ErrorBox error={error} /> : <div className="tk-detail">{[0, 1, 2].map((i) => <div key={i} className="skeleton tk-skel" />)}</div>) : (
        <div className="tk-detail">
          <h2 className="tk-detail-ref" id={titleId}><bdi dir="ltr">{ticket.reference}</bdi></h2>
          <div className="tk-detail-who">
            <bdi>{ticket.lead_traveler_name || customerLabel(ticket.customer)}</bdi>
            {ticket.contact_phone && <> · <bdi dir="ltr">{ticket.contact_phone}</bdi></>}
          </div>

          <ol className={`stepper ${cancelled ? "cancelled" : ""}`} aria-label={t("Status")}
            style={{ ["--step-color" as string]: statusColor, ["--progress" as string]: grown && idx > 0 ? `${(idx / 3) * 75}%` : "0%" }}>
            {STEPS.map((s, i) => {
              const state = cancelled ? "todo" : i < idx ? "done" : i === idx ? "current" : "todo";
              return (
                <li key={s} className={`step ${state}`} aria-current={state === "current" ? "step" : undefined}>
                  <span className="step-dot" style={state === "current" ? { ["--c" as string]: STATUS_COLOR[s] } : undefined}>
                    {state === "done" && <Check weight="bold" aria-hidden="true" />}
                  </span>
                  <span className="step-label">{t(TICKET_STATUS_LABELS[s])}</span>
                </li>
              );
            })}
          </ol>
          {cancelled && <div className="tk-cancelled">{t("Cancelled. The seats went back to the package.")}</div>}

          <dl className="tk-grid-details">
            <dt>{t("Package")}</dt><dd>{ticket.package_title}</dd>
            <dt>{t("Departure")}</dt><dd>{shortDate(ticket.departure_date)}</dd>
            <dt>{t("Travellers")}</dt><dd>{travelersText(ticket.adults, ticket.children)}</dd>
            <dt>{t("Total")}</dt><dd className="tk-strong"><Money value={ticket.total_price} currency={ticket.currency} /></dd>
            <dt>{t("Lead traveller")}</dt><dd><bdi>{ticket.lead_traveler_name || "—"}</bdi></dd>
            <dt>{t("Email")}</dt><dd>{ticket.contact_email ? <bdi dir="ltr">{ticket.contact_email}</bdi> : "—"}</dd>
            <dt>{t("Customer")}</dt><dd><bdi>{customerLabel(ticket.customer)}</bdi></dd>
            {ticket.special_requests && <><dt>{t("Special requests")}</dt><dd dir="auto">{ticket.special_requests}</dd></>}
            {!showRefInput && <><dt>{t("Payment reference")}</dt><dd>{ticket.payment_reference ? <bdi dir="ltr" className="tk-strong">{ticket.payment_reference}</bdi> : "—"}</dd></>}
            <dt>{t("Created by")}</dt>
            <dd>{ticket.created_by === "ai" ? t("{agent} (AI) in chat", { agent }) : t("Staff")} · {dateTime(ticket.created_at)}</dd>
          </dl>

          {ticket.conversation_id && can("conversations.view") && (
            <Link className="btn btn-soft btn-sm tk-conv-link" to={`/app/conversations/${ticket.conversation_id}`}>
              <ChatsCircle aria-hidden="true" />{t("Open the conversation")}
            </Link>
          )}

          <form onSubmit={save} className="tk-form">
            {showRefInput && (
              <div key={refError} className={`tk-ref-field ${refError ? "shake" : ""}`}>
                <label className="field-label" htmlFor={`payref-${id}`}>{t("Payment reference")}</label>
                <input id={`payref-${id}`} value={form.payment_reference} disabled={busy} dir="ltr" maxLength={200}
                  placeholder={t("Receipt or transfer number")} aria-invalid={refError > 0}
                  aria-describedby={refError ? `payref-err-${id}` : undefined}
                  className={refError ? "ref-invalid" : ""}
                  onChange={(e) => { setForm({ ...form, payment_reference: e.target.value }); setRefError(0); }} />
                {refError > 0 && (
                  <div className="tk-ref-err" id={`payref-err-${id}`} role="alert">
                    <WarningCircle aria-hidden="true" />{t("Add the payment reference to mark this ticket paid.")}
                  </div>
                )}
              </div>
            )}

            {canManage && actions.length > 0 && (
              <div className="tk-actions">
                {actions.map((s, i) => (
                  <button key={s} type="button" disabled={busy} onClick={() => onAction(s)}
                    className={`btn tk-action ${s === "cancelled" ? "btn-danger" : i === 0 ? "btn-primary" : ""}`}>
                    {t(actionLabel(ticket.status, s))}
                  </button>
                ))}
              </div>
            )}
            {busy && <div className="tk-saving" role="status">{t("Saving…")}</div>}

            <div className="tk-fields">
              <Field label={t("Assigned to")}
                hint={!canAssign && !mineOrFree ? t("Only an employee who can assign tickets can change this.") : undefined}>
                <select value={form.assigned} disabled={!canChangeAssignee || busy} onChange={(e) => setForm({ ...form, assigned: e.target.value })}>
                  {(canAssign || mineOrFree) && <option value="">— {t("nobody")} —</option>}
                  {assignOptions.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </Field>
              {isAdmin && (
                <Field label={t("Total price ({currency})", { currency: ticket.currency })} hint={t("Admins only")}>
                  <input type="number" min={0} step="0.001" value={form.total_price} disabled={!canManage || busy} required dir="ltr"
                    onChange={(e) => setForm({ ...form, total_price: e.target.value })} />
                </Field>
              )}
              <Field label={t("Internal notes")}>
                <textarea rows={3} value={form.internal_notes} disabled={!canManage || busy} dir="auto"
                  placeholder={t("Only your team sees this")}
                  onChange={(e) => setForm({ ...form, internal_notes: e.target.value })} />
              </Field>
            </div>
            <ErrorBox error={error} />
            {saved && !dirty && <div className="ok-box">{t("Saved.")}</div>}
            {canManage && (
              <button className={`btn btn-block ${dirty ? "btn-primary" : ""}`} disabled={busy}>
                {busy ? t("Saving…") : t("Save")}
              </button>
            )}
          </form>

          <TicketHistory events={events} currency={ticket.currency} lang={lang} />
        </div>
      )}
      {confirmReq && <ConfirmSheet req={confirmReq} onClose={() => setConfirmReq(null)} />}
    </PushPanel>
  );
}

function TicketHistory({ events, currency, lang }: { events: TicketEvent[] | null; currency: string; lang: "en" | "ar" }) {
  const { t } = useI18n();
  const status = (v: string | null) => (v && TICKET_STATUS_LABELS[v] ? t(TICKET_STATUS_LABELS[v]) : v ?? "—");
  const money = (v: string | null) => (v == null || v === "" || Number.isNaN(Number(v)) ? v ?? "—" : moneyText(Number(v), currency, lang));

  const describe = (ev: TicketEvent): string => {
    const who = ev.actor === "AI" ? t("AI agent") : ev.actor;
    switch (ev.action) {
      case "created":
        return ev.new_value
          ? t("{who} created the booking: {details}", { who, details: trServer(ev.new_value) })
          : t("{who} created the booking", { who });
      case "assigned":
        return ev.old_value
          ? t("{who} moved the ticket from {old} to {new}", { who, old: ev.old_value, new: ev.new_value ?? "—" })
          : t("{who} assigned the ticket to {new}", { who, new: ev.new_value ?? "—" });
      case "unassigned":
        return ev.old_value
          ? t("{who} removed {old} from the ticket", { who, old: ev.old_value })
          : t("{who} removed the assignment", { who });
      case "payment_reference":
        return ev.new_value
          ? t("{who} set the payment reference to {new}", { who, new: `⁦${ev.new_value}⁩` })
          : t("{who} removed the payment reference", { who });
      case "price":
        return t("{who} changed the price from {old} to {new}", { who, old: money(ev.old_value), new: money(ev.new_value) });
      case "status":
        return t("{who} changed the status from {old} to {new}", { who, old: status(ev.old_value), new: status(ev.new_value) });
      case "notes":
        return t("{who} updated the internal notes", { who });
      default:
        return `${who}: ${ev.action}`;
    }
  };
  const dot = (ev: TicketEvent) =>
    ev.action === "status" ? STATUS_COLOR[ev.new_value ?? ""] ?? "var(--brand)"
      : ev.action === "payment_reference" ? "var(--st-paid)"
        : ev.action === "price" ? "var(--accent)"
          : ev.action === "notes" ? "var(--st-cancelled)" : "var(--brand)";

  return (
    <section className="tk-history" aria-label={t("History")}>
      <h3>{t("History")}</h3>
      {events === null ? <div className="muted small">{t("Loading…")}</div> : events.length === 0 ? (
        <div className="muted small">{t("No changes yet.")}</div>
      ) : (
        <ol className="timeline">
          {[...events].reverse().map((ev) => (
            <li key={ev.id} style={{ ["--dot" as string]: dot(ev) }}>
              <span className="tl-rail" aria-hidden="true"><span className="tl-dot" /></span>
              <span className="tl-body">
                <span className="tl-text">{describe(ev)}</span>
                <span className="tl-time">{dateTime(ev.created_at)}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
