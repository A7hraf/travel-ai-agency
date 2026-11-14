import { FormEvent, useEffect, useId, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { get, patch } from "../api";
import { useAuth } from "../auth";
import { Binoculars, ChatsCircle, Check, CheckCircle, MagnifyingGlass, WarningCircle } from "../components/Icon";
import { Money, moneyText } from "../components/Money";
import { ConfirmRequest, ConfirmSheet, PushPanel } from "../components/staff/Sheet";
import { useStaff } from "../components/staff/StaffContext";
import { ErrorBox, Field, Loading } from "../components/ui";
import ExportCsv from "../components/ExportCsv";
import { pollWatcher } from "../errorReporter";
import { trServer, useI18n } from "../lang";
import type { Service, Ticket, TicketEvent, TicketStatus, User } from "../types";
import MemberBadge from "../components/members/MemberBadge";
import BookingPanel from "../components/requests/BookingPanel";
import QuotePanel from "../components/requests/QuotePanel";
import RequestCard from "../components/requests/RequestCard";
import {
  customerLabel, dateTime, NEEDS_PAYMENT_REFERENCE, NEXT_TICKET_STATUSES, shortDate, TICKET_STATUS_LABELS,
  todayIso, travelersText, usePolling,
} from "../util";

/** An unpaid booking gives its seats back after the hold time; marking it paid takes them again. */
const seatsReleased = (tk: Ticket) => tk.seats_released;

type Filter = "us" | "client" | "confirmed" | "all";
// Requests waiting for the team, and requests waiting for the client.
const FOR_US = ["new", "changes", "chosen", "in_progress", "paid"];
const FOR_CLIENT = ["quoted", "final", "pending_payment"];
const OPEN = ["pending_payment", "in_progress"];
const QUOTING = ["new", "quoted", "changes", "chosen", "rejected"];
const FILTERS: { value: Filter; label: string; match: (s: string) => boolean }[] = [
  { value: "us", label: "Waiting for us", match: (s) => FOR_US.includes(s) },
  { value: "client", label: "Waiting for the client", match: (s) => FOR_CLIENT.includes(s) },
  { value: "confirmed", label: "Confirmed", match: (s) => s === "confirmed" },
  { value: "all", label: "All", match: () => true },
];

/** Status colours of the design (always shown with a text label). */
const STATUS_COLOR: Record<string, string> = {
  new: "var(--st-progress)",
  quoted: "var(--st-paid)",
  changes: "var(--st-waiting)",
  chosen: "var(--st-progress)",
  final: "var(--st-paid)",
  rejected: "var(--st-cancelled)",
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
  (tk.status === "new" || tk.status === "pending_payment") && !seen.has(tk.id) && Date.now() - new Date(tk.created_at).getTime() < 24 * 3600 * 1000;

export default function Tickets() {
  const { t, lang } = useI18n();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>("us");
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState("");
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [seen, setSeen] = useState(readSeen);
  const openId = params.get("open");
  const { user, can } = useAuth();
  const [listError, setListError] = useState<string | null>(null);
  const listPoll = useRef(pollWatcher("Tickets list"));

  const load = () => {
    const q = new URLSearchParams({ limit: "1000", sort: "urgency" });
    if (mine) q.set("mine", "true");
    if (search.trim()) q.set("q", search.trim());
    get<Ticket[]>(`/api/tickets?${q}`, { quiet: true })
      .then((list) => { setTickets(list); setListError(null); listPoll.current.ok(); })
      .catch((e) => { setListError((e as Error).message); listPoll.current.fail(e); });
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
        <div className="bt-title-row">
          <h1 className="screen-title">{t("Requests")}</h1>
          {can("reports.view") && <ExportCsv className="btn btn-sm btn-ghost" />}
        </div>
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

      {shown === null && listError ? (
        <ErrorBox error={listError} onRetry={load} />
      ) : shown === null ? (
        <><Loading height={0} /><div className="tk-grid" style={{ marginTop: 14 }}>{[0, 1, 2].map((i) => <div key={i} className="skeleton tk-skel" />)}</div></>
      ) : shown.length === 0 ? (
        <div className="empty">
          <Binoculars className="empty-icon" aria-hidden="true" />
          {tickets && tickets.length === 0 && !mine && !search.trim() ? (
            t("No requests yet. They appear here when the AI sends a request card or books a package.")
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
            <Link key={tk.id} to={`/app/tickets?open=${tk.id}`} className={`tk-card ${isNew(tk, seen) ? "new" : ""}`}
              // A grid item is as wide as its longest line by default: a long package title (e.g. English · Arabic)
              // pushed the card past the phone screen instead of being cut with "…".
              style={{ minWidth: 0 }}>
              <span className="tk-card-top">
                <bdi dir="ltr" className="tk-ref">{tk.reference}</bdi>
                <span className={`pill st-${tk.status}`}>{t(TICKET_STATUS_LABELS[tk.status])}</span>
              </span>
              {seatsReleased(tk) && (
                <span className="pill" style={{ alignSelf: "flex-start", background: "color-mix(in srgb, var(--st-cancelled) 18%, transparent)" }}>{t("Seats released")}</span>
              )}
              <span className="tk-who"><bdi>{tk.lead_traveler_name || customerLabel(tk.customer)}</bdi> · {tk.package_title}</span>
              {((tk.urgency?.score ?? 0) >= 20 || tk.customer.member_level) && (
                <span className="gx-rq-tags">
                  {(tk.urgency?.score ?? 0) >= 20 && <span className={`gx-rq-urgent ${(tk.urgency.score ?? 0) >= 45 ? "high" : ""}`}>{t((tk.urgency.score ?? 0) >= 45 ? "Urgent" : "Soon")} · {urgencyText(tk.urgency.reasons ?? [], t, user?.company?.member_levels, lang)}</span>}
                  <MemberBadge level={tk.customer.member_level} />
                </span>
              )}
              <span className="tk-card-foot">
                <span>{shortDate(tk.departure_date)} · {travelersText(tk.adults, tk.children)}</span>
                <span className="tk-total">{tk.total_price > 0 || !QUOTING.includes(tk.status) ? <Money value={tk.total_price} currency={tk.currency} /> : t("Quotation")}</span>
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
// A service request goes through the quotation first.
const QUOTE_STEPS: TicketStatus[] = ["new", "quoted", "final", "pending_payment", "paid", "confirmed"];
const QUOTE_STAGE: Record<string, number> = { new: 0, quoted: 1, changes: 1, chosen: 1, final: 2, pending_payment: 3, in_progress: 3, paid: 4, confirmed: 5 };

/** "trip in 2 days · VIP member" in the staff's language. */
function urgencyText(reasons: string[], t: (k: string, v?: Record<string, string | number>) => string,
  levels?: Record<string, { name_en: string; name_ar: string }> | null, lang?: string): string {
  return reasons.map((r) => {
    let m = /^trip in (\d+) days?$/.exec(r);
    if (m) return t("trip in {n} days", { n: m[1] });
    m = /^waiting (\d+) (days?|hours?)$/.exec(r);
    if (m) return t(m[2].startsWith("day") ? "waiting {n} days" : "waiting {n} hours", { n: m[1] });
    m = /^(.+) member$/.exec(r);
    if (m) {
      const l = Object.values(levels ?? {}).find((x) => x.name_en === m![1]);
      return t("{level} member", { level: l && lang === "ar" ? l.name_ar : m[1] });
    }
    return t(r);
  }).join(" · ");
}

/** Button text for a move to a status. */
function actionLabel(from: string, to: string): string {
  if (to === "in_progress") return "Start working on it";
  if (to === "paid") return "Mark as paid";
  if (to === "confirmed") return "Confirm the trip";
  if (to === "cancelled") return "Cancel request";
  if (to === "new") return "Reopen request";
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
  const [services, setServices] = useState<Service[]>([]);

  const [eventsError, setEventsError] = useState<string | null>(null);
  const [teamError, setTeamError] = useState<string | null>(null);
  const loadEvents = () => get<TicketEvent[]>(`/api/tickets/${id}/events`)
    .then((x) => { setEvents(x); setEventsError(null); }).catch((e) => setEventsError((e as Error).message));
  const loadTeam = () => get<User[]>("/api/team").then((x) => { setTeam(x); setTeamError(null); })
    .catch((e) => setTeamError((e as Error).message));

  useEffect(() => {
    get<Ticket>(`/api/tickets/${id}`).then((tk) => {
      setTicket(tk);
      setForm(formFrom(tk));
    }).catch((e) => setError(e.message));
    loadTeam();
    loadEvents();
    get<Service[]>("/api/services").then(setServices).catch(() => {});
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
  // After the departure date a booking can only be cancelled.
  const departed = !!ticket?.departure_date && ticket.departure_date < todayIso();
  const nexts = ticket
    ? (NEXT_TICKET_STATUSES[ticket.status] ?? []).filter((s) => (!["cancelled", "rejected"].includes(ticket.status) || isAdmin)
      // A request with a service is confirmed by sending its documents (below), not by this button.
      && !(s === "confirmed" && !!ticket.service)
      // A cancelled package booking reopens to "waiting for payment", a cancelled service request to "new".
      && (ticket.status !== "cancelled" || (s === "new") === (!!ticket.service && ticket.service.key !== "packages"))
      && !(departed && NEEDS_PAYMENT_REFERENCE.includes(s)))
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
      const request = !!ticket?.service && ticket.service.key !== "packages";
      setConfirmReq({
        title: request ? t("Cancel this request?") : t("Cancel this booking?"),
        text: request ? t("The client is told in the chat. Only a company admin can reopen it.")
          : t("The seats go back to the package and the payment reference is cleared. Only a company admin can reopen it."),
        okLabel: request ? t("Cancel request") : t("Cancel booking"),
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

  const quoting = !!ticket?.service && ticket.service.key !== "packages";
  const steps = quoting ? QUOTE_STEPS : STEPS;
  const idx = ticket ? (quoting ? QUOTE_STAGE[ticket.status] ?? -1 : STEPS.indexOf(ticket.status)) : -1;
  const cancelled = ticket?.status === "cancelled" || ticket?.status === "rejected";
  const statusColor = ticket ? STATUS_COLOR[ticket.status] : undefined;
  // The payment reference matters once the client approved the quotation.
  const showRefInput = !!ticket && canManage && !cancelled && !(quoting && [...QUOTING, "final"].includes(ticket.status));
  const agent = agentName || t("AI agent");

  return (
    <PushPanel backLabel={t("Requests")} onClose={requestClose} labelledBy={titleId}>
      {!ticket ? (error ? <ErrorBox error={error} /> : <div className="tk-detail"><Loading height={0} />{[0, 1, 2].map((i) => <div key={i} className="skeleton tk-skel" />)}</div>) : (
        <div className="tk-detail">
          <h2 className="tk-detail-ref" id={titleId}><bdi dir="ltr">{ticket.reference}</bdi></h2>
          <div className="tk-detail-who">
            <bdi>{ticket.lead_traveler_name || customerLabel(ticket.customer)}</bdi>
            {ticket.contact_phone && <> · <bdi dir="ltr">{ticket.contact_phone}</bdi></>}
          </div>

          <ol className={`stepper ${quoting ? "gx-steps-6" : ""} ${cancelled ? "cancelled" : ""}`} aria-label={t("Status")}
            style={{ ["--step-color" as string]: statusColor, ["--progress" as string]: grown && idx > 0 ? `${(idx / (steps.length - 1)) * (100 - 100 / steps.length)}%` : "0%" }}>
            {steps.map((s, i) => {
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
          {cancelled && <div className="tk-cancelled">{ticket.status === "rejected" ? t("The client rejected the quotation.")
            : quoting ? t("Cancelled.") : t("Cancelled. The seats went back to the package.")}</div>}
          {ticket.urgency?.score ? <div className="gx-rq-urgency-line"><span className={`gx-rq-urgent ${(ticket.urgency.score ?? 0) >= 45 ? "high" : ""}`}>{t("Priority {n}/100", { n: ticket.urgency.score })}</span> {urgencyText(ticket.urgency.reasons ?? [], t, user?.company?.member_levels, lang)}</div> : null}
          <RequestCard ticket={ticket} services={services} />
          <QuotePanel ticket={ticket} onChange={(tk) => after(tk, true)} />
          <BookingPanel ticket={ticket} onChange={(tk) => after(tk, true)} />
          {seatsReleased(ticket) && (
            <div className="tk-cancelled" role="note">
              {t("Not paid in time: the seats went back on sale. Marking it paid takes them again if seats are still left on this date.")}
            </div>
          )}
          {departed && !cancelled && (
            <div className="tk-cancelled" role="note">{t("The departure date has passed: this booking can only be cancelled.")}</div>
          )}

          <dl className="tk-grid-details">
            <dt>{quoting ? t("Request") : t("Package")}</dt><dd dir="auto">{ticket.package_title}</dd>
            <dt>{t("Departure")}</dt><dd>{shortDate(ticket.departure_date)}{ticket.return_date ? ` – ${shortDate(ticket.return_date)}` : ""}</dd>
            <dt>{t("Travellers")}</dt><dd>{travelersText(ticket.adults, ticket.children)}</dd>
            {(ticket.total_price > 0 || !quoting) && <><dt>{t("Total")}</dt><dd className="tk-strong"><Money value={ticket.total_price} currency={ticket.currency} /></dd></>}
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
          <ErrorBox error={teamError} onRetry={loadTeam} />
          {eventsError && events === null ? <ErrorBox error={eventsError} onRetry={loadEvents} />
            : <TicketHistory events={events} currency={ticket.currency} lang={lang} />}
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
    const who = ev.actor === "AI" ? t("AI agent") : ev.actor === "System" ? t("System")
      : ev.actor === "Client" ? t("The client") : ev.actor === "Client (trips page)" ? t("The client (trips page)") : ev.actor;
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
      case "seats_released":
        return trServer(ev.new_value) || t("Seats released");
      case "option_added":
        return t("{who} added the choice {new}", { who, new: ev.new_value ?? "" });
      case "option_changed":
        return t("{who} changed the choice {new}", { who, new: ev.new_value ?? "" });
      case "option_removed":
        return t("{who} removed the choice {new}", { who, new: ev.new_value ?? "" });
      case "ai_drafted":
        return t("{who} let the AI draft choices ({new})", { who, new: ev.new_value ?? "" });
      case "chosen":
        return t("{who} picked: {new}", { who, new: ev.new_value ?? "" });
      case "changes":
        return t("{who} asked for changes: {new}", { who, new: ev.new_value ?? "" });
      case "final_note":
        return t("{who} added to the final quotation: {new}", { who, new: ev.new_value ?? "" });
      case "moved":
        return t("Moved from the old requests");
      case "payment_proof":
        return t("{who} sent a payment proof: {new}", { who, new: ev.new_value ?? "" });
      case "client_file":
        return t("{who} sent a file: {new}", { who, new: ev.new_value ?? "" });
      case "file_added":
        return t("{who} added the file {new}", { who, new: ev.new_value ?? "" });
      case "file_removed":
        return t("{who} removed the file {new}", { who, new: ev.new_value ?? "" });
      case "step_done":
        return t("{who} ticked: {new}", { who, new: ev.new_value ?? "" });
      case "step_undone":
        return t("{who} unticked: {new}", { who, new: ev.new_value ?? "" });
      case "saved_to_library":
        return t("{who} saved {new} to the library", { who, new: ev.new_value ?? "" });
      case "documents_sent":
        return t("{who} sent the documents: {new}", { who, new: ev.new_value ?? "" });
      default:
        return `${who}: ${ev.action}`;
    }
  };
  const dot = (ev: TicketEvent) =>
    ev.action === "status" ? STATUS_COLOR[ev.new_value ?? ""] ?? "var(--brand)"
      : ev.action === "payment_reference" ? "var(--st-paid)"
        : ev.action === "price" ? "var(--accent)"
          : ev.action === "notes" || ev.action === "seats_released" ? "var(--st-cancelled)" : "var(--brand)";

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
