import { FormEvent, useState } from "react";
import { post } from "../../api";
import { useI18n } from "../../lang";
import type { Service, Ticket } from "../../types";
import { X } from "../Icon";
import { Sheet } from "../staff/Sheet";
import { ErrorBox } from "../ui";
import { FieldInput } from "./RequestDetails";

const CONTACT = ["full_name", "phone", "email"];

/** A request the team takes outside the chat (a call, a walk-in, an email): a tailor-made trip, flights, a visa… */
export default function NewRequest({ services, onClose, onCreated }: { services: Service[]; onClose: () => void; onCreated: (t: Ticket) => void }) {
  const { t, lang } = useI18n();
  const usable = services.filter((s) => s.is_active && s.pricing !== "packages");
  const [serviceId, setServiceId] = useState<number>(usable.find((s) => s.key === "custom_trip")?.id ?? usable[0]?.id ?? 0);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const service = usable.find((s) => s.id === serviceId);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const clean = Object.fromEntries(Object.entries(answers).filter(([, v]) => v.trim()));
      onCreated(await post<Ticket>("/api/tickets", { service_id: serviceId, name: name || null, phone: phone || null, email: email || null, answers: clean, summary }));
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Sheet label={t("New request")} onClose={onClose} className="rw-new">
      <form onSubmit={submit} className="rw-new-form">
        <div className="rw-row-between">
          <h2>{t("New request")}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label={t("Close")}><X /></button>
        </div>
        <p className="muted small">{t("For a client who called, came to the office or wrote by email. Save what you know now; the rest can be added later.")}</p>
        {usable.length === 0 ? <p className="muted">{t("Add a service first (Services page).")}</p> : (
          <>
            <label className="rw-lbl"><span>{t("Service")}</span>
              <select value={serviceId} onChange={(e) => { setServiceId(Number(e.target.value)); setAnswers({}); }}>
                {usable.map((s) => <option key={s.id} value={s.id}>{lang === "ar" ? s.name_ar : s.name_en}</option>)}
              </select>
            </label>
            <div className="rw-edit-grid">
              <label><span>{t("Client name")}</span><input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} dir="auto" required={!phone} /></label>
              <label><span>{t("WhatsApp number")}</span><input value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={30} dir="ltr" inputMode="tel" placeholder="+968 9123 4567" /></label>
              <label><span>{t("Email")}</span><input value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200} dir="ltr" type="email" /></label>
              {(service?.fields ?? []).filter((f) => !CONTACT.includes(f.key)).map((f) => (
                <label key={f.key} className={f.type === "long_text" ? "wide" : ""}>
                  <span>{lang === "ar" ? f.label_ar : f.label_en}{f.required && " *"}</span>
                  <FieldInput f={f} value={answers[f.key] ?? ""} onChange={(v) => setAnswers({ ...answers, [f.key]: v })} />
                </label>
              ))}
              <label className="wide"><span>{t("Summary and special requests")}</span>
                <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={4000} dir="auto"
                  placeholder={t("e.g. Honeymoon, likes nature and quiet 5-star hotels, halal food")} /></label>
            </div>
            <p className="muted small">{t("With the WhatsApp number, the client gets updates there and can follow the request on their trips page.")}</p>
          </>
        )}
        <ErrorBox error={error} />
        <div className="rw-row-end">
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy || !service}>{busy ? t("Saving…") : t("Create the request")}</button>
        </div>
      </form>
    </Sheet>
  );
}
