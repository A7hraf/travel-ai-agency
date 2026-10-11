import { FormEvent, useEffect, useState } from "react";
import { get, patch } from "../api";
import { ErrorBox, Field, PageHeader } from "../components/ui";
import type { CompanySettings } from "../types";

export default function Settings() {
  const [s, setS] = useState<CompanySettings | null>(null);
  const [token, setToken] = useState("");
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
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const webhookUrl = `${window.location.origin}/api/webhooks/whatsapp`;
  const storefront = `${window.location.origin}/c/${s.slug}`;

  return (
    <div className="narrow">
      <PageHeader title="AI agent & WhatsApp" subtitle="One AI brain, your own persona, knowledge and WhatsApp number." />
      <ErrorBox error={error} />

      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault(); save("ai", {
        ai_agent_name: s.ai_agent_name, ai_welcome_message: s.ai_welcome_message ?? "",
        ai_instructions: s.ai_instructions, knowledge_base: s.knowledge_base }); }}>
        <h3>AI travel consultant</h3>
        <div className="form-grid">
          <Field label="Agent name" hint="How the AI introduces itself to customers.">
            <input value={s.ai_agent_name} onChange={(e) => set("ai_agent_name", e.target.value)} required />
          </Field>
          <Field label="Customer page">
            <a href={storefront} target="_blank" rel="noreferrer" className="link-box">{storefront} ↗</a>
          </Field>
        </div>
        <Field label="Welcome message" hint="First message on the website chat. Empty = default greeting.">
          <textarea rows={2} value={s.ai_welcome_message ?? ""} onChange={(e) => set("ai_welcome_message", e.target.value)} />
        </Field>
        <Field label="Knowledge & policies" hint="Payment methods, deposit, cancellation, visas, office hours… The AI uses this to answer and never contradicts it.">
          <textarea rows={8} value={s.knowledge_base} onChange={(e) => set("knowledge_base", e.target.value)} />
        </Field>
        <Field label="Extra instructions" hint={"Style and selling rules, e.g. \"Always reply in Gulf Arabic\", \"Suggest travel insurance\"."}>
          <textarea rows={4} value={s.ai_instructions} onChange={(e) => set("ai_instructions", e.target.value)} />
        </Field>
        {saved === "ai" && <div className="ok-box">AI settings saved. They apply to the next customer message.</div>}
        <button className="btn btn-primary">Save AI settings</button>
      </form>

      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault();
        const body: Record<string, unknown> = {
          whatsapp_phone_number_id: s.whatsapp_phone_number_id ?? "",
          whatsapp_display_number: s.whatsapp_display_number ?? "" };
        if (token) body.whatsapp_access_token = token;
        save("wa", body); }}>
        <h3>WhatsApp Business</h3>
        <p className="muted small">
          Connect your WhatsApp Business number from Meta (WhatsApp Cloud API). Customers who message this number talk
          to your AI agent, and your team can reply from the Conversations page.
        </p>
        <div className="form-grid">
          <Field label="Phone number ID" hint="Meta App → WhatsApp → API Setup → Phone number ID">
            <input value={s.whatsapp_phone_number_id ?? ""} onChange={(e) => set("whatsapp_phone_number_id", e.target.value)} />
          </Field>
          <Field label="Public WhatsApp number" hint="Shown on your customer page, e.g. +971 50 123 4567">
            <input value={s.whatsapp_display_number ?? ""} onChange={(e) => set("whatsapp_display_number", e.target.value)} />
          </Field>
        </div>
        <Field label="Access token" hint={s.whatsapp_token_set ? "A token is saved. Type a new one to replace it." : "Permanent token of a Meta system user with whatsapp_business_messaging permission."}>
          <input type="password" value={token} placeholder={s.whatsapp_token_set ? "•••••••• (saved)" : ""} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
        </Field>
        <div className="info-box small">
          <div><strong>Webhook URL:</strong> <code>{webhookUrl}</code></div>
          <div>Subscribe the webhook to the <code>messages</code> field. The verify token is set by your platform admin.</div>
        </div>
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
          <Field label="Default currency"><input maxLength={3} value={s.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></Field>
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
