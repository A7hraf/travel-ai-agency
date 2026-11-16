import { FormEvent, ReactNode, useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { get, patch, post } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { Service, Ticket, TicketEvent, User } from "../../types";
import { customerLabel, dateTime, NEXT_TICKET_STATUSES, shortDate, TICKET_STATUS_LABELS, travelersText } from "../../util";
import {
  ArrowRight, CalendarPlus, ChatsCircle, Check, CheckCircle, FilePdf, Hourglass, Lightning, Prohibit, WarningCircle,
} from "../Icon";
import MemberBadge from "../members/MemberBadge";
import { PushPanel, Sheet } from "../staff/Sheet";
import { useStaff } from "../staff/StaffContext";
import { ErrorBox, Loading } from "../ui";
import BookingPanel from "./BookingPanel";
import ClientDocsPanel from "./ClientDocsPanel";
import TicketHistory from "./History";
import MoneyBox from "./MoneyBox";
import PaymentsPanel from "./PaymentsPanel";
import PlanPanel from "./PlanPanel";
import ProcessPanel from "./ProcessPanel";
import QuotePanel from "./QuotePanel";
import RequestDetails from "./RequestDetails";

type Tab = "request" | "process" | "quotation" | "plan" | "documents" | "payments" | "booking" | "history";

// The tab where the current step's work is done.
const STEP_TAB: Record<string, Tab> = {
  intake: "request", review: "request", quote: "quotation", documents: "documents", payment: "payments", schedule: "process",
  booking: "booking", delivery: "booking", trip: "process", feedback: "process", task: "process",
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
function nextStep(tk: Ticket, t: (k: string, v?: Record<string, string | number>) => string, money: (v: number | null) => string, lang: string):
  { tone: "act" | "wait" | "done" | "closed"; text: string; tab?: Tab; cta?: string } {
  const m = tk.money;
  const step = tk.current_step;
  const name = step ? (lang === "ar" ? step.label_ar : step.label_en) : "";
  const due = tk.process?.due_now ?? m.balance ?? m.total;
  if (tk.status === "rejected") return { tone: "closed", text: t("The client rejected the quotation.") + (tk.client_note ? ` “${tk.client_note}”` : "") };
  if (tk.stage === "closed") return { tone: "closed", text: t("Cancelled.") };
  if (!step) return { tone: "done", text: t("Every step is done.") };
  switch (step.type) {
    case "intake":
      return { tone: "act", text: t("Some answers are missing: complete the request details (or ask the client)."), tab: "request", cta: t("Open the details") };
    case "review":
      return { tone: "act", text: t("Check the request. Ask the client for anything missing, then continue."), tab: "process", cta: t("Review") };
    case "quote":
      switch (tk.status) {
        case "changes": return { tone: "act", text: t("The client asked for changes. Update the choices and send them again."), tab: "quotation", cta: t("Update choices") };
        case "chosen": return { tone: "act", text: t("The client chose. Check the total and profit, then send the final quotation."), tab: "quotation", cta: t("Send the final quotation") };
        case "quoted": return { tone: "wait", text: t("Choices sent. Waiting for the client to choose ({time}).", { time: since(tk.updated_at, t) }), tab: "quotation", cta: t("See the choices") };
        case "final": return { tone: "wait", text: t("Final quotation sent. Waiting for the client to approve ({time}).", { time: since(tk.updated_at, t) }) };
        default: return { tone: "act", text: tk.service?.pricing === "fixed" ? t("Fixed price: check the request and send the final quotation.")
          : t("Prepare up to 3 choices per part (with your cost and the client price) and send them."), tab: "quotation", cta: t("Prepare choices") };
      }
    case "documents":
      return { tone: "wait", text: t("Waiting for the client's documents ({n} missing). When you have everything, mark them complete.", { n: tk.client_documents.missing }), tab: "documents", cta: t("Client documents") };
    case "payment":
      if (!m.total) return { tone: "act", text: t("Set the client price: the client is then asked to pay."), tab: "request", cta: t("Open the details") };
      if (m.pending_proofs) return { tone: "act", text: t("The client sent a payment receipt: check it and approve the amount."), tab: "payments", cta: t("Check the receipt") };
      return { tone: "wait", text: t("{step}: waiting for {amount}; the client has your payment details.", { step: name, amount: money(due) }), tab: "payments", cta: t("Record a payment") };
    case "schedule":
      return { tone: "act", text: t("Book the appointment at a time that suits the client, then record their confirmation."), tab: "process", cta: t("Book the appointment") };
    case "booking": {
      const left = tk.booking_steps.filter((s) => !s.done && s.key !== "documents").length;
      return { tone: "act", text: left ? t("Book everything ({n} steps left).", { n: left }) : t("Mark the booking done."), tab: "booking", cta: t("Open the booking") };
    }
    case "delivery":
      return { tone: "act", text: t("Send the travel documents to the client."), tab: "booking", cta: t("Open the booking") };
    case "trip":
      return { tone: "done", text: tk.departure_date ? t("Confirmed. The trip starts {date}.", { date: shortDate(tk.departure_date) }) : t("Confirmed.") };
    case "feedback":
      return { tone: "wait", text: t("Trip done. Waiting for the client's feedback."), tab: "process", cta: t("Steps") };
    default:
      return { tone: "act", text: name, tab: "process", cta: t("Mark it done") };
  }
}

function CloseSheet({ onClose, onDone, isPackage }: { onClose: () => void; onDone: (by: "client" | "team", reason: string) => Promise<void>; isPackage: boolean }) {
  const { t } = useI18n();
  const [by, setBy] = useState<"client" | "team">("client");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try { await onDone(by, reason.trim()); onClose(); } finally { setBusy(false); }
  };
  return (
    <Sheet label={isPackage ? t("Cancel this booking?") : t("Cancel this request?")} onClose={onClose}>
      <form className="gx-close" onSubmit={submit}>
        <h3>{isPackage ? t("Cancel this booking?") : t("Cancel this request?")}</h3>
        <p className="muted small">{isPackage ? t("The seats go back to the package and the payment reference is cleared. Only a company admin can reopen it.")
          : t("The client is told in the chat. Only a company admin can reopen it.")}</p>
        <fieldset className="gx-close-by">
          <legend>{t("Who asked to cancel?")}</legend>
          <label><input type="radio" name="by" checked={by === "client"} onChange={() => setBy("client")} /> {t("The client")}</label>
          <label><input type="radio" name="by" checked={by === "team"} onChange={() => setBy("team")} /> {t("Our team")}</label>
        </fieldset>
        <label className="rw-lbl"><span>{t("Why?")}</span>
          <textarea rows={3} dir="auto" required minLength={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder={t("For example: dates changed, found a cheaper offer, no answer for two weeks")} /></label>
        <div className="gx-wf-save">
          <button className="btn btn-sm btn-danger" disabled={busy || reason.trim().length < 2}>{isPackage ? t("Cancel booking") : t("Cancel request")}</button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>{t("Keep it")}</button>
        </div>
      </form>
    </Sheet>
  );
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
  const [closing, setClosing] = useState(false);

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
  const closed = ticket.stage === "closed";
  const step = nextStep(ticket, t, money, lang);
  const flowSteps = ticket.process?.steps ?? [];
  const docsMissing = ticket.client_documents.missing;
  const tabs: { key: Tab; label: string; badge?: string | number; hide?: boolean }[] = [
    { key: "request", label: t("Request") },
    { key: "process", label: t("Steps"), hide: !ticket.process },
    { key: "quotation", label: t("Quotation"), hide: !flowSteps.some((s) => s.type === "quote") },
    { key: "plan", label: t("Trip plan"), hide: isPackage || !flowSteps.some((s) => s.type === "trip") },
    { key: "documents", label: t("Client documents"), badge: docsMissing || ticket.client_documents.unsorted.length || undefined },
    { key: "payments", label: t("Payments"), badge: ticket.money.pending_proofs || undefined },
    { key: "booking", label: t("Booking") },
    { key: "history", label: t("History") },
  ];
  const current = tab ?? (closed ? "process" : STEP_TAB[ticket.current_step?.type ?? ""] ?? "request");
  const active = tabs.find((x) => x.key === current && !x.hide) ? current : "request";

  // Cancel, reopen (admins), and confirming an old booking without a service; payments and documents move the rest.
  const actions = (NEXT_TICKET_STATUSES[ticket.status] ?? []).filter((s) =>
    (s === "cancelled" || ((s === "new" || s === "pending_payment") && closed && isAdmin && ((s === "new") === !isPackage))
      || (s === "confirmed" && !ticket.service)));
  const move = async (to: string) => {
    setBusy(true); setError(null);
    try { after(await patch<Ticket>(`/api/tickets/${id}`, { status: to })); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const onAction = (to: string) => (to === "cancelled" ? setClosing(true) : move(to));
  const close = async (by: "client" | "team", reason: string) => {
    setError(null);
    try { after(await post<Ticket>(`/api/tickets/${id}/close`, { by, reason })); } catch (e) { setError((e as Error).message); }
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
    process: <ProcessPanel key={ticket.updated_at} ticket={ticket} onChange={after} />,
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

        {flowSteps.length > 0 && (
          <ol className={`rw-life ${closed ? "closed" : ""}`} aria-label={t("Progress")}>
            {flowSteps.map((s) => {
              const state = closed && s.state === "active" ? "todo" : s.state === "done" ? "done" : s.state === "skipped" ? "skip" : s.state === "active" ? "current" : "todo";
              return (
                <li key={s.key} className={state} aria-current={state === "current" ? "step" : undefined}>
                  <button type="button" className="rw-life-btn" onClick={() => setTab("process")}>
                    <span className="rw-dot">{state === "done" && <Check weight="bold" />}</span>
                    <span className="rw-life-label"><bdi>{lang === "ar" ? s.label_ar : s.label_en}</bdi></span>
                    {state === "current" && s.started_at && <span className="rw-life-sub">{since(s.started_at, t)}</span>}
                  </button>
                </li>
              );
            })}
          </ol>
        )}

        <div className={`rw-next ${step.tone}`} role="status">
          {step.tone === "act" ? <ArrowRight className="flip" weight="bold" /> : step.tone === "wait" ? <Hourglass weight="fill" />
            : step.tone === "done" ? <CheckCircle weight="fill" /> : <Prohibit weight="fill" />}
          <span className="rw-next-text">{step.text}</span>
          {step.tab && step.cta && active !== step.tab && <button type="button" className="btn btn-sm btn-primary" onClick={() => setTab(step.tab!)}>{step.cta}</button>}
        </div>
        {docsMissing > 0 && !closed && !["confirmed", "completed"].includes(ticket.status) && !flowSteps.some((s) => s.type === "documents" && (s.state === "done" || s.state === "skipped" || s.state === "active")) && (
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
      {closing && <CloseSheet isPackage={isPackage} onClose={() => setClosing(false)} onDone={close} />}
    </PushPanel>
  );
}
