import { FormEvent, useEffect, useState } from "react";
import { get, post, put } from "../../api";
import { ConfirmSheet, PageTitle, Switch } from "../../components/admin/AdminUI";
import {
  ArrowsClockwise, Brain, Check, CheckCircle, Copy, Info, Key, Lightning, WarningCircle, WhatsappLogo, XCircle,
} from "../../components/Icon";
import { ErrorBox, Field } from "../../components/ui";
import { trServer, useI18n } from "../../lang";
import type { AICheck, PlatformSettings as Settings, PlatformSettingValue } from "../../types";
import { dateTime } from "../../util";

const GROQ_URL = "https://api.groq.com/openai/v1";
const OLLAMA_URL = "http://localhost:11434/v1";
type Preset = "groq" | "custom" | "ollama" | "demo";

const AI_TEXT_FIELDS = ["llm_base_url", "llm_model", "llm_fallback_models", "llm_reasoning_effort"] as const;
type AIText = (typeof AI_TEXT_FIELDS)[number];

function CopyRow({ value, label }: { value: string; label: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <div className="copy-row">
      <code dir="ltr" aria-label={label}>{value || "—"}</code>
      <button type="button" className={`btn btn-sm ${copied ? "btn-soft" : ""}`} disabled={!value} onClick={() => {
        navigator.clipboard?.writeText(value).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
      }}>{copied ? <><Check />{t("Copied")}</> : <><Copy />{t("Copy")}</>}</button>
      <span className="sr-only" aria-live="polite">{copied ? t("Copied") : ""}</span>
    </div>
  );
}

const str = (v: string | boolean | null | undefined) => (typeof v === "string" ? v : "");

/** "Saved here" / "From Render" / "Not set" under a field. */
function useSourceHint() {
  const { t } = useI18n();
  return (s: PlatformSettingValue | undefined, extra?: string) => {
    if (!s) return extra;
    let text: string;
    if (s.secret) {
      text = s.saved ? t("Saved here (encrypted). Type a new one to replace it.")
        : s.env_set ? t("Using the value from Render. Type one here to replace it.")
        : t("Not set yet.");
    } else if (s.saved) {
      text = s.env_set ? t("Saved here. Empty the field to use the Render value ({value}).", { value: String(s.env_value) })
        : t("Saved here.");
    } else {
      text = s.env_set ? t("Using the value from Render.") : t("Not set yet.");
    }
    return extra ? `${extra} ${text}` : text;
  };
}

function lastChange(group: Record<string, PlatformSettingValue>): PlatformSettingValue | null {
  return Object.values(group).filter((s) => s.updated_at)
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))[0] ?? null;
}

export default function PlatformSettings() {
  const { t } = useI18n();
  const hint = useSourceHint();
  const [data, setData] = useState<Settings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // AI form
  const [ai, setAi] = useState<Record<AIText, string>>({ llm_base_url: "", llm_model: "", llm_fallback_models: "", llm_reasoning_effort: "" });
  const [provider, setProvider] = useState<"openai_compatible" | "mock">("openai_compatible");
  const [apiKey, setApiKey] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiSaved, setAiSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [check, setCheck] = useState<AICheck | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);

  // WhatsApp form
  const [appSecret, setAppSecret] = useState("");
  const [waToken, setWaToken] = useState("");
  const [apiVersion, setApiVersion] = useState("");
  const [share, setShare] = useState(true);
  const [shareTouched, setShareTouched] = useState(false);
  const [waBusy, setWaBusy] = useState(false);
  const [waError, setWaError] = useState<string | null>(null);
  const [waSaved, setWaSaved] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<null | "regenerate" | "llm_api_key" | "whatsapp_app_secret" | "whatsapp_default_access_token">(null);

  const fill = (d: Settings) => {
    setData(d);
    setAi({
      llm_base_url: str(d.ai.llm_base_url?.value),
      llm_model: str(d.ai.llm_model?.value),
      llm_fallback_models: str(d.ai.llm_fallback_models?.value),
      llm_reasoning_effort: str(d.ai.llm_reasoning_effort?.value),
    });
    setProvider(d.ai.llm_provider?.effective === "mock" ? "mock" : "openai_compatible");
    setApiVersion(str(d.whatsapp.whatsapp_api_version?.value));
    setShare(d.whatsapp.whatsapp_share_default_token?.effective !== false);
    setShareTouched(false);
    setApiKey("");
    setAppSecret("");
    setWaToken("");
  };

  useEffect(() => {
    get<Settings>("/api/system/platform-settings").then(fill).catch((e) => setLoadError((e as Error).message));
  }, []);

  if (loadError) return <div className="narrow ad-narrow"><PageTitle kicker={t("Platform console")} title={t("Platform settings")} /><ErrorBox error={loadError} /></div>;
  if (!data) return <div className="narrow ad-narrow"><PageTitle kicker={t("Platform console")} title={t("Platform settings")} /><div className="skeleton" style={{ height: 320, borderRadius: 24 }} /></div>;

  const A = data.ai;
  const W = data.whatsapp;
  const effectiveUrl = ai.llm_base_url || str(A.llm_base_url?.effective);
  const preset: Preset = provider === "mock" ? "demo"
    : effectiveUrl.includes("groq.com") ? "groq"
    : /localhost:11434|127\.0\.0\.1:11434|ollama/i.test(effectiveUrl) ? "ollama" : "custom";

  const choosePreset = (p: Preset) => {
    setAiSaved(false);
    if (p === "demo") { setProvider("mock"); return; }
    setProvider("openai_compatible");
    if (p === "groq") setAi((x) => ({ ...x, llm_base_url: GROQ_URL }));
    if (p === "ollama") setAi((x) => ({ ...x, llm_base_url: OLLAMA_URL }));
    if (p === "custom" && (preset === "groq" || preset === "ollama")) setAi((x) => ({ ...x, llm_base_url: "" }));
  };
  const setAiField = (k: AIText, v: string) => { setAi((x) => ({ ...x, [k]: v })); setAiSaved(false); };

  const aiBody = () => {
    const body: Record<string, string | null> = { ...ai };
    // Only saved when it differs from the Render value, so Render stays in charge otherwise.
    body.llm_provider = provider === (A.llm_provider?.env_value ?? "openai_compatible") && !A.llm_provider?.saved ? null : provider;
    if (apiKey.trim()) body.llm_api_key = apiKey.trim();
    return body;
  };

  const saveAI = async (e?: FormEvent, extra?: Record<string, string>) => {
    e?.preventDefault();
    setAiBusy(true); setAiError(null); setAiSaved(false);
    try {
      fill(await put<Settings>("/api/system/platform-settings", { ai: { ...aiBody(), ...extra } }));
      setAiSaved(true);
    } catch (err) {
      setAiError((err as Error).message);
    } finally {
      setAiBusy(false);
    }
  };

  const testAI = async () => {
    setTesting(true); setCheckError(null); setCheck(null);
    try {
      const body: Record<string, string> = { ...ai, llm_provider: provider };
      if (apiKey.trim()) body.llm_api_key = apiKey.trim();
      setCheck(await post<AICheck>("/api/system/platform-settings/ai-check", body));
    } catch (err) {
      setCheckError((err as Error).message);
    } finally {
      setTesting(false);
    }
  };

  const saveWA = async (body: Record<string, unknown>, message: string) => {
    setWaBusy(true); setWaError(null); setWaSaved(null);
    try {
      fill(await put<Settings>("/api/system/platform-settings", { whatsapp: body }));
      setWaSaved(message);
    } catch (err) {
      setWaError((err as Error).message);
    } finally {
      setWaBusy(false);
    }
  };

  const submitWA = (e: FormEvent) => {
    e.preventDefault();
    const body: Record<string, unknown> = { whatsapp_api_version: apiVersion };
    if (appSecret.trim()) body.whatsapp_app_secret = appSecret.trim();
    if (waToken.trim()) body.whatsapp_default_access_token = waToken.trim();
    if (shareTouched) body.whatsapp_share_default_token = share;
    saveWA(body, t("WhatsApp settings saved."));
  };

  const regenerate = async () => {
    setWaBusy(true); setWaError(null); setWaSaved(null);
    try {
      await post("/api/system/platform-settings/whatsapp/verify-token");
      fill(await get<Settings>("/api/system/platform-settings"));
      setWaSaved(t("New verify token created. Enter it in your Meta app and press Verify and save."));
    } catch (err) {
      setWaError((err as Error).message);
    } finally {
      setWaBusy(false);
      setConfirm(null);
    }
  };

  const removeSecret = (key: "llm_api_key" | "whatsapp_app_secret" | "whatsapp_default_access_token") => {
    setConfirm(null);
    if (key === "llm_api_key") saveAI(undefined, { llm_api_key: "" });
    else saveWA({ [key]: "" }, t("Removed. The value from Render is used again, if there is one."));
  };

  const webhookUrl = window.location.origin + data.webhook_path;
  const verifyToken = str(W.whatsapp_verify_token?.effective);
  const waReady = !!W.whatsapp_app_secret?.effective_set;
  const tokenReady = !!W.whatsapp_default_access_token?.effective_set;
  const good = !!check && check.ok && check.uses_tools;
  const tone = !check ? "" : good ? "ok" : check.ok ? "warn" : "bad";
  const aiChange = lastChange(A);
  const waChange = lastChange(W);
  const changedLine = (s: PlatformSettingValue | null) => s && (
    <p className="ad-card-note">{t("Last changed {date} by {who}", { date: dateTime(s.updated_at), who: s.updated_by ?? "—" })}</p>
  );
  const placeholder = (s: PlatformSettingValue | undefined) => (s && !s.saved && s.env_set ? String(s.env_value) : "");
  const secretPlaceholder = (s: PlatformSettingValue | undefined) =>
    s?.saved ? `•••••••• (${t("saved")})` : s?.env_set ? `•••••••• (${t("from Render")})` : "";

  return (
    <div className="narrow ad-narrow">
      <PageTitle kicker={t("Platform console")} title={t("Platform settings")}
        subtitle={t("The AI brain and the shared WhatsApp connection used by every company.")} />

      <div className="info-box small" style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <Info size={20} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
        <span>{t("Values saved here are used instead of the Render environment variables. Leave a field empty to keep using the Render value. Secret keys are stored encrypted and are never shown again.")}</span>
      </div>

      {/* --- AI brain --- */}
      <form className={`ad-card ai-card ${tone}`} onSubmit={saveAI}>
        <h2 className="ad-card-title"><span className="ad-card-icon"><Brain /></span>{t("AI brain")}<span className="spacer" />
          {provider === "mock" ? <span className="ad-status warn">{t("Demo mode")}</span>
            : A.llm_api_key?.effective_set || preset === "ollama" ? <span className="ad-status on">{t("Configured")}</span>
            : <span className="ad-status off">{t("API key missing")}</span>}
        </h2>
        <p className="ad-card-note">{t("The AI model that answers customers for every company. Choose your provider, paste the API key, then press Test AI.")}</p>
        {changedLine(aiChange)}

        <div className="field">
          <span className="field-label" id="ai-provider-label">{t("AI provider")}</span>
          <div className="seg" role="group" aria-labelledby="ai-provider-label" style={{ flexWrap: "wrap" }}>
            {([["groq", "Groq"], ["custom", t("Other (OpenAI-compatible)")], ["ollama", "Ollama"], ["demo", t("Demo (no AI)")]] as [Preset, string][]).map(([p, label]) => (
              <button type="button" key={p} className={preset === p ? "active" : ""} aria-pressed={preset === p} onClick={() => choosePreset(p)}>{label}</button>
            ))}
          </div>
        </div>
        {provider === "mock" ? (
          <div className="info-box small">{t("Demo mode: a simple built-in helper lists your packages. No real AI is used. Choose a provider above to connect a real AI.")}</div>
        ) : (
          <>
            <div className="ad-grid-2">
              <Field label={t("Server address (base URL)")} hint={hint(A.llm_base_url, preset === "groq" ? t("Groq: {url}", { url: GROQ_URL }) : undefined)}>
                <input dir="ltr" maxLength={500} value={ai.llm_base_url} placeholder={placeholder(A.llm_base_url)} onChange={(e) => setAiField("llm_base_url", e.target.value)} />
              </Field>
              <Field label={t("API key")} hint={hint(A.llm_api_key, preset === "groq" ? t("From console.groq.com → API Keys.") : undefined)}>
                <input type="password" dir="ltr" autoComplete="new-password" maxLength={1000} value={apiKey} placeholder={secretPlaceholder(A.llm_api_key)}
                  onChange={(e) => { setApiKey(e.target.value); setAiSaved(false); }} />
              </Field>
              <Field label={t("Model")} hint={hint(A.llm_model, preset === "groq" ? t("For example {model}", { model: "openai/gpt-oss-120b" }) : undefined)}>
                <input dir="ltr" maxLength={200} value={ai.llm_model} placeholder={placeholder(A.llm_model)} onChange={(e) => setAiField("llm_model", e.target.value)} />
              </Field>
              <Field label={t("Backup models")} hint={hint(A.llm_fallback_models, t("Used when the main model is busy or retired. Separate with commas."))}>
                <input dir="ltr" maxLength={1000} value={ai.llm_fallback_models} placeholder={placeholder(A.llm_fallback_models)} onChange={(e) => setAiField("llm_fallback_models", e.target.value)} />
              </Field>
              <Field label={t("Reasoning effort")} hint={hint(A.llm_reasoning_effort, t("Only for reasoning models such as gpt-oss. Low keeps replies fast and cheap."))}>
                <select value={ai.llm_reasoning_effort} onChange={(e) => setAiField("llm_reasoning_effort", e.target.value)}>
                  <option value="">{A.llm_reasoning_effort?.env_set ? t("From Render ({value})", { value: String(A.llm_reasoning_effort.env_value) }) : t("Not used")}</option>
                  <option value="low">{t("Low")}</option>
                  <option value="medium">{t("Medium")}</option>
                  <option value="high">{t("High")}</option>
                </select>
              </Field>
            </div>
          </>
        )}

        <div aria-live="polite">
          {checkError && <div className="ai-result bad"><XCircle weight="fill" /><span>{checkError}</span></div>}
          {check && (
            <div className={`ai-result ${tone}`}>
              {good ? <CheckCircle weight="fill" /> : check.ok ? <WarningCircle weight="fill" /> : <XCircle weight="fill" />}
              <div>
                <strong>{good ? t("Working") : check.ok ? t("Partly working") : t("Not working")}</strong>
                {" · "}{trServer(check.message)}{" · "}<span className="tnum">{t("{n}s", { n: check.seconds })}</span>
                <div className="ai-tech">
                  {t("Model:")} <code>{check.answered_by || check.model || "—"}</code>
                  {check.fallback_models.length > 0 && <> ({t("backup:")} <code>{check.fallback_models.join(", ")}</code>)</>}
                  {" · "}{t("Server:")} <code>{check.server || "—"}</code> · {t("API key:")} {check.api_key_set ? t("set") : t("missing")}
                </div>
                {!aiSaved && <div className="ai-tech">{t("This test used the values on the form. Press Save to keep them.")}</div>}
              </div>
            </div>
          )}
        </div>
        <ErrorBox error={aiError} />
        {aiSaved && <div className="ok-box ad-notice" role="status">{t("AI settings saved. They apply to the next customer message.")}</div>}
        <div className="ad-form-actions" style={{ flexWrap: "wrap" }}>
          <button className="btn btn-primary" disabled={aiBusy}>{aiBusy ? t("Saving…") : t("Save AI settings")}</button>
          <button type="button" className="btn" onClick={testAI} disabled={testing} aria-busy={testing}>
            {testing ? <><span className="login-spin" aria-hidden="true" />{t("Testing…")}</> : <><Lightning weight="fill" />{t("Test AI")}</>}
          </button>
          {A.llm_api_key?.saved && (
            <button type="button" className="btn btn-ghost" disabled={aiBusy} onClick={() => setConfirm("llm_api_key")}>{t("Remove saved key")}</button>
          )}
        </div>
      </form>

      {/* --- WhatsApp (platform app) --- */}
      <form className="ad-card" onSubmit={submitWA}>
        <h2 className="ad-card-title"><span className="ad-card-icon wa"><WhatsappLogo weight="fill" /></span>{t("WhatsApp (platform app)")}<span className="spacer" />
          {waReady ? <span className="ad-status on">{t("Ready to receive")}</span> : <span className="ad-status off">{t("App secret missing")}</span>}
        </h2>
        <p className="ad-card-note">{t("Your own Meta app, shared with the companies: you add each company's WhatsApp number to it, and messages reach the right company automatically. Companies that use their own Meta app do not need this.")}</p>
        {changedLine(waChange)}

        <div className="info-box small wa-steps">
          <div><strong>{t("How to connect (one time):")}</strong></div>
          <div>{t("1. In developers.facebook.com open your app → WhatsApp → Configuration → Webhook → Edit, and enter:")}</div>
          <div>{t("Callback URL:")}</div><CopyRow value={webhookUrl} label={t("Callback URL:")} />
          <div>{t("Verify token:")}</div><CopyRow value={verifyToken} label={t("Verify token:")} />
          <div><button type="button" className="btn btn-sm" disabled={waBusy} onClick={() => setConfirm("regenerate")}>
            <ArrowsClockwise />{t("New verify token")}
          </button></div>
          <div>{t("2. Press Verify and save, then subscribe to the {field} field.", { field: "messages" })}</div>
          <div>{t("3. Paste the app secret (App settings → Basic → App secret) and a permanent access token (Business settings → System users) below, and save.")}</div>
          <div>{t("4. Add each company's phone number ID on its page under Companies.")}</div>
          {!waReady && <div><strong>{t("Until the app secret is saved, WhatsApp messages sent to this address are refused.")}</strong></div>}
        </div>

        <div className="ad-grid-2">
          <Field label={t("App secret")} hint={hint(W.whatsapp_app_secret)}>
            <input type="password" dir="ltr" autoComplete="new-password" maxLength={500} value={appSecret} placeholder={secretPlaceholder(W.whatsapp_app_secret)}
              onChange={(e) => { setAppSecret(e.target.value); setWaSaved(null); }} />
          </Field>
          <Field label={t("Shared access token")} hint={hint(W.whatsapp_default_access_token, t("Used for companies that did not save their own token."))}>
            <input type="password" dir="ltr" autoComplete="new-password" maxLength={2000} value={waToken} placeholder={secretPlaceholder(W.whatsapp_default_access_token)}
              onChange={(e) => { setWaToken(e.target.value); setWaSaved(null); }} />
          </Field>
          <Field label={t("Graph API version")} hint={hint(W.whatsapp_api_version, t("For example {v}. Change only when Meta retires the version.", { v: "v21.0" }))}>
            <input dir="ltr" maxLength={10} value={apiVersion} placeholder={placeholder(W.whatsapp_api_version)} onChange={(e) => { setApiVersion(e.target.value); setWaSaved(null); }} />
          </Field>
        </div>
        <Switch checked={share} onChange={(v) => { setShare(v); setShareTouched(true); setWaSaved(null); }}
          label={t("Let companies use the shared access token")}
          hint={tokenReady ? t("Off: every company must save its own token on its AI & WhatsApp page.") : t("No shared access token is set yet.")} />

        <ErrorBox error={waError} />
        {waSaved && <div className="ok-box ad-notice" role="status">{waSaved}</div>}
        <div className="ad-form-actions" style={{ flexWrap: "wrap" }}>
          <button className="btn btn-primary" disabled={waBusy}>{waBusy ? t("Saving…") : t("Save WhatsApp settings")}</button>
          {W.whatsapp_app_secret?.saved && (
            <button type="button" className="btn btn-ghost" disabled={waBusy} onClick={() => setConfirm("whatsapp_app_secret")}>{t("Remove app secret")}</button>
          )}
          {W.whatsapp_default_access_token?.saved && (
            <button type="button" className="btn btn-ghost" disabled={waBusy} onClick={() => setConfirm("whatsapp_default_access_token")}>{t("Remove token")}</button>
          )}
        </div>
      </form>

      {/* --- Read-only info --- */}
      <section className="ad-card">
        <h2 className="ad-card-title"><span className="ad-card-icon"><Key /></span>{t("About this platform")}</h2>
        <dl className="acc-details" style={{ marginTop: 4 }}>
          <div><dt>{t("Version")}</dt><dd dir="ltr" style={{ textAlign: "start" }}>{data.info.version || "—"}{data.info.commit ? ` · ${data.info.commit}` : ""}</dd></div>
          <div><dt>{t("Database")}</dt><dd>{data.info.database}{data.info.database === "SQLite" && data.info.environment === "production" ? ` · ${t("data is lost when the server restarts on hosts without a disk")}` : ""}</dd></div>
          <div><dt>{t("Environment")}</dt><dd>{data.info.environment === "production" ? t("Production") : t("Development")}</dd></div>
          <div><dt>{t("Demo data")}</dt><dd>{data.info.demo_data ? t("On") : t("Off")}</dd></div>
          <div><dt>{t("Companies")}</dt><dd className="tnum">{data.info.companies}</dd></div>
        </dl>
      </section>

      {confirm && (
        <ConfirmSheet
          title={confirm === "regenerate" ? t("Create a new verify token?") : t("Remove this saved value?")}
          text={confirm === "regenerate"
            ? t("The old token stops working. You must enter the new one in your Meta app's webhook settings.")
            : t("The value from Render is used again, if there is one.")}
          confirmLabel={confirm === "regenerate" ? t("Create new token") : t("Remove")}
          tone={confirm === "regenerate" ? "primary" : "danger"}
          busy={waBusy || aiBusy}
          onCancel={() => setConfirm(null)}
          onConfirm={() => (confirm === "regenerate" ? regenerate() : removeSecret(confirm))}
        />
      )}
    </div>
  );
}
