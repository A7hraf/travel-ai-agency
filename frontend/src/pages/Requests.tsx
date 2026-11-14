import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { get, post, put, del } from "../api";
import { PageTitle } from "../components/admin/AdminUI";
import { ArrowLeft, Check, Plus, Trash, WhatsappLogo } from "../components/Icon";
import { money, PART_LABEL, PARTS, PartChip, STATUS, StatusBadge, STEP_LABEL, Thread, TripFacts } from "../components/b2b/TripParts";
import { Empty, ErrorBox, Field, Loading } from "../components/ui";
import { useI18n } from "../lang";
import type { Partner, PartnerList, StaffTrip, StaffTripOption, StaffTripRow, TripPart, TripStatus } from "../types";
import { dateTime, shortDate } from "../util";

const FILTERS: (TripStatus | "")[] = ["", "new", "with_vendor", "options_ready", "with_client", "chosen", "approved", "booked", "completed", "cancelled"];
const EDITABLE: TripStatus[] = ["new", "with_vendor", "options_ready"];

function RequestList() {
  const { t } = useI18n();
  const [rows, setRows] = useState<StaffTripRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<TripStatus | "">("");
  const load = () => get<StaffTripRow[]>(`/api/b2b/requests${status ? `?status=${status}` : ""}`)
    .then((r) => { setRows(r); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <PageTitle kicker={t("Agency workspace")} title={t("Business requests")}
        subtitle={t("Trips your business clients ask for. Forward them to a vendor, send the client up to 3 choices per part, approve, and track the booking.")} />
      <div className="gx-chips" role="group" aria-label={t("Status")}>
        {FILTERS.map((f) => (
          <button key={f || "all"} type="button" className={`gx-chip ${status === f ? "on" : ""}`} aria-pressed={status === f} onClick={() => setStatus(f)}>
            {f ? <StatusLabel s={f} /> : t("All")}
          </button>
        ))}
      </div>
      {!rows ? (error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={220} />) : rows.length === 0 ? <Empty>{t("No requests.")}</Empty> : (
        <ul className="gx-req-list">
          {rows.map((r) => (
            <li key={r.id}>
              <Link to={`/app/requests/${r.id}`} className="gx-req-row">
                <span className="gx-req-ref">{r.reference}</span>
                <span className="gx-req-main" dir="auto"><strong>{r.client_name}</strong> · {r.destination} · {shortDate(r.depart_date)} · {t("{n} travellers", { n: r.travellers })}</span>
                <span className="muted small">{r.vendor_name ?? "—"}</span>
                {r.source === "whatsapp" && <WhatsappLogo className="gx-req-wa" aria-label="WhatsApp" />}
                <StatusBadge status={r.status} side="staff" />
                <span className="muted small">{dateTime(r.updated_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StatusLabel({ s }: { s: TripStatus }) {
  const { t } = useI18n();
  return <>{t(STATUS[s].staff)}</>;
}

const EMPTY_OPTION = { category: "flight" as TripPart, title: "", provider: "", details: "", cost_price: "", price: "" };

function OptionForm({ needs, initial, onSave, onCancel }: {
  needs: TripPart[]; initial?: StaffTripOption; onSave: (body: Record<string, unknown>) => Promise<void>; onCancel?: () => void;
}) {
  const { t } = useI18n();
  const [o, setO] = useState(initial ? {
    category: initial.category, title: initial.title, provider: initial.provider ?? "", details: initial.details ?? "",
    cost_price: initial.cost_price === null ? "" : String(initial.cost_price), price: initial.price === null ? "" : String(initial.price),
  } : { ...EMPTY_OPTION, category: needs[0] ?? "flight" });
  const [busy, setBusy] = useState(false);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onSave({ ...o, provider: o.provider || null, details: o.details || null,
        cost_price: o.cost_price === "" ? null : o.cost_price, price: o.price === "" ? null : o.price });
      if (!initial) setO({ ...EMPTY_OPTION, category: o.category });
    } finally { setBusy(false); }
  };
  return (
    <form className="gx-opt-form" onSubmit={save}>
      <select value={o.category} onChange={(e) => setO({ ...o, category: e.target.value as TripPart })} aria-label={t("Part")}>
        {PARTS.map((p) => <option key={p} value={p}>{t(PART_LABEL[p])}</option>)}
      </select>
      <input value={o.title} onChange={(e) => setO({ ...o, title: e.target.value })} placeholder={t("Title (e.g. WY 601 Business, 08:10)")} aria-label={t("Title")} required minLength={2} maxLength={200} dir="auto" />
      <input value={o.provider} onChange={(e) => setO({ ...o, provider: e.target.value })} placeholder={t("Airline / hotel / operator")} aria-label={t("Provider")} maxLength={120} dir="auto" />
      <input value={o.cost_price} onChange={(e) => setO({ ...o, cost_price: e.target.value })} placeholder={t("Cost")} aria-label={t("Cost")} inputMode="decimal" />
      <input value={o.price} onChange={(e) => setO({ ...o, price: e.target.value })} placeholder={t("Client price")} aria-label={t("Client price")} inputMode="decimal" />
      <textarea value={o.details} onChange={(e) => setO({ ...o, details: e.target.value })} placeholder={t("Details shown to the client")} aria-label={t("Details")} rows={2} maxLength={2000} dir="auto" />
      <div className="gx-opt-form-actions">
        {onCancel && <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>{t("Cancel")}</button>}
        <button className="btn btn-soft btn-sm" disabled={busy}>{initial ? <><Check />{t("Save")}</> : <><Plus />{t("Add option")}</>}</button>
      </div>
    </form>
  );
}

function RequestDetail({ id }: { id: number }) {
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const [trip, setTrip] = useState<StaffTrip | null>(null);
  const [vendors, setVendors] = useState<Partner[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [vendorId, setVendorId] = useState<number | "">("");
  const [brief, setBrief] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [markup, setMarkup] = useState("");
  const [bookingRef, setBookingRef] = useState("");
  const [thread, setThread] = useState<"client" | "vendor">("client");
  const base = `/api/b2b/requests/${id}`;

  const show = (tr: StaffTrip) => {
    setTrip(tr);
    setPicked(tr.options.filter((o) => o.sent_to_client).map((o) => o.id));
    setMarkup(String(Number(tr.markup_percent)));
    if (!brief) setBrief(tr.vendor_brief ?? "");
  };
  const load = () => get<StaffTrip>(base).then((tr) => { show(tr); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => {
    load();
    get<PartnerList>("/api/partners").then((d) => setVendors(d.partners.filter((p) => p.kind === "vendor" && p.is_active && p.active_features.includes("vendor.requests")))).catch(() => {});
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (fn: () => Promise<StaffTrip>) => {
    setActionError(null);
    try { show(await fn()); } catch (err) { setActionError((err as Error).message); throw err; }
  };
  const act = (fn: () => Promise<StaffTrip>) => { run(fn).catch(() => {}); };

  if (!trip) return error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={300} />;
  const cur = trip.currency;
  const editable = EDITABLE.includes(trip.status);
  const pickedByPart = (p: TripPart) => trip.options.filter((o) => o.category === p && picked.includes(o.id)).length;
  const tooMany = PARTS.some((p) => pickedByPart(p) > 3);
  const prefill = () => setBrief([trip.purpose, `${trip.travellers} travellers`, trip.notes].filter(Boolean).join("\n"));

  return (
    <div className="gx-req">
      <button type="button" className="link-btn" onClick={() => navigate("/app/requests")}><ArrowLeft className="flip" />{t("All requests")}</button>
      <div className="gx-req-head">
        <div>
          <div className="gx-kicker">{trip.reference}{trip.source === "whatsapp" && <> · <WhatsappLogo /> WhatsApp</>}</div>
          <h1 dir="auto">{trip.client_name} · {trip.destination}</h1>
        </div>
        <StatusBadge status={trip.status} side="staff" />
      </div>
      <ErrorBox error={actionError} />

      <div className="gx-req-grid">
        <div className="gx-req-col">
          <section className="gx-card">
            <h2 className="gx-card-title">{t("Trip")}</h2>
            <TripFacts trip={trip} extra={<>
              {trip.budget && <div><dt>{t("Budget")}</dt><dd dir="auto">{trip.budget}</dd></div>}
              {trip.traveller_names && <div className="gx-facts-wide"><dt>{t("Traveller names")}</dt><dd className="gx-pre" dir="auto">{trip.traveller_names}</dd></div>}
              {trip.notes && <div className="gx-facts-wide"><dt>{t("Client notes")}</dt><dd className="gx-pre" dir="auto">{trip.notes}</dd></div>}
            </>} />
          </section>

          {editable && (
            <section className="gx-card">
              <h2 className="gx-card-title">{t("Vendor")}</h2>
              {trip.vendor_name && <p>{t("Now with {name}", { name: trip.vendor_name })} · {trip.vendor_accepted ? t("accepted") : t("not answered yet")}</p>}
              <p className="gx-card-note">{t("The vendor sees the route, dates, number of travellers, the parts and your brief. Never the client's name, notes, budget or prices. Traveller names are shared after approval.")}</p>
              <Field label={t("Vendor")}>
                <select value={vendorId} onChange={(e) => setVendorId(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">{t("Choose a vendor")}</option>
                  {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              </Field>
              <Field label={t("Brief for the vendor")} hint={<button type="button" className="link-btn" onClick={prefill}>{t("Fill from the request")}</button>}>
                <textarea rows={3} value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={4000} dir="auto" />
              </Field>
              <button className="btn btn-primary" disabled={!vendorId}
                onClick={() => act(() => post<StaffTrip>(`${base}/vendor`, { vendor_id: vendorId, brief: brief || null }))}>
                {trip.vendor_id ? t("Send to this vendor instead") : t("Send to vendor")}
              </button>
            </section>
          )}

          <section className="gx-card">
            <div className="gx-row-between">
              <h2 className="gx-card-title">{t("Options")}</h2>
              {editable && (
                <form className="gx-markup" onSubmit={(e) => { e.preventDefault(); act(() => put<StaffTrip>(`${base}/markup`, { markup_percent: markup || "0" })); }}>
                  <label>{t("Margin %")} <input value={markup} onChange={(e) => setMarkup(e.target.value)} inputMode="decimal" size={5} /></label>
                  <button className="btn btn-sm btn-ghost">{t("Apply")}</button>
                </form>
              )}
            </div>
            {editable && <p className="gx-card-note">{t("Tick up to 3 choices per part to send. Options without a client price get the cost plus your margin.")}</p>}
            {trip.options.length === 0 && <p className="muted">{t("No options yet. Wait for the vendor, or add them yourself.")}</p>}
            {PARTS.filter((p) => trip.options.some((o) => o.category === p)).map((p) => (
              <div key={p} className="gx-opt-group">
                <div className="gx-opt-group-head"><PartChip part={p} />{editable && <span className={`muted small ${pickedByPart(p) > 3 ? "error-text" : ""}`}>{pickedByPart(p)} / 3</span>}</div>
                {trip.options.filter((o) => o.category === p).map((o) => editing === o.id ? (
                  <OptionForm key={o.id} needs={trip.needs} initial={o} onCancel={() => setEditing(null)}
                    onSave={async (body) => { await run(() => put<StaffTrip>(`${base}/options/${o.id}`, body)); setEditing(null); }} />
                ) : (
                  <div key={o.id} className={`gx-opt ${o.chosen ? "chosen" : ""}`}>
                    {editable && <input type="checkbox" checked={picked.includes(o.id)} aria-label={t("Send {name}", { name: o.title })}
                      onChange={() => setPicked(picked.includes(o.id) ? picked.filter((x) => x !== o.id) : [...picked, o.id])} />}
                    <div className="gx-opt-main">
                      <strong dir="auto">{o.title}</strong>{o.provider && <span className="muted"> · {o.provider}</span>}
                      {o.details && <div className="muted small gx-pre" dir="auto">{o.details}</div>}
                      <div className="muted small">{o.added_by === "vendor" ? t("From the vendor") : t("Added by your team")}{o.sent_to_client && ` · ${t("sent to the client")}`}{o.chosen && ` · ${t("chosen")}`}</div>
                    </div>
                    <div className="gx-opt-prices">
                      <span className="muted small">{t("Cost")} {money(o.cost_price, cur, lang)}</span>
                      {o.price !== null || o.cost_price === null
                        ? <strong>{money(o.price, cur, lang)}</strong>
                        : <span className="muted" title={t("Price with your margin, set when you send")}>≈ {money(Number(o.cost_price) * (1 + Number(trip.markup_percent) / 100), cur, lang)}</span>}
                    </div>
                    {editable && <button type="button" className="btn btn-sm btn-ghost" onClick={() => setEditing(o.id)}>{t("Edit")}</button>}
                    {editable && <button type="button" className="icon-btn" aria-label={t("Remove")} onClick={() => act(() => del(`${base}/options/${o.id}`).then(() => get<StaffTrip>(base)))}><Trash /></button>}
                  </div>
                ))}
              </div>
            ))}
            {editable && <OptionForm needs={trip.needs} onSave={(body) => run(() => post<StaffTrip>(`${base}/options`, body))} />}
            {editable && (
              <button className="btn btn-primary gx-send" disabled={!picked.length || tooMany}
                onClick={() => act(() => post<StaffTrip>(`${base}/send`, { option_ids: picked }))}>
                {t("Send {n} choices to the client", { n: picked.length })}
              </button>
            )}
            {trip.total_price !== null && (
              <div className="gx-totals">
                <span>{t("Client pays")} <strong>{money(trip.total_price, cur, lang)}</strong></span>
                {trip.total_cost !== null && <span>{t("Cost")} {money(trip.total_cost, cur, lang)}</span>}
                {trip.total_cost !== null && <span>{t("Margin")} <strong>{money(Number(trip.total_price) - Number(trip.total_cost), cur, lang)}</strong></span>}
              </div>
            )}
          </section>

          <section className="gx-card gx-req-actions">
            {trip.status === "chosen" && <button className="btn btn-primary" onClick={() => act(() => post<StaffTrip>(`${base}/approve`))}><Check />{t("Approve the client's choice")}</button>}
            {trip.status === "approved" && (
              <form className="gx-inline" onSubmit={(e) => { e.preventDefault(); act(() => post<StaffTrip>(`${base}/booked`, { booking_reference: bookingRef })); }}>
                <input value={bookingRef} onChange={(e) => setBookingRef(e.target.value)} placeholder={t("Booking reference (PNR, hotel confirmation…)")} required minLength={2} maxLength={200} dir="ltr" />
                <button className="btn btn-soft">{t("Mark as booked")}</button>
              </form>
            )}
            {trip.status === "approved" && trip.vendor_name && <p className="muted small">{t("{name} books it and adds the booking reference. You can also do it here.", { name: trip.vendor_name })}</p>}
            {trip.booking_reference && <p>{t("Booking reference")}: <strong dir="ltr">{trip.booking_reference}</strong>{trip.booking_notes && <span className="muted"> · {trip.booking_notes}</span>}</p>}
            {trip.status === "booked" && <button className="btn btn-soft" onClick={() => act(() => post<StaffTrip>(`${base}/complete`))}>{t("Mark as completed")}</button>}
            {!["completed", "cancelled"].includes(trip.status) && (
              <button className="btn btn-ghost btn-danger-text" onClick={() => { if (window.confirm(t("Cancel this request?"))) act(() => post<StaffTrip>(`${base}/cancel`, {})); }}>{t("Cancel request")}</button>
            )}
          </section>
        </div>

        <div className="gx-req-col">
          <section className="gx-card">
            <div className="seg" role="tablist" aria-label={t("Messages")}>
              <button type="button" role="tab" aria-selected={thread === "client"} className={thread === "client" ? "active" : ""} onClick={() => setThread("client")}>{t("With the client")}</button>
              <button type="button" role="tab" aria-selected={thread === "vendor"} className={thread === "vendor" ? "active" : ""} onClick={() => setThread("vendor")} disabled={!trip.vendor_id && !trip.messages.some((m) => m.thread === "vendor")}>{t("With the vendor")}</button>
            </div>
            <p className="muted small">{t("The client and the vendor never see each other's messages.")}</p>
            <Thread me="staff" messages={trip.messages.filter((m) => m.thread === thread)} disabled={thread === "vendor" && !trip.vendor_id}
              onSend={(text) => run(() => post<StaffTrip>(`${base}/messages`, { thread, text }))} />
          </section>
          <section className="gx-card">
            <h2 className="gx-card-title">{t("History")}</h2>
            <ol className="gx-steps">
              {trip.events.map((e, i) => (
                <li key={i}><span>{t(STEP_LABEL[e.action] ?? e.action)}{e.detail && <span className="muted" dir="auto"> · {e.detail}</span>}</span>
                  <time>{e.actor_name ?? ""} · {dateTime(e.created_at)}</time></li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}

export default function Requests() {
  const { id } = useParams();
  return id ? <RequestDetail id={Number(id)} /> : <RequestList />;
}
