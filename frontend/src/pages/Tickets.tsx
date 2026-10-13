import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { get, patch } from "../api";
import { useAuth } from "../auth";
import { Badge, Empty, ErrorBox, Field, Modal, PageHeader, TICKET_TONES } from "../components/ui";
import { trServer, useI18n } from "../lang";
import type { Ticket, TicketEvent, TicketStatus, User } from "../types";
import { Money, moneyText } from "../components/Money";
import {
  customerLabel, dateTime, NEEDS_PAYMENT_REFERENCE, NEXT_TICKET_STATUSES, shortDate, TICKET_STATUS_LABELS,
  travelersText, usePolling,
} from "../util";

export default function Tickets() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState("");
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState("");
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const openId = params.get("open");
  const filtered = !!(status || mine || search.trim());

  const load = () => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    if (mine) q.set("mine", "true");
    if (search.trim()) q.set("q", search.trim());
    get<Ticket[]>(`/api/tickets?${q}`).then(setTickets).catch(() => {});
  };
  usePolling(load, 10000, [status, mine, search]);

  return (
    <div>
      <PageHeader title={t("Booking tickets")}
        subtitle={t("The AI creates a ticket when a customer confirms a booking. Your team takes the payment and confirms it.")} />
      <div className="toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("Status")}>
          <option value="">{t("All statuses")}</option>
          {Object.entries(TICKET_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
        </select>
        <input placeholder={t("Reference, name or phone")} aria-label={t("Reference, name or phone")} value={search}
          onChange={(e) => setSearch(e.target.value)} />
        <label className="check"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> {t("Assigned to me")}</label>
      </div>

      {tickets === null ? <div className="loading">{t("Loading…")}</div> : tickets.length === 0 ? (
        <Empty>{filtered ? t("No results for this filter.") : t("No tickets yet. They appear here when the AI closes a booking.")}</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table cards">
            <thead>
              <tr><th>{t("Reference")}</th><th>{t("Customer")}</th><th>{t("Package")}</th><th>{t("Departure")}</th><th>{t("Travelers")}</th><th>{t("Total")}</th><th>{t("Status")}</th><th>{t("Assigned")}</th><th>{t("Created")}</th></tr>
            </thead>
            <tbody>
              {tickets.map((tk) => (
                <tr key={tk.id} className="clickable" tabIndex={0} onClick={() => setParams({ open: String(tk.id) })}
                  onKeyDown={(e) => { if (e.key === "Enter") setParams({ open: String(tk.id) }); }}>
                  <td data-label={t("Reference")}><strong><bdi dir="ltr">{tk.reference}</bdi></strong></td>
                  <td data-label={t("Customer")}>
                    <div>{tk.lead_traveler_name}{tk.contact_phone && <div className="muted small"><bdi dir="ltr">{tk.contact_phone}</bdi></div>}</div>
                  </td>
                  <td data-label={t("Package")}>{tk.package_title}</td>
                  <td data-label={t("Departure")}>{shortDate(tk.departure_date)}</td>
                  <td data-label={t("Travelers")}>{travelersText(tk.adults, tk.children)}</td>
                  <td data-label={t("Total")}><Money value={tk.total_price} currency={tk.currency} /></td>
                  <td data-label={t("Status")}><Badge tone={TICKET_TONES[tk.status]}>{t(TICKET_STATUS_LABELS[tk.status])}</Badge></td>
                  <td data-label={t("Assigned")}>{tk.assigned_to?.full_name ?? <span className="muted">—</span>}</td>
                  <td data-label={t("Created")} className="muted small">{dateTime(tk.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openId && (
        <TicketModal id={Number(openId)} onClose={() => setParams({})} onSaved={load} />
      )}
    </div>
  );
}

type TicketForm = { status: string; assigned: string; payment_reference: string; internal_notes: string; total_price: string };

function formFrom(tk: Ticket): TicketForm {
  return {
    status: tk.status,
    assigned: tk.assigned_to ? String(tk.assigned_to.id) : "",
    payment_reference: tk.payment_reference ?? "",
    internal_notes: tk.internal_notes,
    total_price: String(tk.total_price),
  };
}

function TicketModal({ id, onClose, onSaved }: { id: number; onClose: () => void; onSaved: () => void }) {
  const { user, can } = useAuth();
  const { t } = useI18n();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [team, setTeam] = useState<User[]>([]);
  const [events, setEvents] = useState<TicketEvent[] | null>(null);
  const [form, setForm] = useState<TicketForm>({ status: "", assigned: "", payment_reference: "", internal_notes: "", total_price: "" });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadEvents = () => get<TicketEvent[]>(`/api/tickets/${id}/events`).then(setEvents).catch(() => setEvents([]));

  useEffect(() => {
    get<Ticket>(`/api/tickets/${id}`).then((tk) => {
      setTicket(tk);
      setForm(formFrom(tk));
    }).catch((e) => setError(e.message));
    get<User[]>("/api/team").then(setTeam).catch(() => {});
    loadEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const canManage = can("tickets.manage");
  const canAssign = can("tickets.assign");
  const isAdmin = user?.role === "company_admin";
  const dirty = !!ticket && JSON.stringify(form) !== JSON.stringify(formFrom(ticket));

  // Only the changes the server accepts from the current status.
  const statusOptions = ticket
    ? [ticket.status, ...(NEXT_TICKET_STATUSES[ticket.status] ?? []).filter((s) => ticket.status !== "cancelled" || isAdmin)]
    : [];
  const needsReference = NEEDS_PAYMENT_REFERENCE.includes(form.status);

  // Without tickets.assign an employee can only take a ticket nobody has, or let go of their own.
  const currentAssignee = ticket?.assigned_to ? String(ticket.assigned_to.id) : "";
  const mineOrFree = !currentAssignee || currentAssignee === String(user?.id);
  const assignOptions = canAssign
    ? team
    : team.filter((u) => String(u.id) === currentAssignee || (mineOrFree && u.id === user?.id));
  const canChangeAssignee = canManage && (canAssign || mineOrFree);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!ticket || busy) return;
    setError(null);
    setSaved(false);
    const body: Record<string, unknown> = {};
    if (form.status !== ticket.status) body.status = form.status as TicketStatus;
    if (form.payment_reference.trim() !== (ticket.payment_reference ?? "")) body.payment_reference = form.payment_reference.trim();
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
      setTicket(tk);
      setForm(formFrom(tk));
      setSaved(true);
      onSaved();
      loadEvents();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={ticket ? t("Ticket {reference}", { reference: ticket.reference }) : t("Ticket")} onClose={onClose} wide dirty={dirty}>
      {!ticket ? (error ? <ErrorBox error={error} /> : <div className="loading">{t("Loading…")}</div>) : (
        <>
          <div className="grid-2">
            <div>
              <h3>{ticket.package_title}</h3>
              <dl className="details">
                <dt>{t("Reference")}</dt><dd><bdi dir="ltr">{ticket.reference}</bdi></dd>
                <dt>{t("Departure")}</dt><dd>{shortDate(ticket.departure_date)}</dd>
                <dt>{t("Travelers")}</dt><dd>{travelersText(ticket.adults, ticket.children)}</dd>
                <dt>{t("Lead traveler")}</dt><dd>{ticket.lead_traveler_name}</dd>
                <dt>{t("Phone")}</dt><dd>{ticket.contact_phone ? <bdi dir="ltr">{ticket.contact_phone}</bdi> : "—"}</dd>
                <dt>{t("Email")}</dt><dd>{ticket.contact_email ? <bdi dir="ltr">{ticket.contact_email}</bdi> : "—"}</dd>
                <dt>{t("Customer")}</dt><dd><bdi>{customerLabel(ticket.customer)}</bdi></dd>
                <dt>{t("Special requests")}</dt><dd dir="auto">{ticket.special_requests || "—"}</dd>
                <dt>{t("Payment reference")}</dt><dd>{ticket.payment_reference ? <bdi dir="ltr">{ticket.payment_reference}</bdi> : "—"}</dd>
                <dt>{t("Total")}</dt><dd><strong><Money value={ticket.total_price} currency={ticket.currency} /></strong></dd>
                <dt>{t("Created")}</dt><dd>{t("{date} by {who}", { date: dateTime(ticket.created_at), who: ticket.created_by === "ai" ? t("AI agent") : t("staff") })}</dd>
              </dl>
              {ticket.conversation_id && can("conversations.view") && (
                <Link className="btn btn-sm" to={`/app/conversations/${ticket.conversation_id}`}>{t("Open the conversation")} →</Link>
              )}
            </div>
            <form onSubmit={save}>
              <Field label={t("Status")}>
                <select value={form.status} disabled={!canManage || busy} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  {statusOptions.map((k) => <option key={k} value={k}>{t(TICKET_STATUS_LABELS[k])}</option>)}
                </select>
              </Field>
              <Field label={t("Assigned to")}
                hint={!canAssign && !mineOrFree ? t("Only an employee who can assign tickets can change this.") : undefined}>
                <select value={form.assigned} disabled={!canChangeAssignee || busy} onChange={(e) => setForm({ ...form, assigned: e.target.value })}>
                  {(canAssign || mineOrFree) && <option value="">— {t("nobody")} —</option>}
                  {assignOptions.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
              </Field>
              <Field label={needsReference ? `${t("Payment reference")} *` : t("Payment reference")}
                hint={needsReference ? t("Required for paid and confirmed bookings: receipt or transfer number.") : t("Bank transfer ID, receipt number…")}>
                <input value={form.payment_reference} disabled={!canManage || busy} required={needsReference} dir="ltr"
                  maxLength={200} onChange={(e) => setForm({ ...form, payment_reference: e.target.value })} />
              </Field>
              <Field label={t("Total price ({currency})", { currency: ticket.currency })}
                hint={isAdmin ? undefined : t("Only a company admin can change the price.")}>
                <input type="number" min={0} step="0.001" value={form.total_price} disabled={!canManage || !isAdmin || busy} required
                  onChange={(e) => setForm({ ...form, total_price: e.target.value })} />
              </Field>
              <Field label={t("Internal notes")}>
                <textarea rows={4} value={form.internal_notes} disabled={!canManage || busy} dir="auto"
                  onChange={(e) => setForm({ ...form, internal_notes: e.target.value })} />
              </Field>
              <ErrorBox error={error} />
              {saved && !dirty && <div className="ok-box">{t("Saved.")}</div>}
              {canManage && <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Save ticket")}</button>}
            </form>
          </div>
          <TicketHistory events={events} currency={ticket.currency} />
        </>
      )}
    </Modal>
  );
}

function TicketHistory({ events, currency }: { events: TicketEvent[] | null; currency: string }) {
  const { t, lang } = useI18n();
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

  return (
    <section className="ticket-history">
      <h3>{t("History")}</h3>
      {events === null ? <div className="muted small">{t("Loading…")}</div> : events.length === 0 ? (
        <div className="muted small">{t("No changes yet.")}</div>
      ) : (
        <ol className="history-list">
          {[...events].reverse().map((ev) => (
            <li key={ev.id}>
              <span>{describe(ev)}</span>
              <span className="muted small">{dateTime(ev.created_at)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
