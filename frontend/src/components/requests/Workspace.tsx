import { FormEvent, ReactNode, useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { get, patch } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { Service, Ticket, TicketEvent, User } from "../../types";
import { customerLabel, dateTime, NEXT_TICKET_STATUSES, shortDate, TICKET_STATUS_LABELS, todayIso, travelersText } from "../../util";
import {
  ArrowRight, CalendarPlus, ChatsCircle, Check, CheckCircle, FilePdf, Hourglass, Lightning, Prohibit, WarningCircle,
} from "../Icon";
import MemberBadge from "../members/MemberBadge";
import { ConfirmRequest, ConfirmSheet, PushPanel } from "../staff/Sheet";
import { useStaff } from "../staff/StaffContext";
import { ErrorBox, Loading } from "../ui";
import BookingPanel from "./BookingPanel";
import ClientDocsPanel from "./ClientDocsPanel";
import TicketHistory from "./History";
import MoneyBox from "./MoneyBox";
import PaymentsPanel from "./PaymentsPanel";
import PlanPanel from "./PlanPanel";
import QuotePanel from "./QuotePanel";
import RequestDetails from "./RequestDetails";

type Tab = "request" | "quotation" | "plan" | "documents" | "payments" | "booking" | "history";

const LIFE = ["Request", "Quotation", "Client approval", "Payment", "Booking", "Confirmed", "Trip"];
const LIFE_INDEX: Record<string, number> = {
  new: 1, changes: 1, chosen: 1, quoted: 2, final: 2, pending_payment: 3, in_progress: 3, paid: 4, confirmed: 5,
};
const DEFAULT_TAB: Record<string, Tab> = {
  new: "quotation", changes: "quotation", chosen: "quotation", quoted: "quotation", final: "quotation",
  pending_payment: "payments", in_progress: "payments", paid: "booking", confirmed: "booking", cancelled: "history", rejected: "history",
};

/** "Waiting 3 hours" / "2 days" since a time. */
function since(iso: string | null, t: (k: string, v?: Record<string, string | number>) => string): string {
  if (!iso) return "";
  const h = Math.max(0, (Date.now() - new Date(iso).getTime()) / 3600000);
  if (h < 1) return t("less than an hour");
  if (h < 48) return t("{n} hours", { n: Math.floor(h) });
  return t("{n} days", { n: Math.floor(h / 24) });
}

/** What the team should do now on this request, in one sentence, and where to do it. */
function nextStep(tk: Ticket, t: (k: string, v?: Record<string, string | number>) => string, money: (v: number | null) => string):
  { tone: "act" | "wait" | "done" | "closed"; text: string; tab?: Tab; cta?: string } {
  const m = tk.money;
  const isPackage = !tk.service || tk.service.key === "packages";
  switch (tk.status) {
    case "new":
      return { tone: "act", text: tk.service?.pricing === "fixed" ? t("Fixed price: check the request and send the final quotation.")
        : t("Prepare up to 3 choices per part (with your cost and the client price) and send them."), tab: "quotation", cta: t("Prepare choices") };
    case "changes":
      return { tone: "act", text: t("The client asked for changes. Update the choices and send them again."), tab: "quotation", cta: t("Update choices") };
    case "chosen":
      return { tone: "act", text: t("The client chose. Check the total and profit, then send the final quotation."), tab: "quotation", cta: t("Send the final quotation") };
    case "quoted":
      return { tone: "wait", text: t("Choices sent. Waiting for the client to choose ({time}).", { time: since(tk.updated_at, t) }), tab: "quotation", cta: t("See the choices") };
    case "final":
      return { tone: "wait", text: t("Final quotation sent. Waiting for the client to approve ({time}).", { time: since(tk.updated_at, t) }) };
    case "pending_payment":
      if (m.pending_proofs) return { tone: "act", text: t("The client sent a payment receipt: check it and approve the amount."), tab: "payments", cta: t("Check the receipt") };
      return { tone: "wait", text: isPackage ? t("Booked. Waiting for the payment of {amount}.", { amount: money(m.balance ?? m.total) })
        : t("Approved. Waiting for the payment of {amount}; the client has your payment details.", { amount: money(m.balance ?? m.total) }), tab: "payments", cta: t("Record a payment") };
    case "in_progress":
      return m.pending_proofs
        ? { tone: "act", text: t("The client sent a payment receipt: check it and approve the amount."), tab: "payments", cta: t("Check the receipt") }
        : { tone: "wait", text: t("Partly paid: {paid} of {total}. Waiting for the balance.", { paid: money(m.paid), total: money(m.total) }), tab: "payments", cta: t("Payments") };
    case "paid": {
      const left = tk.booking_steps.filter((s) => !s.done && s.key !== "documents").length;
      return { tone: "act", text: left ? t("Paid. Book everything ({n} steps left), then send the travel documents.", { n: left })
        : t("Everything is booked: send the travel documents to confirm."), tab: "booking", cta: t("Open the booking") };
    }
    case "confirmed": {
      const done = !!tk.return_date && tk.return_date < todayIso();
      return { tone: "done", text: done ? t("Trip done.") : tk.departure_date ? t("Confirmed. The trip starts {date}.", { date: shortDate(tk.departure_date) }) : t("Confirmed.") };
    }
    case "rejected":
      return { tone: "closed", text: t("The client rejected the quotation.") + (tk.client_note ? ` “${tk.client_note}”` : "") };
    default:
      return { tone: "closed", text: t("Cancelled.") };
  }
}

export default function Workspace({ id, onClose, onSaved }: { id: number; onClose: () => void; onSaved: () => void }) {
  const { user, can } = useAuth();
  const { t, lang } = useI18n();
  const { refreshCounts } = useStaff();
  const titleId = useId();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [team, setTeam] = useState<User[]>([]);
  const [events, setEvents] = useState<TicketEvent[] | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [tab, setTab] = useState<Tab | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState("");
  const [notesSaved, setNotesSaved] = useState(false);
  const [confirmReq, setConfirmReq] = useState<ConfirmRequest | null>(null);

  const loadEvents = () => get<TicketEvent[]>(`/api/tickets/${id}/events`).then(setEvents).catch(() => {});
  useEffect(() => {
    setTicket(null); setTab(null);
    get<Ticket>(`/api/tickets/${id}`).then((tk) => { setTicket(tk); setNotes(tk.internal_notes); }).catch((e) => setError((e as Error).message));
    get<User[]>("/api/team").then(setTeam).catch(() => {});
    get<Service[]>("/api/services").then(setServices).catch(() => {});
    loadEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const after = (tk: Ticket) => { setTicket(tk); onSaved(); refreshCounts(); loadEvents(); };
  const money = (v: number | null) => (v == null ? "—" : new Intl.NumberFormat(lang === "ar" ? "ar-OM" : "en-GB", { maximumFractionDigits: 3 }).format(v) + ` ${ticket?.currency ?? ""}`);
  const manage = can("tickets.manage");
  const canAssign = can("tickets.assign");
  const isAdmin = user?.role === "company_admin";

  if (!ticket) {
    return (
      <PushPanel wide backLabel={t("Requests")} onClose={onClose} labelledBy={titleId}>
        {error ? <ErrorBox error={error} /> : <div className="rw"><Loading height={0} /><div className="skeleton tk-skel" /><div className="skeleton tk-skel" /></div>}
      </PushPanel>
    );
  }

  const isPackage = !ticket.service || ticket.service.key === "packages";
  const life = LIFE_INDEX[ticket.status] ?? -1;
  const tripDone = ticket.status === "confirmed" && !!ticket.return_date && ticket.return_date < todayIso();
  const closed = ticket.stage === "closed";
  const step = nextStep(ticket, t, money);
  const docsMissing = ticket.client_documents.missing;
  const tabs: { key: Tab; label: string; badge?: string | number; hide?: boolean }[] = [
    { key: "request", label: t("Request") },
    { key: "quotation", label: t("Quotation"), hide: isPackage },
    { key: "plan", label: t("Trip plan"), hide: isPackage || ticket.service?.pricing === "fixed" },
    { key: "documents", label: t("Client documents"), badge: docsMissing || ticket.client_documents.unsorted.length || undefined },
    { key: "payments", label: t("Payments"), badge: ticket.money.pending_proofs || undefined },
    { key: "booking", label: t("Booking") },
    { key: "history", label: t("History") },
  ];
  const current = tab ?? DEFAULT_TAB[ticket.status] ?? "request";
  const active = tabs.find((x) => x.key === current && !x.hide) ? current : "request";

  // Cancel, reopen (admins), and confirming an old booking without a service; payments and documents move the rest.
  const actions = (NEXT_TICKET_STATUSES[ticket.status] ?? []).filter((s) =>
    (s === "cancelled" || ((s === "new" || s === "pending_payment") && closed && isAdmin && ((s === "new") === !isPackage))
      || (s === "confirmed" && !ticket.service)));
  const move = async (to: string) => {
    setBusy(true); setError(null);
    try { after(await patch<Ticket>(`/api/tickets/${id}`, { status: to })); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const onAction = (to: string) => {
    if (to !== "cancelled") return move(to);
    setConfirmReq({
      title: isPackage ? t("Cancel this booking?") : t("Cancel this request?"),
      text: isPackage ? t("The seats go back to the package and the payment reference is cleared. Only a company admin can reopen it.")
        : t("The client is told in the chat. Only a company admin can reopen it."),
      okLabel: isPackage ? t("Cancel booking") : t("Cancel request"),
      onConfirm: () => move(to),
    });
  };
  const assign = async (value: string) => {
    setBusy(true); setError(null);
    try { after(await patch<Ticket>(`/api/tickets/${id}`, value ? { assigned_to_id: Number(value) } : { unassign: true })); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const saveNotes = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setNotesSaved(false);
    try { after(await patch<Ticket>(`/api/tickets/${id}`, { internal_notes: notes })); setNotesSaved(true); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const currentAssignee = ticket.assigned_to ? String(ticket.assigned_to.id) : "";
  const mineOrFree = !currentAssignee || currentAssignee === String(user?.id);
  const assignOptions = canAssign ? team : team.filter((u) => String(u.id) === currentAssignee || (mineOrFree && u.id === user?.id));
  const urgent = (ticket.urgency?.score ?? 0) >= 45;

  const panels: Record<Tab, ReactNode> = {
    request: <RequestDetails key={ticket.updated_at} ticket={ticket} services={services} onChange={after} />,
    quotation: <QuotePanel key={ticket.updated_at} ticket={ticket} onChange={after} />,
    plan: <PlanPanel key={ticket.updated_at} ticket={ticket} onChange={after} />,
    documents: <ClientDocsPanel ticket={ticket} onChange={after} />,
    payments: <PaymentsPanel ticket={ticket} onChange={after} />,
    booking: <BookingPanel ticket={ticket} onChange={after} />,
    history: <TicketHistory events={events} currency={ticket.currency} lang={lang} />,
  };

  return (
    <PushPanel wide backLabel={t("Requests")} onClose={onClose} labelledBy={titleId}>
      <div className="rw">
        <header className="rw-head">
          <div className="rw-title">
            <h2 id={titleId}><bdi dir="ltr">{ticket.reference}</bdi></h2>
            <span className={`pill st-${ticket.status}`}>{t(TICKET_STATUS_LABELS[ticket.status])}</span>
            {urgent && <span className="gx-rq-urgent high"><Lightning weight="fill" /> {t("Urgent")}</span>}
          </div>
          <div className="rw-who">
            <strong><bdi>{ticket.lead_traveler_name || customerLabel(ticket.customer)}</bdi></strong>
            <MemberBadge level={ticket.customer.member_level} />
            {ticket.contact_phone && <bdi dir="ltr" className="muted">{ticket.contact_phone}</bdi>}
            <span className="muted">· {lang === "ar" ? ticket.service?.name_ar ?? ticket.package_title : ticket.service?.name_en ?? ticket.package_title}
              {ticket.destination && <> · <bdi>{ticket.destination}</bdi></>}
              {ticket.departure_date && <> · {shortDate(ticket.departure_date)}{ticket.return_date && ` – ${shortDate(ticket.return_date)}`}</>}
              {" · "}{travelersText(ticket.adults, ticket.children)}</span>
          </div>
        </header>

        <ol className={`rw-life ${closed ? "closed" : ""}`} aria-label={t("Progress")}>
          {LIFE.map((label, i) => {
            const skipped = isPackage && (i === 1 || i === 2);
            const state = closed ? "todo" : skipped ? "skip" : (i < life || tripDone) ? "done" : i === life ? "current" : "todo";
            return (
              <li key={label} className={state} aria-current={state === "current" ? "step" : undefined}>
                <span className="rw-dot">{state === "done" && <Check weight="bold" />}</span>
                <span className="rw-life-label">{t(label)}</span>
                {skipped && <span className="rw-life-sub">{t("package price")}</span>}
              </li>
            );
          })}
        </ol>

        <div className={`rw-next ${step.tone}`} role="status">
          {step.tone === "act" ? <ArrowRight className="flip" weight="bold" /> : step.tone === "wait" ? <Hourglass weight="fill" />
            : step.tone === "done" ? <CheckCircle weight="fill" /> : <Prohibit weight="fill" />}
          <span className="rw-next-text">{step.text}</span>
          {step.tab && step.cta && active !== step.tab && <button type="button" className="btn btn-sm btn-primary" onClick={() => setTab(step.tab!)}>{step.cta}</button>}
        </div>
        {docsMissing > 0 && !closed && ticket.status !== "confirmed" && (
          <button type="button" className="rw-alert" onClick={() => setTab("documents")}>
            <WarningCircle weight="fill" /> {t("Documents still missing from the client: {n}", { n: docsMissing })}
          </button>
        )}
        {ticket.seats_released && <div className="rw-alert static"><WarningCircle weight="fill" /> {t("Not paid in time: the seats went back on sale. Marking it paid takes them again if seats are still left on this date.")}</div>}

        <div className="rw-grid">
          <main className="rw-main">
            <div className="rw-tabs" role="tablist">
              {tabs.filter((x) => !x.hide).map((x) => (
                <button key={x.key} type="button" role="tab" aria-selected={active === x.key} className={active === x.key ? "on" : ""} onClick={() => setTab(x.key)}>
                  {x.label}{x.badge ? <span className="rw-badge">{x.badge}</span> : null}
                </button>
              ))}
            </div>
            <div className="rw-tab-body" role="tabpanel">{panels[active]}</div>
          </main>

          <aside className="rw-side">
            <MoneyBox ticket={ticket} onChange={after} />
            <section className="rw-card">
              <h3>{t("Team")}</h3>
              <label className="rw-lbl"><span>{t("Assigned to")}</span>
                <select value={currentAssignee} disabled={!manage || busy || !(canAssign || mineOrFree)} onChange={(e) => assign(e.target.value)}>
                  {(canAssign || mineOrFree) && <option value="">— {t("nobody")} —</option>}
                  {assignOptions.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </label>
              <form onSubmit={saveNotes} className="rw-notes">
                <label className="rw-lbl"><span>{t("Internal notes")}</span>
                  <textarea rows={3} value={notes} disabled={!manage || busy} dir="auto" placeholder={t("Only your team sees this")}
                    onChange={(e) => { setNotes(e.target.value); setNotesSaved(false); }} /></label>
                {manage && notes !== ticket.internal_notes && <button className="btn btn-sm btn-primary">{t("Save the notes")}</button>}
                {notesSaved && notes === ticket.internal_notes && <span className="muted small">{t("Saved.")}</span>}
              </form>
            </section>
            <section className="rw-card rw-links">
              {ticket.conversation_id && can("conversations.view") && (
                <Link className="btn btn-soft btn-sm" to={`/app/conversations/${ticket.conversation_id}`}><ChatsCircle />{t("Open the conversation")}</Link>
              )}
              {user?.company?.addons?.includes("quotes") && ticket.options.some((o) => o.price != null) && (
                <a className="btn btn-soft btn-sm" href={`/app/tickets/${ticket.id}/quotation?kind=${ticket.options.some((o) => o.chosen) ? "final" : "draft"}`} target="_blank" rel="noreferrer"><FilePdf />{t("Quotation PDF")}</a>
              )}
              {user?.company?.addons?.includes("calendar") && manage && (
                <Link className="btn btn-soft btn-sm" to={`/app/calendar?new=1&ticket=${ticket.id}&title=${encodeURIComponent(ticket.reference)}`}><CalendarPlus />{t("Add to the calendar")}</Link>
              )}
              <Link className="btn btn-ghost btn-sm" to={`/app/customers/${ticket.customer.id}`}>{t("Client profile")}</Link>
              <p className="muted small">{ticket.created_by === "ai" ? t("Made by the AI in the chat") : t("Made by the team")} · {dateTime(ticket.created_at)}</p>
            </section>
            {manage && actions.length > 0 && (
              <section className="rw-card rw-actions">
                {actions.map((s) => (
                  <button key={s} type="button" disabled={busy} onClick={() => onAction(s)} className={`btn btn-sm ${s === "cancelled" ? "btn-ghost btn-danger-text" : "btn-soft"}`}>
                    {s === "cancelled" ? (isPackage ? t("Cancel booking") : t("Cancel request")) : s === "confirmed" ? t("Confirm the trip") : t("Reopen request")}
                  </button>
                ))}
              </section>
            )}
            <ErrorBox error={error} />
          </aside>
        </div>
      </div>
      {confirmReq && <ConfirmSheet req={confirmReq} onClose={() => setConfirmReq(null)} />}
    </PushPanel>
  );
}
