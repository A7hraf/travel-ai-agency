import { FormEvent, useState } from "react";
import { put } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { Service, ServiceField, Ticket } from "../../types";
import { shortDate, travelersText } from "../../util";
import { PencilSimple, WarningCircle } from "../Icon";
import { PREFERENCE_LABEL } from "../clients/preferences";
import { ErrorBox } from "../ui";
import AskClient from "./AskClient";

export function FieldInput({ f, value, onChange }: { f: ServiceField; value: string; onChange: (v: string) => void }) {
  const { t } = useI18n();
  if (f.type === "long_text") return <textarea rows={2} value={value} onChange={(e) => onChange(e.target.value)} maxLength={2000} dir="auto" />;
  if (f.type === "choice") {
    return (
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>
        {f.choices.map((c) => <option key={c} value={c}>{c}</option>)}
        {value && !f.choices.includes(value) && <option value={value}>{value}</option>}
      </select>
    );
  }
  return <input value={value} onChange={(e) => onChange(e.target.value)} maxLength={300} dir={["phone", "email", "date", "number"].includes(f.type) ? "ltr" : "auto"}
    type={f.type === "date" ? "date" : f.type === "email" ? "email" : "text"} inputMode={f.type === "number" ? "numeric" : f.type === "phone" ? "tel" : undefined}
    placeholder={f.type === "phone" ? "+968 9123 4567" : undefined} aria-label={t(f.label_en)} />;
}

/** What the client asked: the service's questions and answers, editable by staff (calls, corrections). */
export default function RequestDetails({ ticket, services, onChange }: { ticket: Ticket; services: Service[]; onChange: (t: Ticket) => void }) {
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const service = services.find((s) => s.id === ticket.service?.id);
  const [edit, setEdit] = useState<Record<string, string> | null>(null);
  const [notes, setNotes] = useState(ticket.special_requests);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const answers = ticket.answers ?? {};
  const fields = service?.fields ?? [];
  const label = (f: ServiceField) => (lang === "ar" ? f.label_ar : f.label_en);
  const missing = fields.filter((f) => f.required && !answers[f.key]?.trim());
  const extra = Object.keys(answers).filter((k) => !fields.some((f) => f.key === k));
  const prefs = Object.entries(ticket.client_preferences ?? {});
  const editable = can("tickets.manage") && !!service && service.pricing !== "packages" && !["cancelled", "rejected", "confirmed"].includes(ticket.status);
  const show = (f: ServiceField) => {
    const v = answers[f.key];
    if (!v) return null;
    return f.type === "date" ? shortDate(v) : v;
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!edit) return;
    setBusy(true); setError(null);
    try {
      onChange(await put<Ticket>(`/api/tickets/${ticket.id}/details`, { answers: edit, special_requests: notes }));
      setEdit(null);
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="rw-request">
      {ticket.client_note && ["changes", "new", "chosen"].includes(ticket.status) && (
        <div className="gx-rq-note" role="note"><WarningCircle weight="fill" /><span><strong>{t("The client asked for changes:")}</strong> <span dir="auto">{ticket.client_note}</span></span></div>
      )}
      {missing.length > 0 && !edit && (
        <div className="gx-rq-hint warn" role="note"><WarningCircle weight="fill" />
          <span>{t("Still to ask the client:")} {missing.map(label).join(", ")}</span></div>
      )}
      {!service || service.pricing === "packages" ? (
        <dl className="rw-facts">
          <dt>{t("Package")}</dt><dd dir="auto">{ticket.package_title}</dd>
          <dt>{t("Departure")}</dt><dd>{shortDate(ticket.departure_date)}</dd>
          <dt>{t("Travellers")}</dt><dd>{travelersText(ticket.adults, ticket.children)}</dd>
          <dt>{t("Lead traveller")}</dt><dd><bdi>{ticket.lead_traveler_name || "—"}</bdi></dd>
          {ticket.contact_email && <><dt>{t("Email")}</dt><dd><bdi dir="ltr">{ticket.contact_email}</bdi></dd></>}
        </dl>
      ) : edit ? (
        <form className="rw-edit" onSubmit={save}>
          <div className="rw-edit-grid">
            {fields.map((f) => (
              <label key={f.key} className={f.type === "long_text" ? "wide" : ""}>
                <span>{label(f)}{f.required && " *"}</span>
                <FieldInput f={f} value={edit[f.key] ?? ""} onChange={(v) => setEdit({ ...edit, [f.key]: v })} />
              </label>
            ))}
            <label className="wide"><span>{t("Summary and special requests")}</span>
              <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4000} dir="auto" /></label>
          </div>
          <ErrorBox error={error} />
          <div className="rw-row-end">
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setEdit(null)}>{t("Cancel")}</button>
            <button className="btn btn-sm btn-primary" disabled={busy}>{t("Save")}</button>
          </div>
        </form>
      ) : (
        <>
          <div className="rw-row-between">
            <h4>{t("What the client asked")}</h4>
            {editable && <button type="button" className="btn btn-sm btn-ghost" onClick={() => { setNotes(ticket.special_requests); setEdit({ ...answers }); }}><PencilSimple />{t("Edit")}</button>}
          </div>
          <dl className="rw-answers">
            {fields.map((f) => (
              <div key={f.key} className={!answers[f.key] && f.required ? "missing" : ""}>
                <dt>{label(f)}</dt><dd dir="auto">{show(f) ?? <span className="muted">{f.required ? t("Missing") : "—"}</span>}</dd>
              </div>
            ))}
            {extra.map((k) => <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd dir="auto">{answers[k]}</dd></div>)}
          </dl>
          {ticket.special_requests && (
            <div className="rw-summary"><h4>{t("Summary and special requests")}</h4><p dir="auto">{ticket.special_requests}</p></div>
          )}
        </>
      )}
      {prefs.length > 0 && (
        <div className="rw-summary gx-prefs">
          <h4>{t("What this client likes")}</h4>
          <dl className="rw-answers">{prefs.map(([k, v]) => <div key={k}><dt>{t(PREFERENCE_LABEL[k] ?? k)}</dt><dd dir="auto">{v}</dd></div>)}</dl>
        </div>
      )}
      <AskClient ticket={ticket} onChange={onChange} />
    </div>
  );
}
