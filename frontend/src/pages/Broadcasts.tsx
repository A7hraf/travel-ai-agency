import { FormEvent, useEffect, useState } from "react";
import { get, post } from "../api";
import { useAuth } from "../auth";
import { PageTitle } from "../components/admin/AdminUI";
import { useLevelName } from "../components/members/MemberBadge";
import { Megaphone, PaperPlaneRight, Star, UsersThree } from "../components/Icon";
import { ConfirmSheet } from "../components/staff/Sheet";
import { ErrorBox, Field } from "../components/ui";
import { useI18n } from "../lang";
import type { MemberLevel, Service } from "../types";
import { dateTime } from "../util";

interface Audience { member_levels: string[]; tag: string | null; service_id: number | null; travelled_within_days: number | null; booked: boolean | null }
interface Sent { id: number; kind: string; text_en: string; text_ar: string; sent: number; skipped: number; created_by: string; created_at: string }

/** One message to a group of clients on WhatsApp (an offer, news), or a feedback request about their last trip. */
export default function Broadcasts() {
  const { t, lang } = useI18n();
  const levelName = useLevelName();
  const { user } = useAuth();
  const levels = Object.keys(user?.company?.member_levels ?? {}) as MemberLevel[];
  const [kind, setKind] = useState<"message" | "feedback">("message");
  const [textEn, setTextEn] = useState("");
  const [textAr, setTextAr] = useState("");
  const [aud, setAud] = useState<Audience>({ member_levels: [], tag: null, service_id: null, travelled_within_days: null, booked: null });
  const [preview, setPreview] = useState<{ count: number; sample: string[] } | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [history, setHistory] = useState<Sent[]>([]);
  const [confirm, setConfirm] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadHistory = () => get<Sent[]>("/api/broadcasts").then(setHistory).catch(() => {});
  useEffect(() => { get<Service[]>("/api/services").then(setServices).catch(() => {}); loadHistory(); }, []);
  useEffect(() => {
    setPreview(null);
    const id = window.setTimeout(() => post<{ count: number; sample: string[] }>("/api/broadcasts/preview", aud).then(setPreview).catch((e) => setError((e as Error).message)), 300);
    return () => window.clearTimeout(id);
  }, [aud]);
  const set = (patch: Partial<Audience>) => setAud({ ...aud, ...patch });
  const send = async () => {
    setError(null); setDone(null);
    try {
      const r = await post<{ sent: number; skipped: number }>("/api/broadcasts", { kind, text_en: textEn, text_ar: textAr, audience: aud });
      setDone(t("Sent to {n} clients ({s} could not be reached on WhatsApp).", { n: r.sent, s: r.skipped }));
      setTextEn(""); setTextAr(""); loadHistory();
    } catch (e) { setError((e as Error).message); }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); setConfirm(true); };

  return (
    <div className="narrow gx-narrow">
      <PageTitle kicker={t("Clients")} title={t("Broadcasts")}
        subtitle={t("Send an offer, news or a feedback request to a group of your clients on WhatsApp, each in their language.")} />
      <form className="gx-card" onSubmit={submit}>
        <div className="gx-ask-kinds" role="radiogroup" aria-label={t("What to send")}>
          <button type="button" role="radio" aria-checked={kind === "message"} className={`chip-btn ${kind === "message" ? "active" : ""}`} onClick={() => setKind("message")}><Megaphone />{t("A message")}</button>
          <button type="button" role="radio" aria-checked={kind === "feedback"} className={`chip-btn ${kind === "feedback" ? "active" : ""}`} onClick={() => setKind("feedback")}><Star />{t("Ask about their last trip")}</button>
        </div>
        <p className="muted small">{kind === "feedback"
          ? t("Each client is asked to rate their last trip; the AI saves the answers in Trip feedback. Add a few words if you like.")
          : t("Write it in both languages: each client gets the one they chat in.")}</p>
        <div className="gx-grid-2">
          <Field label={t("Message (English)")}><textarea rows={4} dir="ltr" maxLength={1000} value={textEn} onChange={(e) => setTextEn(e.target.value)} /></Field>
          <Field label={t("Message (Arabic)")}><textarea rows={4} dir="rtl" maxLength={1000} value={textAr} onChange={(e) => setTextAr(e.target.value)} /></Field>
        </div>
        <div className="gx-section-label"><UsersThree /> {t("Who receives it")}</div>
        <div className="gx-ask-kinds">
          {levels.map((k) => (
            <label key={k} className="gx-feat-check"><input type="checkbox" checked={aud.member_levels.includes(k)}
              onChange={(e) => set({ member_levels: e.target.checked ? [...aud.member_levels, k] : aud.member_levels.filter((x) => x !== k) })} /> {levelName(k)?.name ?? k}</label>
          ))}
        </div>
        <div className="gx-grid-2">
          <Field label={t("Label")}><input value={aud.tag ?? ""} maxLength={40} dir="auto" onChange={(e) => set({ tag: e.target.value || null })} placeholder={t("For example VIP, family")} /></Field>
          <Field label={t("Asked for this service")}>
            <select value={aud.service_id ?? ""} onChange={(e) => set({ service_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">{t("Any service")}</option>
              {services.map((s) => <option key={s.id} value={s.id}>{lang === "ar" ? s.name_ar : s.name_en}</option>)}
            </select>
          </Field>
          <Field label={t("Booked with you")}>
            <select value={aud.booked == null ? "" : String(aud.booked)} onChange={(e) => set({ booked: e.target.value === "" ? null : e.target.value === "true" })}>
              <option value="">{t("Anyone")}</option><option value="true">{t("Booked at least once")}</option><option value="false">{t("Never booked")}</option>
            </select>
          </Field>
          <Field label={t("Came back from a trip")}>
            <select value={aud.travelled_within_days ?? ""} onChange={(e) => set({ travelled_within_days: e.target.value ? Number(e.target.value) : null })}>
              <option value="">{t("Any time")}</option><option value="14">{t("In the last 2 weeks")}</option>
              <option value="90">{t("In the last 3 months")}</option><option value="365">{t("In the last year")}</option>
            </select>
          </Field>
        </div>
        {preview && <p className="gx-card-note"><strong>{t("{n} clients", { n: preview.count })}</strong>{preview.sample.length > 0 && ` · ${preview.sample.join(", ")}…`}</p>}
        <p className="muted small">{t("Clients who haven't written in the last 24 hours get it only through your approved WhatsApp template (AI & channels).")}</p>
        <ErrorBox error={error} />
        {done && <div className="ok-box gx-notice" role="status">{done}</div>}
        <div className="gx-form-actions">
          <button className="btn btn-primary" disabled={!preview?.count || (kind === "message" && !textEn.trim() && !textAr.trim())}>
            <PaperPlaneRight className="flip" />{t("Send to {n} clients", { n: preview?.count ?? 0 })}</button>
        </div>
      </form>

      {history.length > 0 && (
        <section className="gx-card">
          <h2 className="gx-card-title">{t("Sent before")}</h2>
          <ul className="gx-ask-list">
            {history.map((b) => (
              <li key={b.id} className="done">
                {b.kind === "feedback" ? <Star /> : <Megaphone />}
                <div>
                  <strong dir="auto">{(lang === "ar" ? b.text_ar || b.text_en : b.text_en || b.text_ar) || t("Ask about their last trip")}</strong>
                  <small className="muted">{t("{n} sent · {s} not reached", { n: b.sent, s: b.skipped })} · <bdi>{b.created_by}</bdi> · {dateTime(b.created_at)}</small>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {confirm && <ConfirmSheet req={{ title: t("Send to {n} clients?", { n: preview?.count ?? 0 }), text: t("This can't be undone."), okLabel: t("Send"), tone: "brand", onConfirm: send }} onClose={() => setConfirm(false)} />}
    </div>
  );
}
