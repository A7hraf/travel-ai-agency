import { FormEvent, useEffect, useState } from "react";
import { del, get, post } from "../../api";
import { useI18n } from "../../lang";
import type { TripPart, VendorTrip } from "../../types";
import { shortDate } from "../../util";
import { ArrowLeft, Check, Plus, Trash, X } from "../Icon";
import { Empty, ErrorBox, Loading } from "../ui";
import { money, PART_LABEL, PartChip, StatusBadge, Steps, Thread, TripFacts } from "./TripParts";

function JobView({ job, onChange, onGone, onBack, canQuote }: {
  job: VendorTrip; onChange: (j: VendorTrip) => void; onGone: () => void; onBack: () => void; canQuote: boolean;
}) {
  const { t, lang } = useI18n();
  const [o, setO] = useState({ category: (job.needs[0] ?? "flight") as TripPart, title: "", provider: "", details: "", cost_price: "" });
  const [bookingRef, setBookingRef] = useState("");
  const [bookingNotes, setBookingNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const base = `/api/partner/jobs/${job.id}`;
  const quoting = job.status === "with_vendor";
  const approved = ["approved", "booked", "completed"].includes(job.status);
  const run = async (fn: () => Promise<VendorTrip>) => {
    setError(null);
    try { onChange(await fn()); } catch (err) { setError((err as Error).message); throw err; }
  };
  const add = (e: FormEvent) => {
    e.preventDefault();
    run(() => post<VendorTrip>(`${base}/options`, { ...o, provider: o.provider || null, details: o.details || null }))
      .then(() => setO({ ...o, title: "", provider: "", details: "", cost_price: "" })).catch(() => {});
  };
  const decline = async () => {
    if (!window.confirm(t("Decline this request? It goes back to the travel company."))) return;
    setError(null);
    try { await post(`${base}/decline`, {}); onGone(); } catch (err) { setError((err as Error).message); }
  };

  return (
    <div className="gx-portal-detail">
      <button type="button" className="link-btn" onClick={onBack}><ArrowLeft className="flip" />{t("All jobs")}</button>
      <div className="gx-req-head">
        <div><div className="gx-kicker">{job.reference}</div><h1 dir="auto">{job.destination}</h1></div>
        <StatusBadge status={job.status} side="vendor" />
      </div>
      <ErrorBox error={error} />
      <section className="gx-card">
        <TripFacts trip={job} extra={<>
          {job.brief && <div className="gx-facts-wide"><dt>{t("Brief")}</dt><dd className="gx-pre" dir="auto">{job.brief}</dd></div>}
          {job.traveller_names && <div className="gx-facts-wide"><dt>{t("Traveller names")}</dt><dd className="gx-pre" dir="auto">{job.traveller_names}</dd></div>}
        </>} />
        {!approved && <p className="muted small">{t("Traveller names are shared once the trip is approved.")}</p>}
        {quoting && job.accepted === null && (
          <div className="gx-inline">
            <button className="btn btn-primary" onClick={() => run(() => post<VendorTrip>(`${base}/accept`)).catch(() => {})}><Check />{t("Accept")}</button>
            <button className="btn btn-ghost" onClick={decline}><X />{t("Decline")}</button>
          </div>
        )}
      </section>

      <section className="gx-card">
        <h2 className="gx-card-title">{t("Your options")}</h2>
        {quoting && <p className="gx-card-note">{t("Give up to 3 options for each part, with your total price for all travellers.")}</p>}
        {job.options.length === 0 && <p className="muted">{t("No options yet.")}</p>}
        {job.options.map((x) => (
          <div key={x.id} className={`gx-opt ${x.chosen ? "chosen" : ""}`}>
            <PartChip part={x.category} />
            <div className="gx-opt-main">
              <strong dir="auto">{x.title}</strong>{x.provider && <span className="muted"> · {x.provider}</span>}
              {x.details && <div className="muted small gx-pre" dir="auto">{x.details}</div>}
            </div>
            <div className="gx-opt-prices"><strong>{money(x.cost_price, job.currency, lang)}</strong>{x.chosen && <span className="gx-status on">{t("Chosen: book this")}</span>}</div>
            {quoting && canQuote && <button type="button" className="icon-btn" aria-label={t("Remove")} onClick={() => run(() => del(`${base}/options/${x.id}`).then(() => get<VendorTrip>(base))).catch(() => {})}><Trash /></button>}
          </div>
        ))}
        {quoting && canQuote && (
          <form className="gx-opt-form" onSubmit={add}>
            <select value={o.category} onChange={(e) => setO({ ...o, category: e.target.value as TripPart })} aria-label={t("Part")}>
              {job.needs.map((p) => <option key={p} value={p}>{t(PART_LABEL[p])}</option>)}
            </select>
            <input value={o.title} onChange={(e) => setO({ ...o, title: e.target.value })} placeholder={t("Title (e.g. WY 601 Business, 08:10)")} aria-label={t("Title")} required minLength={2} maxLength={200} dir="auto" />
            <input value={o.provider} onChange={(e) => setO({ ...o, provider: e.target.value })} placeholder={t("Airline / hotel / operator")} aria-label={t("Provider")} maxLength={120} dir="auto" />
            <input value={o.cost_price} onChange={(e) => setO({ ...o, cost_price: e.target.value })} placeholder={t("Your price (total)")} aria-label={t("Your price (total)")} required inputMode="decimal" />
            <textarea value={o.details} onChange={(e) => setO({ ...o, details: e.target.value })} placeholder={t("Details: times, room type, conditions…")} aria-label={t("Details")} rows={2} maxLength={2000} dir="auto" />
            <div className="gx-opt-form-actions"><button className="btn btn-soft btn-sm"><Plus />{t("Add option")}</button></div>
          </form>
        )}
        {quoting && canQuote && job.options.length > 0 && (
          <button className="btn btn-primary gx-send" onClick={() => run(() => post<VendorTrip>(`${base}/submit`)).catch(() => {})}>{t("Send my options")}</button>
        )}
        {job.total_cost !== null && <div className="gx-totals"><span>{t("Total to book")} <strong>{money(job.total_cost, job.currency, lang)}</strong></span></div>}
      </section>

      {job.status === "approved" && (
        <form className="gx-card" onSubmit={(e) => { e.preventDefault(); run(() => post<VendorTrip>(`${base}/booked`, { booking_reference: bookingRef, booking_notes: bookingNotes || null })).catch(() => {}); }}>
          <h2 className="gx-card-title">{t("Booked? Add the references")}</h2>
          <input value={bookingRef} onChange={(e) => setBookingRef(e.target.value)} placeholder={t("Booking reference (PNR, hotel confirmation…)")} required minLength={2} maxLength={200} dir="ltr" />
          <textarea rows={2} value={bookingNotes} onChange={(e) => setBookingNotes(e.target.value)} placeholder={t("Notes for the travel company (optional)")} maxLength={4000} dir="auto" />
          <div className="modal-actions"><span className="spacer" /><button className="btn btn-primary">{t("Mark as booked")}</button></div>
        </form>
      )}
      {job.booking_reference && <section className="gx-card"><h2 className="gx-card-title">{t("Booking reference")}</h2><p className="gx-big" dir="ltr">{job.booking_reference}</p></section>}

      <section className="gx-card">
        <h2 className="gx-card-title">{t("Messages with the travel company")}</h2>
        <Thread me="vendor" messages={job.messages} disabled={["completed", "cancelled"].includes(job.status)}
          onSend={(text) => run(() => post<VendorTrip>(`${base}/messages`, { text }))} />
      </section>
      <section className="gx-card"><h2 className="gx-card-title">{t("Progress")}</h2><Steps steps={job.steps} /></section>
    </div>
  );
}

/** Vendor: the requests the travel company sent it. */
export default function VendorJobs({ canQuote }: { canQuote: boolean }) {
  const { t } = useI18n();
  const [list, setList] = useState<VendorTrip[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const load = () => get<VendorTrip[]>("/api/partner/jobs").then((l) => { setList(l); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);

  if (!list) return error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={220} />;
  const current = open !== null ? list.find((x) => x.id === open) : undefined;
  if (current) {
    return <JobView job={current} canQuote={canQuote} onBack={() => { setOpen(null); load(); }}
      onGone={() => { setOpen(null); load(); }} onChange={(j) => setList(list.map((x) => (x.id === j.id ? j : x)))} />;
  }
  return (
    <div>
      <h2 className="gx-portal-h2">{t("Requests for you")}</h2>
      {list.length === 0 ? <Empty>{t("No requests yet.")}</Empty> : (
        <ul className="gx-req-list">
          {list.map((r) => (
            <li key={r.id}>
              <button type="button" className="gx-req-row" onClick={() => setOpen(r.id)}>
                <span className="gx-req-ref">{r.reference}</span>
                <span className="gx-req-main" dir="auto"><strong>{r.destination}</strong> · {shortDate(r.depart_date)} · {t("{n} travellers", { n: r.travellers })}</span>
                <StatusBadge status={r.status} side="vendor" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
