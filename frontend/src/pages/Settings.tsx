import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, patch } from "../api";
import AICheckCard from "../components/AICheckCard";
import { ErrorBox, Field, PageHeader } from "../components/ui";
import type { CompanySettings } from "../types";

function CopyRow({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="copy-row">
      <code>{value}</code>
      <button type="button" className="btn btn-sm" onClick={() => {
        navigator.clipboard?.writeText(value).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
      }}>{copied ? "Copied" : "Copy"}</button>
    </div>
  );
}

export default function Settings() {
  const [s, setS] = useState<CompanySettings | null>(null);
  const [token, setToken] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => { get<CompanySettings>("/api/company").then(setS).catch((e) => setError(e.message)); }, []);
  if (!s) return <div className="loading">{error ?? "Loading…"}</div>;

  const set = <K extends keyof CompanySettings>(k: K, v: CompanySettings[K]) => setS({ ...s, [k]: v });

  const save = async (section: string, body: Record<string, unknown>) => {
    setError(null);
    setSaved(null);
    try {
      setS(await patch<CompanySettings>("/api/company", body));
      setSaved(section);
      setToken("");
      setAppSecret("");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const ownWebhook = s.whatsapp_webhook_path ? `${window.location.origin}${s.whatsapp_webhook_path}` : "";
  const storefront = `${window.location.origin}/c/${s.slug}`;

  return (
    <div className="narrow">
      <PageHeader title="AI agent & WhatsApp" subtitle="One AI brain, your own persona, knowledge and WhatsApp channel." />
      <ErrorBox error={error} />

      <AICheckCard path="/api/company/ai-check" />

      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault(); save("ai", {
        ai_agent_name: s.ai_agent_name, ai_welcome_message: s.ai_welcome_message ?? "",
        ai_welcome_message_ar: s.ai_welcome_message_ar ?? "",
        ai_instructions: s.ai_instructions, knowledge_base: s.knowledge_base }); }}>
        <h3>AI travel consultant</h3>
        <div className="form-grid">
          <Field label="Agent name" hint="How the AI introduces itself to customers.">
            <input value={s.ai_agent_name} onChange={(e) => set("ai_agent_name", e.target.value)} required />
          </Field>
          <Field label="Your customer page (share this link)">
            <a href={storefront} target="_blank" rel="noreferrer" className="link-box">{storefront} ↗</a>
          </Field>
        </div>
        <div className="form-grid">
          <Field label="Welcome message (English)" hint="Empty = default greeting.">
            <textarea rows={2} value={s.ai_welcome_message ?? ""} onChange={(e) => set("ai_welcome_message", e.target.value)} />
          </Field>
          <Field label="رسالة الترحيب (عربي)" hint="Empty = default Arabic greeting.">
            <textarea rows={2} dir="rtl" value={s.ai_welcome_message_ar ?? ""} onChange={(e) => set("ai_welcome_message_ar", e.target.value)} />
          </Field>
        </div>
        <Field label="Knowledge & policies" hint="Payment methods, deposit, cancellation, visas, office hours… The AI uses this to answer and never contradicts it. Arabic or English.">
          <textarea rows={8} dir="auto" value={s.knowledge_base} onChange={(e) => set("knowledge_base", e.target.value)} />
        </Field>
        <Field label="Extra instructions" hint={"Style and selling rules, e.g. \"Always suggest travel insurance\". For question-and-answer teaching use AI training."}>
          <textarea rows={4} dir="auto" value={s.ai_instructions} onChange={(e) => set("ai_instructions", e.target.value)} />
        </Field>
        {saved === "ai" && <div className="ok-box">AI settings saved. They apply to the next customer message.</div>}
        <div className="row-gap">
          <button className="btn btn-primary">Save AI settings</button>
          <Link to="/app/training" className="btn">AI training (questions &amp; answers) →</Link>
        </div>
      </form>

      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault();
        const body: Record<string, unknown> = {
          whatsapp_phone_number_id: s.whatsapp_phone_number_id ?? "",
          whatsapp_display_number: s.whatsapp_display_number ?? "" };
        if (token) body.whatsapp_access_token = token;
        if (appSecret) body.whatsapp_app_secret = appSecret;
        save("wa", body); }}>
        <h3>Your WhatsApp channel</h3>
        <p className="muted small">
          Each company has its own WhatsApp Business number and its own connection. Customers who message your number
          talk to your AI agent only; their chats are visible only to your team.
        </p>
        <div className="form-grid">
          <Field label="Phone number ID" hint="Meta App → WhatsApp → API Setup → Phone number ID">
            <input value={s.whatsapp_phone_number_id ?? ""} onChange={(e) => set("whatsapp_phone_number_id", e.target.value)} />
          </Field>
          <Field label="Public WhatsApp number" hint="Shown on your customer page, e.g. +968 9123 4567">
            <input value={s.whatsapp_display_number ?? ""} onChange={(e) => set("whatsapp_display_number", e.target.value)} />
          </Field>
          <Field label="Access token" hint={s.whatsapp_token_set ? "Saved (encrypted). Type a new one to replace it." : "Permanent token of a Meta system user with whatsapp_business_messaging."}>
            <input type="password" value={token} placeholder={s.whatsapp_token_set ? "•••••••• (saved)" : ""} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
          </Field>
          <Field label="App secret" hint={s.whatsapp_app_secret_set ? "Saved (encrypted). Type a new one to replace it." : "Meta App → App settings → Basic → App secret."}>
            <input type="password" value={appSecret} placeholder={s.whatsapp_app_secret_set ? "•••••••• (saved)" : ""} onChange={(e) => setAppSecret(e.target.value)} autoComplete="off" />
          </Field>
        </div>
        {ownWebhook && (
          <div className="info-box small">
            <div><strong>In your Meta app → WhatsApp → Configuration → Webhook, enter:</strong></div>
            <div>Callback URL:</div><CopyRow value={ownWebhook} />
            <div>Verify token:</div><CopyRow value={s.whatsapp_verify_token ?? ""} />
            <div>Then subscribe to the <code>messages</code> field. Keep these private.</div>
          </div>
        )}
        {saved === "wa" && <div className="ok-box">WhatsApp settings saved.</div>}
        <div className="row-gap">
          <button className="btn btn-primary">Save WhatsApp settings</button>
          {s.whatsapp_token_set && (
            <button type="button" className="btn btn-ghost" onClick={() => save("wa", { whatsapp_access_token: "" })}>Remove token</button>
          )}
        </div>
      </form>

      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault(); save("company", {
        currency: s.currency, contact_email: s.contact_email || null, contact_phone: s.contact_phone ?? "" }); }}>
        <h3>Company</h3>
        <div className="form-grid">
          <Field label="Default currency" hint="OMR = Omani rial (3 decimals)."><input maxLength={3} value={s.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></Field>
          <Field label="Contact email"><input type="email" value={s.contact_email ?? ""} onChange={(e) => set("contact_email", e.target.value)} /></Field>
          <Field label="Contact phone"><input value={s.contact_phone ?? ""} onChange={(e) => set("contact_phone", e.target.value)} /></Field>
          <Field label="Account limit"><input value={`${s.max_users} accounts (set by the platform admin)`} disabled /></Field>
        </div>
        {saved === "company" && <div className="ok-box">Saved.</div>}
        <button className="btn btn-primary">Save</button>
      </form>
    </div>
  );
}
