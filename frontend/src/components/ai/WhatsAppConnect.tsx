import { FormEvent, ReactNode, useEffect, useState } from "react";
import { get, patch, post } from "../../api";
import { trServer, useI18n } from "../../lang";
import type { WhatsAppStatus, WhatsAppTestResult } from "../../types";
import { ArrowSquareOut, Check, CheckCircle, Copy, PaperPlaneRight, Plugs, WhatsappLogo, XCircle } from "../Icon";
import { ErrorBox, Field } from "../ui";
import "./ai.css";
import "./i18n";

export function CopyValue({ value }: { value: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <div className="copy-row">
      <code dir="ltr">{value}</code>
      <button type="button" className={`btn btn-sm ${copied ? "btn-soft" : ""}`} onClick={() => {
        navigator.clipboard?.writeText(value).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }).catch(() => {});
      }}>{copied ? <><Check />{t("Copied")}</> : <><Copy />{t("Copy")}</>}</button>
      <span className="sr-only" aria-live="polite">{copied ? t("Copied") : ""}</span>
    </div>
  );
}

export function WhatsAppBadge({ status }: { status: WhatsAppStatus["status"] }) {
  const { t } = useI18n();
  if (status === "connected") return <span className="ad-status on">{t("Connected")}</span>;
  if (status === "needs_app_secret") return <span className="ad-status warn">{t("Needs app secret")}</span>;
  if (status === "needs_token") return <span className="ad-status warn">{t("Needs the platform token")}</span>;
  return <span className="ad-status off">{t("Not connected")}</span>;
}

const ext = (href: string, label: string) => <a href={href} target="_blank" rel="noreferrer">{label} <ArrowSquareOut /></a>;

/** "Connect WhatsApp": the company's own Meta app step by step, or the platform's shared number.
 *  variant "company" saves to /api/company; variant "owner" (platform console) assigns the shared number. */
export default function WhatsAppConnect({ variant, base, companyPath }: {
  variant: "company" | "owner";
  /** /api/company/whatsapp or /api/system/companies/{id}/whatsapp */
  base: string;
  /** Owner only: /api/system/companies/{id} (to assign the platform number). */
  companyPath?: string;
}) {
  const { t } = useI18n();
  const [st, setSt] = useState<WhatsAppStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [choice, setChoice] = useState<"own" | "platform">("own");

  const load = () => get<WhatsAppStatus>(base).then((s) => { setSt(s); setChoice(s.mode === "platform" ? "platform" : "own"); })
    .catch((e) => setLoadError(e.message));
  useEffect(() => { load(); }, [base]);
  if (!st) return loadError ? <div className="error-box">{loadError}</div> : <div className="skeleton" style={{ height: 260, borderRadius: 24 }} />;

  const webhook = st.webhook_path ? `${window.location.origin}${st.webhook_path}` : "";

  return (
    <section className="ad-card wa-connect">
      <div className="wa-connect-head">
        <h2 className="ad-card-title" style={{ margin: 0 }}><span className="ad-card-icon wa"><WhatsappLogo weight="fill" /></span>{t("Connect WhatsApp")}</h2>
        <span className="spacer" />
        <WhatsAppBadge status={st.status} />
      </div>
      <p className="ad-card-note">{variant === "company"
        ? t("Customers who message your WhatsApp number talk to your AI consultant, and your team sees the chats in Conversations. Choose how to connect:")
        : t("This company's WhatsApp connection. You can assign a number of the platform's Meta app, or the company connects its own Meta app in its settings.")}</p>

      {st.phone_number_id && (
        <p className="ad-card-note">{t("Phone number ID:")} <code dir="ltr">{st.phone_number_id}</code>
          {st.display_number && <> · <bdi dir="ltr">{st.display_number}</bdi></>}
          {" · "}{st.mode === "platform" ? t("on the platform's WhatsApp app") : t("on the company's own Meta app")}</p>
      )}

      {variant === "company" && (
        <div className="wa-choice" role="group" aria-label={t("How to connect")}>
          <button type="button" aria-pressed={choice === "own"} onClick={() => setChoice("own")}>
            <strong>{t("My own WhatsApp Business number")}</strong>
            <span>{t("Your number, your Meta app. About 20 minutes, following the 4 steps below.")}</span>
          </button>
          <button type="button" aria-pressed={choice === "platform"} onClick={() => setChoice("platform")}>
            <strong>{t("Use the platform's WhatsApp number")}</strong>
            <span>{t("Nothing to set up: the platform owner connects a number for you.")}</span>
          </button>
        </div>
      )}

      {variant === "owner" ? (
        <>
          <OwnerAssign st={st} companyPath={companyPath ?? ""} onSaved={load} />
          {webhook && st.mode !== "platform" && (
            <div className="info-box small">
              <div>{t("The company's own webhook (if it uses its own Meta app):")}</div>
              <CopyValue value={webhook} />
              <div>{t("Verify token:")}</div>
              <CopyValue value={st.verify_token ?? ""} />
              <div>{st.token_set ? t("Access token saved by the company.") : t("No access token saved by the company.")}{" "}
                {st.app_secret_set ? t("App secret saved.") : t("No app secret saved.")}</div>
            </div>
          )}
          <TestBox base={base} st={st} onResult={setSt} />
        </>
      ) : choice === "platform" ? (
        <div className="wa-step">
          <span className="wa-step-num" aria-hidden="true"><Plugs /></span>
          <div className="wa-step-body">
            <h3>{t("The platform's WhatsApp number")}</h3>
            <ul>
              <li>{t("The platform owner adds a WhatsApp number to the platform's Meta app and assigns it to your company. Ask the platform owner for it.")}</li>
              <li>{t("You don't need a Meta account, token or webhook: messages to that number reach your AI and your team automatically.")}</li>
              <li>{t("Once it is assigned, it shows here as connected. You can still switch to your own number later.")}</li>
            </ul>
            {st.mode === "platform"
              ? <div className="ok-box">{t("A platform number is assigned to your company.")}</div>
              : <div className="info-box small">{t("No platform number is assigned to your company yet.")}</div>}
            {st.mode === "platform" && <TestBox base={base} st={st} onResult={setSt} />}
          </div>
        </div>
      ) : (
        <OwnSteps st={st} webhook={webhook} base={base} onSaved={load} onResult={setSt} />
      )}
    </section>
  );
}

function Step({ n, done, title, children }: { n: number; done?: boolean; title: string; children: ReactNode }) {
  return (
    <div className={`wa-step ${done ? "done" : ""}`}>
      <span className="wa-step-num" aria-hidden="true">{done ? <Check weight="bold" /> : n}</span>
      <div className="wa-step-body"><h3>{title}</h3>{children}</div>
    </div>
  );
}

function OwnSteps({ st, webhook, base, onSaved, onResult }: {
  st: WhatsAppStatus; webhook: string; base: string; onSaved: () => void; onResult: (s: WhatsAppStatus) => void;
}) {
  const { t } = useI18n();
  const [numberId, setNumberId] = useState(st.mode === "own" ? st.phone_number_id ?? "" : "");
  const [display, setDisplay] = useState(st.display_number ?? "");
  const [token, setToken] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    // One request: the server saves the token first and checks the phone number ID with Meta using it.
    const body: Record<string, unknown> = { whatsapp_display_number: display.trim() };
    // A platform number assigned by the owner stays until the company enters its own.
    if (st.mode !== "platform" || numberId.trim()) body.whatsapp_phone_number_id = numberId.trim();
    if (token.trim()) body.whatsapp_access_token = token.trim();
    if (secret.trim()) body.whatsapp_app_secret = secret.trim();
    try {
      await patch("/api/company", body);
      setToken("");
      setSecret("");
      setSaved(true);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Step n={1} done={st.token_set} title={t("Get these from Meta")}>
        <ol>
          <li><strong>{t("A Meta Business account")}</strong> — {ext("https://business.facebook.com", "business.facebook.com")}</li>
          <li><strong>{t("A Meta app with WhatsApp")}</strong> — {t("on {site}: My Apps → Create app → Business, then add the WhatsApp product.", { site: "developers.facebook.com" })} {ext("https://developers.facebook.com/apps", t("Open"))}</li>
          <li><strong>{t("Phone number ID")}</strong> — {t("in your app → WhatsApp → API Setup, add and verify your business number, then copy its Phone number ID (a long number, not the phone number). The WhatsApp Business Account ID is not needed here.")}</li>
          <li><strong>{t("Permanent access token")}</strong> — {t("Business settings → Users → System users → Add, give it your app and WhatsApp account, then Generate token with {perms}. The temporary token of API Setup stops after 24 hours.", { perms: "whatsapp_business_messaging, whatsapp_business_management" })}</li>
          <li><strong>{t("App secret")}</strong> — {t("in your app → App settings → Basic → App secret → Show.")}</li>
        </ol>
      </Step>

      <Step n={2} done={st.mode === "own" && !!st.phone_number_id && st.token_set && st.app_secret_set} title={t("Enter them here")}>
        <form onSubmit={save}>
          <div className="ad-grid-2">
            <Field label={t("Phone number ID")} hint={t("Checked with Meta using your access token, so nobody can connect a number that isn't theirs.")}>
              <input dir="ltr" inputMode="numeric" maxLength={64} value={numberId} onChange={(e) => { setNumberId(e.target.value.replace(/\s/g, "")); setSaved(false); }} />
            </Field>
            <Field label={t("Public WhatsApp number")} hint={t("Shown on your customer page, e.g. {example}", { example: "+968 9123 4567" })}>
              <input dir="ltr" maxLength={50} value={display} onChange={(e) => { setDisplay(e.target.value); setSaved(false); }} />
            </Field>
            <Field label={t("Access token")} hint={st.token_set ? t("Saved (encrypted). Type a new one to replace it.") : t("Permanent token of a Meta system user with {permission}.", { permission: "whatsapp_business_messaging" })}>
              <input type="password" value={token} placeholder={st.token_set ? `•••••••• (${t("saved")})` : ""} onChange={(e) => { setToken(e.target.value); setSaved(false); }} autoComplete="new-password" dir="ltr" />
            </Field>
            <Field label={t("App secret")} hint={st.app_secret_set ? t("Saved (encrypted). Type a new one to replace it.") : t("Required for your own Meta app: without it WhatsApp messages are refused. Meta App → App settings → Basic → App secret.")}>
              <input type="password" value={secret} placeholder={st.app_secret_set ? `•••••••• (${t("saved")})` : ""} onChange={(e) => { setSecret(e.target.value); setSaved(false); }} autoComplete="new-password" dir="ltr" />
            </Field>
          </div>
          <ErrorBox error={error} />
          {saved && <div className="ok-box ad-notice" role="status">{t("WhatsApp settings saved.")}</div>}
          <div className="ad-form-actions">
            <button className="btn btn-primary" disabled={busy} aria-busy={busy}>{busy ? t("Saving…") : t("Save WhatsApp settings")}</button>
            {st.token_set && (
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={async () => {
                if (!confirm(t("Remove the WhatsApp access token? WhatsApp messages stop working until a new one is saved."))) return;
                try { await patch("/api/company", { whatsapp_access_token: "" }); onSaved(); } catch (err) { setError((err as Error).message); }
              }}>{t("Remove token")}</button>
            )}
          </div>
        </form>
      </Step>

      <Step n={3} done={st.app_secret_set && st.status === "connected"} title={t("Point Meta's webhook to your AI")}>
        <p className="ad-card-note" style={{ marginTop: 0 }}>{t("In your app → WhatsApp → Configuration → Webhook → Edit, paste:")}</p>
        <div>{t("Callback URL:")}</div>
        {webhook && <CopyValue value={webhook} />}
        <div>{t("Verify token:")}</div>
        <CopyValue value={st.verify_token ?? ""} />
        <ul>
          <li>{t("Click Verify and save. Then, under Webhook fields, click Manage and subscribe to {field}.", { field: "messages" })}</li>
          <li>{t("Keep these private.")}</li>
        </ul>
        {!st.app_secret_set && <div className="warn-box">{t("Save your app secret in step 2 first: messages sent to this address are refused without it.")}</div>}
      </Step>

      <Step n={4} done={st.status === "connected"} title={t("Test the connection")}>
        <TestBox base={base} st={st} onResult={onResult} />
      </Step>
    </>
  );
}

function OwnerAssign({ st, companyPath, onSaved }: { st: WhatsAppStatus; companyPath: string; onSaved: () => void }) {
  const { t } = useI18n();
  const [number, setNumber] = useState(st.mode === "platform" ? st.phone_number_id ?? "" : "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await patch(companyPath, { whatsapp_phone_number_id: number.trim() });
      setSaved(true);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={save} className="wa-step">
      <span className="wa-step-num" aria-hidden="true"><Plugs /></span>
      <div className="wa-step-body">
        <h3>{t("Platform WhatsApp number")}</h3>
        <ul>
          <li>{t("Add the number to the platform's own Meta app (WhatsApp → API Setup) and paste its Phone number ID here. Messages to it go to this company's AI and team.")}</li>
          <li>{st.platform_available ? t("The platform's WhatsApp token is set on the server.") : t("The platform's WhatsApp token is not set on the server (WHATSAPP_DEFAULT_ACCESS_TOKEN), so platform numbers can't send messages yet.")}</li>
          {st.mode === "own" && st.phone_number_id && <li>{t("This company already connected its own number. Assigning a platform number replaces it.")}</li>}
        </ul>
        <div className="wa-test-row">
          <Field label={t("WhatsApp phone number ID (platform app)")} hint={t("Leave empty to disconnect.")}>
            <input value={number} onChange={(e) => { setNumber(e.target.value.replace(/\D/g, "")); setSaved(false); }} inputMode="numeric" maxLength={64} dir="ltr" />
          </Field>
          <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Save")}</button>
        </div>
        <ErrorBox error={error} />
        {saved && <div className="ok-box ad-notice" role="status">{t("Saved.")}</div>}
      </div>
    </form>
  );
}

function TestBox({ base, st, onResult }: { base: string; st: WhatsAppStatus; onResult: (s: WhatsAppStatus) => void }) {
  const { t } = useI18n();
  const [result, setResult] = useState<WhatsAppTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"test" | "msg" | null>(null);
  const [phone, setPhone] = useState("");
  const [msgOk, setMsgOk] = useState<string | null>(null);
  const [msgError, setMsgError] = useState<string | null>(null);

  const test = async () => {
    setBusy("test");
    setError(null);
    try {
      const r = await post<WhatsAppTestResult>(`${base}/test`);
      setResult(r);
      onResult(r.status);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const sendMsg = async (e: FormEvent) => {
    e.preventDefault();
    setBusy("msg");
    setMsgOk(null);
    setMsgError(null);
    try {
      const r = await post<{ sent: boolean; to: string; message: string }>(`${base}/test-message`, { phone });
      setMsgOk(`${trServer(r.message)} (${r.to})`);
    } catch (err) {
      setMsgError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const ok = result?.result === "connected";
  const canSend = !!st.phone_number_id && (st.token_set || st.mode === "platform");

  return (
    <div className="wa-test">
      <p className="ad-card-note" style={{ marginTop: 0 }}>{t("Asks Meta whether the access token may use this phone number.")}</p>
      <button type="button" className="btn btn-primary" onClick={test} disabled={busy !== null} aria-busy={busy === "test"}>
        {busy === "test" ? <><span className="login-spin" aria-hidden="true" />{t("Testing…")}</> : <><Plugs />{t("Test connection")}</>}
      </button>
      <div aria-live="polite">
        <ErrorBox error={error} />
        {result && (
          <div className={`wa-result ${ok ? "ok" : "bad"}`}>
            {ok ? <CheckCircle weight="fill" /> : <XCircle weight="fill" />}
            <div><strong>{ok ? t("Connected") : t("Not connected")}</strong> · <span>{trServer(result.message)}</span>
              {ok && (result.verified_name || result.display_number) && (
                <div><span dir="auto">{result.verified_name}</span> <bdi dir="ltr">{result.display_number}</bdi></div>
              )}
              {ok && st.status === "needs_app_secret" && <div><span>{t("Messages from customers still need the app secret (step 2).")}</span></div>}
            </div>
          </div>
        )}
      </div>
      {canSend && (
        <form onSubmit={sendMsg} style={{ marginTop: 14 }}>
          <div className="wa-test-row">
            <Field label={t("Send a test message to my phone")} hint={t("With the country code. First send any message from this phone to your business number: Meta only allows free messages within 24 hours of the customer's last message.")}>
              <input dir="ltr" type="tel" inputMode="tel" maxLength={30} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+968 9123 4567" required minLength={6} />
            </Field>
            <button className="btn btn-wa" disabled={busy !== null || phone.trim().length < 6}>
              {busy === "msg" ? t("Sending…") : <><PaperPlaneRight weight="fill" className="flip" />{t("Send test")}</>}
            </button>
          </div>
          <div aria-live="polite">
            {msgOk && <div className="ok-box ad-notice">{msgOk}</div>}
            <ErrorBox error={msgError} />
          </div>
        </form>
      )}
    </div>
  );
}
