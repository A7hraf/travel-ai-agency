import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, patch } from "../api";
import AICheckCard from "../components/AICheckCard";
import { ErrorBox, Field, PageHeader } from "../components/ui";
import { useI18n } from "../lang";
import type { CompanySettings } from "../types";

function CopyRow({ value }: { value: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <div className="copy-row">
      <code>{value}</code>
      <button type="button" className="btn btn-sm" onClick={() => {
        navigator.clipboard?.writeText(value).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
      }}>{copied ? t("Copied") : t("Copy")}</button>
    </div>
  );
}

type Section = "ai" | "wa" | "company";

/** The editable fields of each card. Saving one card never resets unsaved edits in the others. */
const SECTION_FIELDS: Record<Section, (keyof CompanySettings)[]> = {
  ai: ["ai_agent_name", "ai_welcome_message", "ai_welcome_message_ar", "ai_instructions", "knowledge_base"],
  wa: ["whatsapp_phone_number_id", "whatsapp_display_number"],
  company: ["currency", "contact_email", "contact_phone"],
};

export default function Settings() {
  const { t } = useI18n();
  const [s, setS] = useState<CompanySettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [token, setToken] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [errors, setErrors] = useState<Partial<Record<Section, string | null>>>({});
  const [saved, setSaved] = useState<Partial<Record<Section, boolean>>>({});
  const [busy, setBusy] = useState<Section | null>(null);

  useEffect(() => { get<CompanySettings>("/api/company").then(setS).catch((e) => setLoadError(e.message)); }, []);
  if (!s) return <div className="loading">{loadError ?? t("Loading…")}</div>;

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
      // Take the saved card (and read-only values) from the server; keep the other cards as they are being edited.
      setS((prev) => {
        if (!prev) return updated;
        const next = { ...updated } as Record<string, unknown>;
        for (const other of Object.keys(SECTION_FIELDS) as Section[]) {
          if (other === section) continue;
          for (const k of SECTION_FIELDS[other]) next[k] = prev[k];
        }
        return next as unknown as CompanySettings;
      });
      setSaved((prev) => ({ ...prev, [section]: true }));
      if (section === "wa") {
        setToken("");
        setAppSecret("");
      }
    } catch (err) {
      setErrors((prev) => ({ ...prev, [section]: (err as Error).message }));
    } finally {
      setBusy(null);
    }
  };
  const button = (section: Section, label: string) => (
    <button className="btn btn-primary" disabled={busy !== null}>{busy === section ? t("Saving…") : label}</button>
  );

  const ownWebhook = s.whatsapp_webhook_path ? `${window.location.origin}${s.whatsapp_webhook_path}` : "";
  const storefront = `${window.location.origin}/c/${s.slug}`;

  return (
    <div className="narrow">
      <PageHeader title={t("AI agent & WhatsApp")} subtitle={t("One AI brain, your own persona, knowledge and WhatsApp channel.")} />

      <AICheckCard path="/api/company/ai-check" />

      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault(); save("ai", {
        ai_agent_name: s.ai_agent_name, ai_welcome_message: s.ai_welcome_message ?? "",
        ai_welcome_message_ar: s.ai_welcome_message_ar ?? "",
        ai_instructions: s.ai_instructions, knowledge_base: s.knowledge_base }); }}>
        <h3>{t("AI travel consultant")}</h3>
        <div className="form-grid">
          <Field label={t("Agent name")} hint={t("How the AI introduces itself to customers.")}>
            <input value={s.ai_agent_name} onChange={(e) => set("ai_agent_name", e.target.value)} required maxLength={80} dir="auto" />
          </Field>
          <Field label={t("Your customer page (share this link)")}>
            <a href={storefront} target="_blank" rel="noreferrer" className="link-box" dir="ltr">{storefront} ↗</a>
          </Field>
        </div>
        <div className="form-grid">
          <Field label={t("Welcome message (English)")} hint={t("Empty = default greeting.")}>
            <textarea rows={2} maxLength={1000} dir="auto" value={s.ai_welcome_message ?? ""} onChange={(e) => set("ai_welcome_message", e.target.value)} />
          </Field>
          <Field label="رسالة الترحيب (عربي)" hint={t("Empty = default Arabic greeting.")}>
            <textarea rows={2} maxLength={1000} dir="rtl" value={s.ai_welcome_message_ar ?? ""} onChange={(e) => set("ai_welcome_message_ar", e.target.value)} />
          </Field>
        </div>
        <Field label={t("Knowledge & policies")} hint={t("Payment methods, deposit, cancellation, visas, office hours… The AI uses this to answer and never contradicts it. Arabic or English.")}>
          <textarea rows={8} maxLength={30000} dir="auto" value={s.knowledge_base} onChange={(e) => set("knowledge_base", e.target.value)} />
        </Field>
        <Field label={t("Extra instructions")} hint={t("Style and selling rules, e.g. \"Always suggest travel insurance\". For question-and-answer teaching use AI training.")}>
          <textarea rows={4} maxLength={8000} dir="auto" value={s.ai_instructions} onChange={(e) => set("ai_instructions", e.target.value)} />
        </Field>
        <ErrorBox error={errors.ai ?? null} />
        {saved.ai && <div className="ok-box">{t("AI settings saved. They apply to the next customer message.")}</div>}
        <div className="row-gap">
          {button("ai", t("Save AI settings"))}
          <Link to="/app/training" className="btn">{t("AI training (questions & answers)")} →</Link>
        </div>
      </form>

      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault();
        const body: Record<string, unknown> = {
          whatsapp_phone_number_id: s.whatsapp_phone_number_id ?? "",
          whatsapp_display_number: s.whatsapp_display_number ?? "" };
        if (token) body.whatsapp_access_token = token;
        if (appSecret) body.whatsapp_app_secret = appSecret;
        save("wa", body); }}>
        <h3>{t("Your WhatsApp channel")}</h3>
        <p className="muted small">
          {t("Each company has its own WhatsApp Business number and its own connection. Customers who message your number talk to your AI agent only; their chats are visible only to your team.")}
        </p>
        <div className="form-grid">
          <Field label={t("Phone number ID")} hint={t("Meta App → WhatsApp → API Setup → Phone number ID")}>
            <input dir="ltr" maxLength={64} value={s.whatsapp_phone_number_id ?? ""} onChange={(e) => set("whatsapp_phone_number_id", e.target.value)} />
          </Field>
          <Field label={t("Public WhatsApp number")} hint={t("Shown on your customer page, e.g. {example}", { example: "+968 9123 4567" })}>
            <input dir="ltr" maxLength={50} value={s.whatsapp_display_number ?? ""} onChange={(e) => set("whatsapp_display_number", e.target.value)} />
          </Field>
          <Field label={t("Access token")} hint={s.whatsapp_token_set ? t("Saved (encrypted). Type a new one to replace it.") : t("Permanent token of a Meta system user with {permission}.", { permission: "whatsapp_business_messaging" })}>
            <input type="password" value={token} placeholder={s.whatsapp_token_set ? `•••••••• (${t("saved")})` : ""} onChange={(e) => { setToken(e.target.value); setSaved((p) => ({ ...p, wa: false })); }} autoComplete="new-password" dir="ltr" />
          </Field>
          <Field label={t("App secret")} hint={s.whatsapp_app_secret_set ? t("Saved (encrypted). Type a new one to replace it.") : t("Meta App → App settings → Basic → App secret.")}>
            <input type="password" value={appSecret} placeholder={s.whatsapp_app_secret_set ? `•••••••• (${t("saved")})` : ""} onChange={(e) => { setAppSecret(e.target.value); setSaved((p) => ({ ...p, wa: false })); }} autoComplete="new-password" dir="ltr" />
          </Field>
        </div>
        {ownWebhook && (
          <div className="info-box small">
            <div><strong>{t("In your Meta app → WhatsApp → Configuration → Webhook, enter:")}</strong></div>
            <div>{t("Callback URL:")}</div><CopyRow value={ownWebhook} />
            <div>{t("Verify token:")}</div><CopyRow value={s.whatsapp_verify_token ?? ""} />
            <div>{t("Then subscribe to the {field} field. Keep these private.", { field: "messages" })}</div>
          </div>
        )}
        <ErrorBox error={errors.wa ?? null} />
        {saved.wa && <div className="ok-box">{t("WhatsApp settings saved.")}</div>}
        <div className="row-gap">
          {button("wa", t("Save WhatsApp settings"))}
          {s.whatsapp_token_set && (
            <button type="button" className="btn btn-ghost" disabled={busy !== null} onClick={() => {
              if (confirm(t("Remove the WhatsApp access token? WhatsApp messages stop working until a new one is saved."))) save("wa", { whatsapp_access_token: "" });
            }}>{t("Remove token")}</button>
          )}
        </div>
      </form>

      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault(); save("company", {
        currency: s.currency, contact_email: s.contact_email || null, contact_phone: s.contact_phone ?? "" }); }}>
        <h3>{t("Company")}</h3>
        <div className="form-grid">
          <Field label={t("Default currency")} hint={t("OMR = Omani rial (3 decimals).")}><input maxLength={3} pattern="[A-Za-z]{3}" title={t("3 English letters, for example OMR")} dir="ltr" value={s.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} required /></Field>
          <Field label={t("Contact email")}><input type="email" dir="ltr" value={s.contact_email ?? ""} onChange={(e) => set("contact_email", e.target.value)} /></Field>
          <Field label={t("Contact phone")}><input dir="ltr" maxLength={50} value={s.contact_phone ?? ""} onChange={(e) => set("contact_phone", e.target.value)} /></Field>
          <Field label={t("Account limit")}><input value={t("{n} accounts (set by the platform admin)", { n: s.max_users })} disabled /></Field>
        </div>
        <ErrorBox error={errors.company ?? null} />
        {saved.company && <div className="ok-box">{t("Saved.")}</div>}
        {button("company", t("Save"))}
      </form>
    </div>
  );
}
