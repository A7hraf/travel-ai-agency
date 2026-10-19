import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, patch } from "../api";
import AICheckCard from "../components/AICheckCard";
import { PageTitle } from "../components/admin/AdminUI";
import WhatsAppConnect from "../components/ai/WhatsAppConnect";
import { ArrowSquareOut, Buildings, GraduationCap, Robot, Sparkle } from "../components/Icon";
import { ErrorBox, Field } from "../components/ui";
import { useI18n } from "../lang";
import type { CompanySettings } from "../types";

type Section = "company";

/** The editable fields of each card. Saving one card never resets unsaved edits in the others. */
const SECTION_FIELDS: Record<Section, (keyof CompanySettings)[]> = {
  company: ["currency", "contact_email", "contact_phone"],
};

export default function Settings() {
  const { t } = useI18n();
  const [s, setS] = useState<CompanySettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Partial<Record<Section, string | null>>>({});
  const [saved, setSaved] = useState<Partial<Record<Section, boolean>>>({});
  const [busy, setBusy] = useState<Section | null>(null);

  useEffect(() => { get<CompanySettings>("/api/company").then(setS).catch((e) => setLoadError(e.message)); }, []);
  if (!s) return loadError ? <div className="error-box">{loadError}</div> : <div className="skeleton" style={{ height: 320, borderRadius: 24 }} />;

  const set = <K extends keyof CompanySettings>(k: K, v: CompanySettings[K]) => {
    const section = (Object.keys(SECTION_FIELDS) as Section[]).find((x) => SECTION_FIELDS[x].includes(k));
    if (section) setSaved((prev) => ({ ...prev, [section]: false }));
    setS({ ...s, [k]: v });
  };

  const save = async (section: Section, body: Record<string, unknown>) => {
    if (busy) return;
    setErrors((prev) => ({ ...prev, [section]: null }));
    setSaved((prev) => ({ ...prev, [section]: false }));
    setBusy(section);
    try {
      const updated = await patch<CompanySettings>("/api/company", body);
      setS(updated);
      setSaved((prev) => ({ ...prev, [section]: true }));
    } catch (err) {
      setErrors((prev) => ({ ...prev, [section]: (err as Error).message }));
    } finally {
      setBusy(null);
    }
  };
  const button = (section: Section, label: string) => (
    <button className="btn btn-primary" disabled={busy !== null} aria-busy={busy === section}>{busy === section ? t("Saving…") : label}</button>
  );

  const storefront = `${window.location.origin}/c/${s.slug}`;

  return (
    <div className="narrow ad-narrow">
      <PageTitle kicker={t("Agency workspace")} title={t("AI & WhatsApp")} subtitle={t("One AI brain, your own persona, knowledge and WhatsApp channel.")} />

      <AICheckCard path="/api/company/ai-check" />

      <section className="ad-card">
        <h2 className="ad-card-title"><span className="ad-card-icon"><Robot /></span>{t("AI travel consultant")}</h2>
        <p className="ad-card-note">{t("{name} answers your customers on your page and on WhatsApp. Its knowledge, personality, welcome messages and trained answers are now all in AI training, with a test chat to try it.", { name: s.ai_agent_name })}</p>
        <div className="ad-grid-2">
          <Field label={t("Your customer page (share this link)")}>
            <a href={storefront} target="_blank" rel="noreferrer" className="link-box" dir="ltr">{storefront} <ArrowSquareOut /></a>
          </Field>
        </div>
        <div className="ad-form-actions">
          <Link to="/app/training" className="btn btn-primary"><GraduationCap />{t("Train your AI")}</Link>
          <Link to="/app/training?tab=knowledge" className="btn btn-ghost">{t("Company knowledge")}</Link>
          <Link to="/app/training?tab=try" className="btn btn-ghost"><Sparkle weight="fill" />{t("Try your AI")}</Link>
        </div>
      </section>

      <WhatsAppConnect variant="company" base="/api/company/whatsapp" />

      <form className="ad-card" onSubmit={(e: FormEvent) => { e.preventDefault(); save("company", {
        currency: s.currency, contact_email: s.contact_email || null, contact_phone: s.contact_phone ?? "" }); }}>
        <h2 className="ad-card-title"><span className="ad-card-icon"><Buildings /></span>{t("Company")}</h2>
        <div className="ad-grid-2">
          <Field label={t("Default currency")} hint={t("OMR = Omani rial (3 decimals).")}><input maxLength={3} pattern="[A-Za-z]{3}" title={t("3 English letters, for example OMR")} dir="ltr" value={s.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} required /></Field>
          <Field label={t("Contact email")}><input type="email" dir="ltr" value={s.contact_email ?? ""} onChange={(e) => set("contact_email", e.target.value)} /></Field>
          <Field label={t("Contact phone")}><input dir="ltr" maxLength={50} value={s.contact_phone ?? ""} onChange={(e) => set("contact_phone", e.target.value)} /></Field>
          <Field label={t("Account limit")}><input value={t("{n} accounts (set by the platform admin)", { n: s.max_users })} disabled /></Field>
        </div>
        <ErrorBox error={errors.company ?? null} />
        {saved.company && <div className="ok-box ad-notice" role="status">{t("Saved.")}</div>}
        <div className="ad-form-actions">{button("company", t("Save"))}</div>
      </form>
    </div>
  );
}
