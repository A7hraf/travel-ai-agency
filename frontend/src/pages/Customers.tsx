import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { download, get, patch } from "../api";
import { useAuth } from "../auth";
import { PageTitle } from "../components/admin/AdminUI";
import { AddressBook, ArrowLeft, ChatsCircle, DownloadSimple, MagnifyingGlass, Ticket } from "../components/Icon";
import { Money } from "../components/Money";
import { ErrorBox, Field } from "../components/ui";
import { useI18n } from "../lang";
import type { CustomerDetail, CustomerList, CustomerRow } from "../types";
import { CONVERSATION_STATUS_LABELS, customerLabel, shortDate, TICKET_STATUS_LABELS, timeAgo } from "../util";

const CHANNEL_LABELS: Record<string, string> = { web: "Website", whatsapp: "WhatsApp", instagram: "Instagram" };
const SORTS: [string, string][] = [
  ["last_contact", "Last contact"],
  ["first_contact", "First contact"],
  ["name", "Name"],
  ["bookings", "Most bookings"],
  ["booked", "Highest total booked"],
  ["conversations", "Most conversations"],
];

function Channels({ list }: { list: string[] }) {
  const { t } = useI18n();
  return <span className="bt-chans">{list.map((c) => <span key={c} className={`bt-chan ${c}`}>{t(CHANNEL_LABELS[c] ?? c)}</span>)}</span>;
}

export default function Customers() {
  const { id } = useParams();
  return id ? <CustomerPage id={Number(id)} /> : <CustomerListPage />;
}

function CustomerListPage() {
  const { t } = useI18n();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [booking, setBooking] = useState<"" | "true" | "false">("");
  const [channel, setChannel] = useState("");
  const [sort, setSort] = useState("last_contact");
  const [data, setData] = useState<CustomerList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const seq = useRef(0);
  const manage = can("customers.manage");

  const params = () => {
    const p = new URLSearchParams({ sort });
    if (q.trim()) p.set("q", q.trim());
    if (booking) p.set("has_booking", booking);
    if (channel) p.set("channel", channel);
    return p;
  };
  const load = () => {
    const n = ++seq.current;
    setError(null);
    get<CustomerList>(`/api/customers?${params()}&limit=500`)
      .then((d) => { if (n === seq.current) setData(d); })
      .catch((e) => { if (n === seq.current) setError((e as Error).message); });
  };
  useEffect(() => {
    const timer = window.setTimeout(load, q ? 250 : 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, booking, channel, sort]);

  const exportCsv = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await download(`/api/customers/export.csv?${params()}`, "customers.csv");
    } catch (e) {
      setExportError((e as Error).message);
    } finally {
      setExporting(false);
    }
  };

  const rows = data?.customers ?? null;
  return (
    <div>
      <PageTitle kicker={t("Agency workspace")} title={t("Customers")}
        subtitle={t("Everyone who wrote to you on your page, WhatsApp or Instagram, with their bookings.")}
        actions={manage && (
          <button type="button" className="btn btn-ghost" disabled={exporting} onClick={exportCsv}>
            <DownloadSimple aria-hidden="true" />{exporting ? t("Preparing…") : t("Export CSV")}
          </button>
        )} />
      <ErrorBox error={exportError} />
      <div className="bt-toolbar">
        <label className="ad-search">
          <MagnifyingGlass aria-hidden="true" />
          <input type="search" placeholder={t("Name, phone or email")} aria-label={t("Name, phone or email")} value={q}
            onChange={(e) => setQ(e.target.value)} />
        </label>
        <div className="chips" role="group" aria-label={t("Bookings")}>
          {([["", "All"], ["true", "With bookings"], ["false", "No booking yet"]] as const).map(([v, label]) => (
            <button key={v} type="button" className={`chip-btn ${booking === v ? "active" : ""}`} aria-pressed={booking === v}
              onClick={() => setBooking(v)}>{t(label)}</button>
          ))}
        </div>
        <select aria-label={t("Channel")} value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="">{t("All channels")}</option>
          {Object.entries(CHANNEL_LABELS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
        </select>
        <select aria-label={t("Sort by")} value={sort} onChange={(e) => setSort(e.target.value)}>
          {SORTS.map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
        </select>
      </div>

      <ErrorBox error={error} onRetry={load} />
      {rows === null && !error && <div className="skeleton" style={{ height: 320, borderRadius: 24 }} />}
      {rows && rows.length === 0 && (
        <div className="empty">
          <AddressBook className="empty-icon" aria-hidden="true" />
          {q || booking || channel ? t("No customer matches these filters.") : t("No customers yet. They appear here after their first message.")}
        </div>
      )}
      {rows && rows.length > 0 && data && (
        <>
          <p className="bt-count">{data.total > rows.length
            ? t("Showing {n} of {m} customers", { n: rows.length, m: data.total })
            : t("{n} customers", { n: data.total })}</p>
          <div className="table-wrap">
            <table className="table cards">
              <thead>
                <tr>
                  <th>{t("Customer")}</th><th>{t("Channels")}</th><th>{t("First contact")}</th><th>{t("Last contact")}</th>
                  <th>{t("Chats")}</th><th>{t("Bookings")}</th><th>{t("Booked")}</th><th>{t("Paid")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c: CustomerRow) => (
                  <tr key={c.id} className="clickable" tabIndex={0} onClick={() => navigate(`/app/customers/${c.id}`)}
                    onKeyDown={(e) => { if (e.key === "Enter") navigate(`/app/customers/${c.id}`); }}>
                    <td data-label="">
                      <span className="bt-who">
                        <Link to={`/app/customers/${c.id}`} onClick={(e) => e.stopPropagation()}><strong><bdi>{customerLabel(c)}</bdi></strong></Link>
                        {(c.phone || c.email) && <small><bdi dir="ltr">{[c.phone, c.email].filter(Boolean).join(" · ")}</bdi></small>}
                        {c.tags.length > 0 && <span className="bt-tags">{c.tags.map((tag) => <span key={tag} className="bt-tag">{tag}</span>)}</span>}
                      </span>
                    </td>
                    <td data-label={t("Channels")}><Channels list={c.channels} /></td>
                    <td data-label={t("First contact")} className="bt-num">{shortDate(c.first_contact)}</td>
                    <td data-label={t("Last contact")} className="bt-num">{c.last_contact ? timeAgo(c.last_contact) : "—"}</td>
                    <td data-label={t("Chats")} className="bt-num">{c.conversations}</td>
                    <td data-label={t("Bookings")} className="bt-num">{c.bookings}</td>
                    <td data-label={t("Booked")} className="bt-num"><Money value={c.total_booked} currency={data.currency} /></td>
                    <td data-label={t("Paid")} className="bt-num"><Money value={c.total_paid} currency={data.currency} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

interface FormState { name: string; phone: string; email: string; notes: string; tags: string }
const formOf = (c: CustomerDetail): FormState => ({
  name: c.name ?? "", phone: c.phone ?? "", email: c.email ?? "", notes: c.notes, tags: c.tags.join(", "),
});

function CustomerPage({ id }: { id: number }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const [c, setC] = useState<CustomerDetail | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const manage = can("customers.manage");

  const load = () => {
    setLoadError(null);
    get<CustomerDetail>(`/api/customers/${id}`).then((x) => { setC(x); setForm(formOf(x)); })
      .catch((e) => setLoadError((e as Error).message));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [id]);

  const back = <Link to="/app/customers" className="bt-back"><ArrowLeft className="flip" />{t("All customers")}</Link>;
  if (!c || !form) {
    return <div className="narrow ad-narrow">{back}{loadError ? <ErrorBox error={loadError} onRetry={load} /> : <div className="skeleton" style={{ height: 320, borderRadius: 24 }} />}</div>;
  }
  const dirty = JSON.stringify(form) !== JSON.stringify(formOf(c));
  const set = (k: keyof FormState, v: string) => { setSaved(false); setForm({ ...form, [k]: v }); };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await patch<CustomerDetail>(`/api/customers/${id}`, {
        name: form.name, phone: form.phone, email: form.email, notes: form.notes,
        tags: form.tags.split(",").map((x) => x.trim()).filter(Boolean),
      });
      setC(updated);
      setForm(formOf(updated));
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="narrow ad-narrow">
      {back}
      <PageTitle kicker={t("Customer")} title={<bdi>{customerLabel(c)}</bdi>}
        subtitle={<Channels list={c.channels} />} />

      <div className="bt-facts">
        <div className="bt-fact"><div className="bt-fact-label">{t("Bookings")}</div><div className="bt-fact-value">{c.bookings}</div></div>
        <div className="bt-fact"><div className="bt-fact-label">{t("Booked")}</div><div className="bt-fact-value"><Money value={c.total_booked} currency={c.currency} /></div></div>
        <div className="bt-fact"><div className="bt-fact-label">{t("Paid")}</div><div className="bt-fact-value"><Money value={c.total_paid} currency={c.currency} /></div></div>
        <div className="bt-fact"><div className="bt-fact-label">{t("First contact")}</div><div className="bt-fact-value small">{shortDate(c.first_contact)}</div></div>
      </div>

      <form className="ad-card" onSubmit={save}>
        <h2 className="ad-card-title"><span className="ad-card-icon"><AddressBook /></span>{t("Contact details")}</h2>
        {!manage && <p className="ad-card-note">{t("Only colleagues with the customers.manage permission can change these details.")}</p>}
        <fieldset disabled={!manage || busy} style={{ border: 0, padding: 0, margin: 0 }}>
          <div className="ad-grid-2">
            <Field label={t("Name")}><input value={form.name} maxLength={200} dir="auto" onChange={(e) => set("name", e.target.value)} /></Field>
            <Field label={t("Phone")}><input value={form.phone} maxLength={50} dir="ltr" onChange={(e) => set("phone", e.target.value)} /></Field>
            <Field label={t("Email")}><input type="email" value={form.email} maxLength={200} dir="ltr" onChange={(e) => set("email", e.target.value)} /></Field>
            <Field label={t("Labels")} hint={t("Separate with commas, for example VIP, family")}>
              <input value={form.tags} maxLength={400} dir="auto" onChange={(e) => set("tags", e.target.value)} />
            </Field>
          </div>
          <Field label={t("Notes")} hint={t("Only your team sees these notes.")}>
            <textarea rows={4} value={form.notes} maxLength={5000} dir="auto" onChange={(e) => set("notes", e.target.value)} />
          </Field>
        </fieldset>
        {c.whatsapp_id && <p className="bt-muted">{t("WhatsApp:")} <bdi dir="ltr">{c.whatsapp_id}</bdi></p>}
        <ErrorBox error={error} />
        {saved && <div className="ok-box ad-notice" role="status">{t("Saved.")}</div>}
        {manage && <div className="ad-form-actions"><button className="btn btn-primary" disabled={busy || !dirty}>{busy ? t("Saving…") : t("Save")}</button></div>}
      </form>

      <section className="ad-card">
        <h2 className="ad-card-title"><span className="ad-card-icon"><ChatsCircle /></span>{t("Conversations")}</h2>
        {c.conversation_list.length === 0 ? <p className="bt-muted">{t("No conversations.")}</p> : (
          <ul className="bt-list">
            {c.conversation_list.map((conv) => (
              <li key={conv.id}>
                <Link to={`/app/conversations/${conv.id}`}>{t("Conversation #{id}", { id: conv.id })}</Link>
                <Channels list={[conv.channel]} />
                <span className="pill">{t(CONVERSATION_STATUS_LABELS[conv.status] ?? conv.status)}</span>
                <span className="spacer" />
                <span className="bt-muted">{timeAgo(conv.last_message_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {c.can_see_tickets && (
        <section className="ad-card">
          <h2 className="ad-card-title"><span className="ad-card-icon"><Ticket /></span>{t("Tickets")}</h2>
          {c.ticket_list.length === 0 ? <p className="bt-muted">{t("No bookings yet.")}</p> : (
            <ul className="bt-list">
              {c.ticket_list.map((tk) => (
                <li key={tk.id}>
                  <Link to={`/app/tickets?open=${tk.id}`}><bdi dir="ltr">{tk.reference}</bdi></Link>
                  <span className={`pill st-${tk.status}`}>{t(TICKET_STATUS_LABELS[tk.status] ?? tk.status)}</span>
                  <span dir="auto">{tk.package_title}</span>
                  <span className="spacer" />
                  <span className="bt-muted">{shortDate(tk.departure_date)}</span>
                  <span className="bt-num"><Money value={tk.total_price} currency={tk.currency} /></span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
