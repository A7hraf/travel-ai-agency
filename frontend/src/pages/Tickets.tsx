import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { get, patch } from "../api";
import { useAuth } from "../auth";
import { Badge, Empty, ErrorBox, Field, Modal, PageHeader, TICKET_TONES } from "../components/ui";
import type { Ticket, TicketStatus, User } from "../types";
import { Money } from "../components/Money";
import { customerLabel, dateTime, shortDate, TICKET_STATUS_LABELS, usePolling } from "../util";

export default function Tickets() {
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState("");
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState("");
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const openId = params.get("open");

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
      <PageHeader title="Booking tickets"
        subtitle="The AI creates a ticket when a customer confirms a booking. Your team takes the payment and confirms it." />
      <div className="toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {Object.entries(TICKET_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input placeholder="Reference, name or phone" value={search} onChange={(e) => setSearch(e.target.value)} />
        <label className="check"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Assigned to me</label>
      </div>

      {tickets === null ? <div className="loading">Loading…</div> : tickets.length === 0 ? (
        <Empty>No tickets yet. They appear here when the AI closes a booking.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Reference</th><th>Customer</th><th>Package</th><th>Departure</th><th>Travelers</th><th>Total</th><th>Status</th><th>Assigned</th><th>Created</th></tr>
            </thead>
            <tbody>
              {tickets.map((t) => (
                <tr key={t.id} className="clickable" onClick={() => setParams({ open: String(t.id) })}>
                  <td><strong>{t.reference}</strong></td>
                  <td>{t.lead_traveler_name}<div className="muted small">{t.contact_phone}</div></td>
                  <td>{t.package_title}</td>
                  <td>{shortDate(t.departure_date)}</td>
                  <td>{t.adults} adult{t.adults > 1 ? "s" : ""}{t.children ? `, ${t.children} child` : ""}</td>
                  <td><Money value={t.total_price} currency={t.currency} /></td>
                  <td><Badge tone={TICKET_TONES[t.status]}>{TICKET_STATUS_LABELS[t.status]}</Badge></td>
                  <td>{t.assigned_to?.full_name ?? <span className="muted">—</span>}</td>
                  <td className="muted small">{dateTime(t.created_at)}</td>
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

function TicketModal({ id, onClose, onSaved }: { id: number; onClose: () => void; onSaved: () => void }) {
  const { user, can } = useAuth();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [team, setTeam] = useState<User[]>([]);
  const [form, setForm] = useState({ status: "", assigned: "", payment_reference: "", internal_notes: "", total_price: "" });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    get<Ticket>(`/api/tickets/${id}`).then((t) => {
      setTicket(t);
      setForm({
        status: t.status,
        assigned: t.assigned_to ? String(t.assigned_to.id) : "",
        payment_reference: t.payment_reference ?? "",
        internal_notes: t.internal_notes,
        total_price: String(t.total_price),
      });
    }).catch((e) => setError(e.message));
    get<User[]>("/api/team").then(setTeam).catch(() => {});
  }, [id]);

  const canManage = can("tickets.manage");
  const canAssign = can("tickets.assign");

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!ticket) return;
    setError(null);
    setSaved(false);
    const body: Record<string, unknown> = {
      status: form.status as TicketStatus,
      payment_reference: form.payment_reference,
      internal_notes: form.internal_notes,
      total_price: Number(form.total_price),
    };
    const current = ticket.assigned_to ? String(ticket.assigned_to.id) : "";
    if (form.assigned !== current) {
      if (form.assigned) body.assigned_to_id = Number(form.assigned);
      else body.unassign = true;
    }
    try {
      setTicket(await patch<Ticket>(`/api/tickets/${id}`, body));
      setSaved(true);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <Modal title={ticket ? `Ticket ${ticket.reference}` : "Ticket"} onClose={onClose} wide>
      {!ticket ? <ErrorBox error={error} /> : (
        <div className="grid-2">
          <div>
            <h3>{ticket.package_title}</h3>
            <dl className="details">
              <dt>Departure</dt><dd>{shortDate(ticket.departure_date)}</dd>
              <dt>Travelers</dt><dd>{ticket.adults} adults, {ticket.children} children</dd>
              <dt>Lead traveler</dt><dd>{ticket.lead_traveler_name}</dd>
              <dt>Phone</dt><dd>{ticket.contact_phone ?? "—"}</dd>
              <dt>Email</dt><dd>{ticket.contact_email ?? "—"}</dd>
              <dt>Customer</dt><dd>{customerLabel(ticket.customer)}</dd>
              <dt>Special requests</dt><dd>{ticket.special_requests || "—"}</dd>
              <dt>Total</dt><dd><strong><Money value={ticket.total_price} currency={ticket.currency} /></strong></dd>
              <dt>Created</dt><dd>{dateTime(ticket.created_at)} by {ticket.created_by === "ai" ? "AI agent" : "staff"}</dd>
            </dl>
            {ticket.conversation_id && can("conversations.view") && (
              <Link className="btn btn-sm" to={`/app/conversations/${ticket.conversation_id}`}>Open the conversation →</Link>
            )}
          </div>
          <form onSubmit={save}>
            <Field label="Status">
              <select value={form.status} disabled={!canManage} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {Object.entries(TICKET_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="Assigned to">
              <select value={form.assigned} disabled={!canManage} onChange={(e) => setForm({ ...form, assigned: e.target.value })}>
                <option value="">— nobody —</option>
                {team.filter((u) => canAssign || u.id === user?.id || String(u.id) === form.assigned).map((u) => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
            </Field>
            <Field label="Payment reference" hint="Bank transfer ID, receipt number…">
              <input value={form.payment_reference} disabled={!canManage}
                onChange={(e) => setForm({ ...form, payment_reference: e.target.value })} />
            </Field>
            <Field label={`Total price (${ticket.currency})`}>
              <input type="number" min={0} step="0.001" value={form.total_price} disabled={!canManage}
                onChange={(e) => setForm({ ...form, total_price: e.target.value })} />
            </Field>
            <Field label="Internal notes">
              <textarea rows={4} value={form.internal_notes} disabled={!canManage}
                onChange={(e) => setForm({ ...form, internal_notes: e.target.value })} />
            </Field>
            <ErrorBox error={error} />
            {saved && <div className="ok-box">Saved.</div>}
            {canManage && <button className="btn btn-primary">Save ticket</button>}
          </form>
        </div>
      )}
    </Modal>
  );
}
