import { FormEvent, useEffect, useState } from "react";
import { get, put } from "../../api";
import { useI18n } from "../../lang";
import type { TripStatus } from "../../types";
import { shortDate } from "../../util";
import { moneyText } from "../Money";
import { ErrorBox, Field, Loading } from "../ui";
import { StatusBadge } from "./TripParts";

interface Figures {
  kind: "client" | "vendor"; currency: string; total: number; by_status: Record<string, number>; amount: number;
  upcoming: { id: number; reference: string; destination: string; depart_date: string }[];
  payments_due: { id: number; reference: string; label: string; due_date: string | null; amount: number | null; overdue: boolean }[];
  rating: number | null;
}

/** A business client's or vendor's own figures: requests by status, money, trips ahead and payments due. */
export function PartnerFigures() {
  const { t, lang } = useI18n();
  const [f, setF] = useState<Figures | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => get<Figures>("/api/partner/stats").then((x) => { setF(x); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);
  if (!f) return error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={220} />;
  const m = (v: number | null) => (v == null ? "—" : moneyText(v, f.currency, lang));
  const side = f.kind === "vendor" ? "vendor" : "client";
  return (
    <div>
      <h2 className="gx-portal-h2">{t("Your figures")}</h2>
      <div className="gx-b2b-meters gx-insight-cards">
        <div className="gx-b2b-meter"><div className="muted small">{f.kind === "vendor" ? t("Jobs") : t("Requests")}</div><div className="gx-b2b-num tnum">{f.total}</div></div>
        <div className="gx-b2b-meter"><div className="muted small">{f.kind === "vendor" ? t("Booked with you") : t("Spent on trips")}</div><div className="gx-b2b-num tnum">{m(f.amount)}</div></div>
        {f.rating != null && <div className="gx-b2b-meter"><div className="muted small">{t("Your rating")}</div><div className="gx-b2b-num">{f.rating}★</div></div>}
      </div>
      {Object.keys(f.by_status).length > 0 && (
        <section className="gx-card">
          <h3 className="gx-insight-h3">{t("By status")}</h3>
          <div className="gx-chips">{Object.entries(f.by_status).map(([s, n]) => <span key={s} className="gx-inline"><StatusBadge status={s as TripStatus} side={side} /> <strong className="tnum">{n}</strong></span>)}</div>
        </section>
      )}
      <div className="gx-insight-grid">
        <section className="gx-card">
          <h3 className="gx-insight-h3">{t("Trips ahead")}</h3>
          {f.upcoming.length === 0 ? <p className="muted small">{t("Nothing ahead.")}</p> : (
            <ol className="gx-insight-list">{f.upcoming.map((u) => <li key={u.id}>{u.reference} · {u.destination} · {shortDate(u.depart_date)}</li>)}</ol>
          )}
        </section>
        <section className="gx-card">
          <h3 className="gx-insight-h3">{f.kind === "vendor" ? t("Payments to receive") : t("Payments to make")}</h3>
          {f.payments_due.length === 0 ? <p className="muted small">{t("Nothing due.")}</p> : (
            <ol className="gx-insight-list">{f.payments_due.map((p) => (
              <li key={`${p.id}-${p.label}`} className={p.overdue ? "gx-bad" : ""}>{p.reference} · {p.label} · {m(p.amount)}{p.due_date && ` · ${t("due {date}", { date: shortDate(p.due_date) })}`}{p.overdue && ` · ${t("Late")}`}</li>
            ))}</ol>
          )}
        </section>
      </div>
    </div>
  );
}

interface QuoteDesign { intro: string; terms: string; valid_days: number; payment_terms: string }

/** The vendor's own quotation: an intro, payment terms, conditions and how long prices hold. */
export function VendorQuoteDesign() {
  const { t } = useI18n();
  const [q, setQ] = useState<QuoteDesign | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { get<QuoteDesign>("/api/partner/quote-settings").then(setQ).catch((e) => setError((e as Error).message)); }, []);
  if (!q) return error ? <ErrorBox error={error} /> : <Loading height={220} />;
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null); setSaved(false);
    try { setQ(await put<QuoteDesign>("/api/partner/quote-settings", q)); setSaved(true); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <form className="gx-card" onSubmit={save}>
      <h2 className="gx-card-title">{t("Your quotation")}</h2>
      <p className="gx-card-note">{t("The travel company sees this with every set of options you send.")}</p>
      <Field label={t("Introduction")}><textarea rows={3} value={q.intro} onChange={(e) => setQ({ ...q, intro: e.target.value })} maxLength={2000} dir="auto" /></Field>
      <Field label={t("Payment terms")}><textarea rows={2} value={q.payment_terms} onChange={(e) => setQ({ ...q, payment_terms: e.target.value })} maxLength={1000} dir="auto" placeholder={t("e.g. 30% on approval, the rest 14 days before travel")} /></Field>
      <Field label={t("Terms and conditions")}><textarea rows={4} value={q.terms} onChange={(e) => setQ({ ...q, terms: e.target.value })} maxLength={3000} dir="auto" /></Field>
      <Field label={t("Prices valid for (days)")}><input type="number" min={1} max={90} value={q.valid_days} onChange={(e) => setQ({ ...q, valid_days: Math.min(90, Math.max(1, Number(e.target.value) || 1)) })} /></Field>
      <ErrorBox error={error} />
      <div className="modal-actions">{saved && <span className="muted small">{t("Saved.")}</span>}<span className="spacer" /><button className="btn btn-primary" disabled={busy}>{t("Save")}</button></div>
    </form>
  );
}
