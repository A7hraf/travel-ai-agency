import { FormEvent, useEffect, useState } from "react";
import { get, post } from "../../api";
import { useI18n } from "../../lang";
import type { ClientTrip, TripPart } from "../../types";
import { shortDate } from "../../util";
import { ArrowLeft, Check, Plus } from "../Icon";
import { Empty, ErrorBox, Field, Loading } from "../ui";
import { money, PART_LABEL, PARTS, PartChip, StatusBadge, Steps, Thread, TripFacts } from "./TripParts";

function NewRequest({ onCreated, onCancel }: { onCreated: (t: ClientTrip) => void; onCancel: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({ purpose: "", origin: "Muscat", destination: "", depart_date: "", return_date: "", travellers: 1,
    traveller_names: "", budget: "", notes: "" });
  const [needs, setNeeds] = useState<TripPart[]>(["flight", "hotel"]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string | number) => setF({ ...f, [k]: v });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onCreated(await post<ClientTrip>("/api/partner/requests", {
        ...f, needs, depart_date: f.depart_date || null, return_date: f.return_date || null,
        purpose: f.purpose || null, origin: f.origin || null, traveller_names: f.traveller_names || null,
        budget: f.budget || null, notes: f.notes || null,
      }));
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <form className="gx-card" onSubmit={submit}>
      <h2 className="gx-card-title">{t("New trip request")}</h2>
      <div className="form-grid">
        <Field label={t("From")}><input value={f.origin} onChange={(e) => set("origin", e.target.value)} maxLength={120} dir="auto" /></Field>
        <Field label={t("To")}><input value={f.destination} onChange={(e) => set("destination", e.target.value)} required minLength={2} maxLength={120} dir="auto" /></Field>
        <Field label={t("Departure")}><input type="date" value={f.depart_date} onChange={(e) => set("depart_date", e.target.value)} /></Field>
        <Field label={t("Return")}><input type="date" value={f.return_date} min={f.depart_date || undefined} onChange={(e) => set("return_date", e.target.value)} /></Field>
        <Field label={t("Travellers")}><input type="number" min={1} max={500} value={f.travellers} onChange={(e) => set("travellers", Math.max(1, Number(e.target.value) || 1))} /></Field>
        <Field label={t("Purpose")}><input value={f.purpose} onChange={(e) => set("purpose", e.target.value)} maxLength={200} dir="auto" placeholder={t("Meeting, conference, training…")} /></Field>
        <Field label={t("Budget (optional)")}><input value={f.budget} onChange={(e) => set("budget", e.target.value)} maxLength={120} dir="auto" /></Field>
      </div>
      <div className="field-label">{t("What do you need?")}</div>
      <div className="gx-parts gx-parts-pick">
        {PARTS.map((p) => (
          <label key={p} className={`gx-part-pick ${needs.includes(p) ? "on" : ""}`}>
            <input type="checkbox" checked={needs.includes(p)} onChange={() => setNeeds(needs.includes(p) ? needs.filter((x) => x !== p) : [...needs, p])} />
            {t(PART_LABEL[p])}
          </label>
        ))}
      </div>
      <Field label={t("Traveller names")} hint={t("One per line, as in the passport.")}>
        <textarea rows={3} value={f.traveller_names} onChange={(e) => set("traveller_names", e.target.value)} maxLength={4000} dir="auto" />
      </Field>
      <Field label={t("Notes and preferences")}><textarea rows={3} value={f.notes} onChange={(e) => set("notes", e.target.value)} maxLength={4000} dir="auto" placeholder={t("Cabin class, hotel area, times…")} /></Field>
      <ErrorBox error={error} />
      <div className="modal-actions">
        <span className="spacer" />
        <button type="button" className="btn btn-ghost" onClick={onCancel}>{t("Cancel")}</button>
        <button className="btn btn-primary" disabled={busy || !needs.length}>{busy ? t("Sending…") : t("Send request")}</button>
      </div>
    </form>
  );
}

function RequestView({ trip, onChange, onBack, canWrite }: { trip: ClientTrip; onChange: (t: ClientTrip) => void; onBack: () => void; canWrite: boolean }) {
  const { t, lang } = useI18n();
  const [choice, setChoice] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const base = `/api/partner/requests/${trip.id}`;
  const parts = PARTS.filter((p) => trip.options.some((o) => o.category === p));
  const choosing = trip.status === "with_client" && canWrite;
  const ready = parts.every((p) => choice[p]);
  const run = async (fn: () => Promise<ClientTrip>) => {
    setError(null);
    try { onChange(await fn()); } catch (err) { setError((err as Error).message); }
  };
  const total = parts.reduce((sum, p) => sum + Number(trip.options.find((o) => o.id === choice[p])?.price ?? 0), 0);

  return (
    <div className="gx-portal-detail">
      <button type="button" className="link-btn" onClick={onBack}><ArrowLeft className="flip" />{t("All requests")}</button>
      <div className="gx-req-head">
        <div><div className="gx-kicker">{trip.reference}</div><h1 dir="auto">{trip.destination}</h1></div>
        <StatusBadge status={trip.status} side="client" />
      </div>
      <ErrorBox error={error} />
      <section className="gx-card"><TripFacts trip={trip} /></section>

      {parts.length > 0 && (
        <section className="gx-card">
          <h2 className="gx-card-title">{choosing ? t("Choose one option for each part") : t("Your options")}</h2>
          {parts.map((p) => (
            <div key={p} className="gx-opt-group" role="radiogroup" aria-label={t(PART_LABEL[p])}>
              <div className="gx-opt-group-head"><PartChip part={p} /></div>
              {trip.options.filter((o) => o.category === p).map((o) => (
                <label key={o.id} className={`gx-opt ${choosing ? "pick" : ""} ${(choosing ? choice[p] === o.id : o.chosen) ? "chosen" : ""}`}>
                  {choosing && <input type="radio" name={`part-${p}`} checked={choice[p] === o.id} onChange={() => setChoice({ ...choice, [p]: o.id })} />}
                  <div className="gx-opt-main">
                    <strong dir="auto">{o.title}</strong>{o.provider && <span className="muted"> · {o.provider}</span>}
                    {o.details && <div className="muted small gx-pre" dir="auto">{o.details}</div>}
                  </div>
                  <div className="gx-opt-prices"><strong>{money(o.price, trip.currency, lang)}</strong>{!choosing && o.chosen && <span className="gx-status on">{t("Chosen")}</span>}</div>
                </label>
              ))}
            </div>
          ))}
          {choosing && (
            <div className="gx-totals">
              <span>{t("Total")} <strong>{ready ? money(total, trip.currency, lang) : "—"}</strong></span>
              <span className="spacer" />
              <button className="btn btn-primary" disabled={!ready} onClick={() => run(() => post<ClientTrip>(`${base}/choose`, { option_ids: parts.map((p) => choice[p]) }))}><Check />{t("Confirm my choice")}</button>
            </div>
          )}
          {!choosing && trip.total_price !== null && <div className="gx-totals"><span>{t("Total")} <strong>{money(trip.total_price, trip.currency, lang)}</strong></span></div>}
        </section>
      )}
      {trip.booking_reference && <section className="gx-card"><h2 className="gx-card-title">{t("Booking reference")}</h2><p className="gx-big" dir="ltr">{trip.booking_reference}</p></section>}

      <section className="gx-card">
        <h2 className="gx-card-title">{t("Messages")}</h2>
        <Thread me="client" messages={trip.messages} disabled={!canWrite || ["completed", "cancelled"].includes(trip.status)}
          onSend={(text) => run(() => post<ClientTrip>(`${base}/messages`, { text }))} />
      </section>
      <section className="gx-card"><h2 className="gx-card-title">{t("Progress")}</h2><Steps steps={trip.steps} /></section>
      {canWrite && ["new", "with_vendor", "options_ready", "with_client", "chosen"].includes(trip.status) && (
        <button className="btn btn-ghost btn-danger-text" onClick={() => { if (window.confirm(t("Cancel this request?"))) run(() => post<ClientTrip>(`${base}/cancel`, {})); }}>{t("Cancel request")}</button>
      )}
    </div>
  );
}

/** Business client: its trip requests, a new request, and choosing options. */
export default function ClientRequests({ canWrite }: { canWrite: boolean }) {
  const { t } = useI18n();
  const [list, setList] = useState<ClientTrip[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | "new" | null>(null);
  const load = () => get<ClientTrip[]>("/api/partner/requests").then((l) => { setList(l); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);
  const replace = (tr: ClientTrip) => setList((l) => (l ? [tr, ...l.filter((x) => x.id !== tr.id)] : [tr]));

  if (!list) return error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={220} />;
  if (open === "new") return <NewRequest onCancel={() => setOpen(null)} onCreated={(tr) => { replace(tr); setOpen(tr.id); }} />;
  const current = typeof open === "number" ? list.find((x) => x.id === open) : undefined;
  if (current) return <RequestView trip={current} canWrite={canWrite} onChange={replace} onBack={() => { setOpen(null); load(); }} />;

  return (
    <div>
      <div className="gx-row-between">
        <h2 className="gx-portal-h2">{t("Your trip requests")}</h2>
        {canWrite && <button className="btn btn-primary" onClick={() => setOpen("new")}><Plus />{t("New trip request")}</button>}
      </div>
      {list.length === 0 ? <Empty>{t("No requests yet.")}</Empty> : (
        <ul className="gx-req-list">
          {list.map((r) => (
            <li key={r.id}>
              <button type="button" className="gx-req-row" onClick={() => setOpen(r.id)}>
                <span className="gx-req-ref">{r.reference}</span>
                <span className="gx-req-main" dir="auto"><strong>{r.destination}</strong> · {shortDate(r.depart_date)} · {t("{n} travellers", { n: r.travellers })}</span>
                <StatusBadge status={r.status} side="client" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
