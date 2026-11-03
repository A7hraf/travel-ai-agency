import { FormEvent, ReactNode, useEffect, useState } from "react";
import { get, patch, post } from "../../api";
import { trServer, useI18n } from "../../lang";
import type { InstagramStatus, InstagramTestResult } from "../../types";
import { ArrowSquareOut, Check, CheckCircle, ClockCountdown, InstagramLogo, Plugs, XCircle } from "../Icon";
import { ErrorBox, Field } from "../ui";
import { CopyValue } from "./WhatsAppConnect";
import "./ai.css";
import "./instagram.css";
import "./i18n";
import "./instagram-i18n";

export function InstagramBadge({ status }: { status: InstagramStatus["status"] }) {
  const { t } = useI18n();
  if (status === "connected") return <span className="ad-status on">{t("Connected")}</span>;
  if (status === "needs_app_secret") return <span className="ad-status warn">{t("Needs app secret")}</span>;
  if (status === "needs_token") return <span className="ad-status warn">{t("Needs access token")}</span>;
  return <span className="ad-status off">{t("Not connected")}</span>;
}

const ext = (href: string, label: string) => <a href={href} target="_blank" rel="noreferrer">{label} <ArrowSquareOut /></a>;

/** "Connect Instagram": the company's own Meta app with the Instagram API with Instagram Login.
 *  variant "company" saves to /api/company (the account is checked with Instagram);
 *  variant "owner" (platform console) saves to {base} and may assign an account without the check. */
export default function InstagramConnect({ variant, base }: {
  variant: "company" | "owner";
  /** /api/company/instagram or /api/system/companies/{id}/instagram */
  base: string;
}) {
  const { t } = useI18n();
  const [st, setSt] = useState<InstagramStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = () => get<InstagramStatus>(base).then(setSt).catch((e) => setLoadError(e.message));
  useEffect(() => { load(); }, [base]);
  if (!st) return loadError ? <div className="error-box">{loadError}</div> : <div className="skeleton" style={{ height: 260, borderRadius: 24 }} />;

  const webhook = st.webhook_path ? `${window.location.origin}${st.webhook_path}` : "";
  // Where account fixes are saved: the company's own settings, or the owner's endpoint.
  const savePath = variant === "company" ? "/api/company" : base;

  return (
    <section className="ad-card wa-connect" aria-labelledby="ig-connect-title">
      <div className="wa-connect-head">
        <h2 className="ad-card-title" id="ig-connect-title" style={{ margin: 0 }}><span className="ad-card-icon ig"><InstagramLogo weight="fill" /></span>{t("Connect Instagram")}</h2>
        <span className="spacer" />
        <InstagramBadge status={st.status} />
      </div>
      <p className="ad-card-note">{variant === "company"
        ? t("Customers who send a Direct Message to your Instagram account talk to your AI consultant, and your team sees and answers the chats in Conversations, like WhatsApp.")
        : t("This company's Instagram Direct connection. You can set it up for the company here: you may assign an account ID without Instagram's ownership check, but never one used by another company.")}</p>

      {st.account_id && (
        <p className="ad-card-note ig-account">{t("Instagram account:")}
          {st.username && <bdi dir="ltr">@{st.username}</bdi>}
          <span>· {t("Account ID:")} <code dir="ltr">{st.account_id}</code></span></p>
      )}

      {variant === "owner" ? (
        <>
          <OwnerForm st={st} base={base} onSaved={load} />
          {webhook && (
            <div className="info-box small">
              <div>{t("The company's Instagram webhook (Callback URL):")}</div>
              <CopyValue value={webhook} />
              <div>{t("Verify token:")}</div>
              <CopyValue value={st.verify_token ?? ""} />
            </div>
          )}
          <TestBox base={base} savePath={savePath} onResult={setSt} onSaved={load} />
        </>
      ) : (
        <OwnSteps st={st} webhook={webhook} base={base} onSaved={load} onResult={setSt} />
      )}
      <WindowNote />
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

function WindowNote() {
  const { t } = useI18n();
  return (
    <div className="info-box small ig-window" role="note">
      <strong><ClockCountdown aria-hidden="true" /> {t("Instagram's 24-hour window")}</strong>
      <ul>
        <li>{t("Your AI and your team can answer a customer for 24 hours after their last message.")}</li>
        <li>{t("After that Instagram refuses replies until the customer writes again. Conversations shows when the window has ended.")}</li>
        <li>{t("Instagram does not share the customer's phone number: the AI asks for it before it books a trip.")}</li>
      </ul>
    </div>
  );
}

function OwnSteps({ st, webhook, base, onSaved, onResult }: {
  st: InstagramStatus; webhook: string; base: string; onSaved: () => void; onResult: (s: InstagramStatus) => void;
}) {
  const { t } = useI18n();
  const [accountId, setAccountId] = useState(st.account_id ?? "");
  const [token, setToken] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setAccountId(st.account_id ?? ""); }, [st.account_id]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    // One request: the server saves the token first, then checks with Instagram that the account is
    // the token's own (or finds the account from the token when the ID is left empty).
    const body: Record<string, unknown> = {};
    if (token.trim()) body.instagram_access_token = token.trim();
    if (secret.trim()) body.instagram_app_secret = secret.trim();
    if (accountId.trim() !== (st.account_id ?? "")) body.instagram_account_id = accountId.trim();
    try {
      if (Object.keys(body).length) await patch("/api/company", body);
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
          <li><strong>{t("An Instagram professional account")}</strong> — {t("Meta only connects Business or Creator accounts. In the Instagram app: Settings → Account type and tools → Switch to professional account.")}</li>
          <li><strong>{t("Allow access to messages")}</strong> — {t("in the Instagram app: Settings → Messages and story replies → Message controls → Connected tools → turn on Allow access to messages.")}</li>
          <li><strong>{t("A Meta app with Instagram")}</strong> — {t("on {site}: My Apps → Create app → Business, then add the product {product}.", { site: "developers.facebook.com", product: "Instagram (API setup with Instagram login)" })} {ext("https://developers.facebook.com/apps", t("Open"))}</li>
          <li><strong>{t("Access token")}</strong> — {t("in your app → Instagram → API setup with Instagram login → Generate access tokens → Add account, log in with your business Instagram account, then Generate token. It needs {perms}.", { perms: "instagram_business_basic, instagram_business_manage_messages" })}</li>
          <li><strong>{t("Instagram app secret")}</strong> — {t("on the same page, under Instagram app ID → Instagram app secret → Show. It is not the Facebook app secret.")}</li>
        </ol>
      </Step>

      <Step n={2} done={!!st.account_id && st.token_set && st.app_secret_set} title={t("Enter them here")}>
        <form onSubmit={save}>
          <div className="ad-grid-2">
            <Field label={t("Access token")} hint={st.token_set ? t("Saved (encrypted). Type a new one to replace it.") : t("The long token from Generate token. It is renewed automatically while customers write to you.")}>
              <input type="password" value={token} placeholder={st.token_set ? `•••••••• (${t("saved")})` : ""} onChange={(e) => { setToken(e.target.value); setSaved(false); }} autoComplete="new-password" dir="ltr" />
            </Field>
            <Field label={t("Instagram app secret")} hint={st.app_secret_set ? t("Saved (encrypted). Type a new one to replace it.") : t("Required: without it Instagram messages are refused.")}>
              <input type="password" value={secret} placeholder={st.app_secret_set ? `•••••••• (${t("saved")})` : ""} onChange={(e) => { setSecret(e.target.value); setSaved(false); }} autoComplete="new-password" dir="ltr" />
            </Field>
            <Field label={t("Instagram account ID")} hint={t("Leave empty: it is read from your access token. If you type it, Instagram must confirm it belongs to your token, so nobody can connect an account that isn't theirs.")}>
              <input dir="ltr" inputMode="numeric" maxLength={64} value={accountId} onChange={(e) => { setAccountId(e.target.value.replace(/\D/g, "")); setSaved(false); }} />
            </Field>
          </div>
          <ErrorBox error={error} />
          {saved && <div className="ok-box ad-notice" role="status">{t("Instagram settings saved.")}</div>}
          <div className="ad-form-actions">
            <button className="btn btn-primary" disabled={busy} aria-busy={busy}>{busy ? t("Saving…") : t("Save Instagram settings")}</button>
            {(st.token_set || st.account_id) && (
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={async () => {
                if (!confirm(t("Disconnect Instagram? Direct messages stop reaching your AI and your team until you connect again."))) return;
                try { await patch("/api/company", { instagram_access_token: "", instagram_account_id: "" }); onSaved(); } catch (err) { setError((err as Error).message); }
              }}>{t("Disconnect")}</button>
            )}
          </div>
        </form>
      </Step>

      <Step n={3} done={st.status === "connected"} title={t("Point Meta's webhook to your AI")}>
        <p className="ad-card-note" style={{ marginTop: 0 }}>{t("In your app → Instagram → API setup with Instagram login → Configure webhooks, paste:")}</p>
        <div>{t("Callback URL:")}</div>
        {webhook && <CopyValue value={webhook} />}
        <div>{t("Verify token:")}</div>
        <CopyValue value={st.verify_token ?? ""} />
        <ul>
          <li>{t("Click Verify and save. Then subscribe to the {field} webhook field.", { field: "messages" })}</li>
          <li>{t("Until Meta approves your app (App Review of {perm}) and it is Live, only people with a role in your app reach the AI.", { perm: "instagram_business_manage_messages" })}</li>
          <li>{t("Keep these private.")}</li>
        </ul>
        {!st.app_secret_set && <div className="warn-box">{t("Save your Instagram app secret in step 2 first: messages sent to this address are refused without it.")}</div>}
      </Step>

      <Step n={4} done={st.status === "connected"} title={t("Test the connection")}>
        <TestBox base={base} savePath="/api/company" onResult={onResult} onSaved={onSaved} />
      </Step>
    </>
  );
}

function OwnerForm({ st, base, onSaved }: { st: InstagramStatus; base: string; onSaved: () => void }) {
  const { t } = useI18n();
  const [accountId, setAccountId] = useState(st.account_id ?? "");
  const [username, setUsername] = useState(st.username ?? "");
  const [token, setToken] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    const body: Record<string, unknown> = { instagram_account_id: accountId.trim(), instagram_username: username.trim() };
    if (token.trim()) body.instagram_access_token = token.trim();
    if (secret.trim()) body.instagram_app_secret = secret.trim();
    try {
      await patch(base, body);
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
    <form onSubmit={save} className="wa-step">
      <span className="wa-step-num" aria-hidden="true"><Plugs /></span>
      <div className="wa-step-body">
        <h3>{t("Set up Instagram for this company")}</h3>
        <ul>
          <li>{t("The company's own Meta app sends and signs the messages: it needs the access token and the Instagram app secret of that app.")}</li>
          <li>{t("Leave the token and secret empty to keep the saved ones.")}</li>
        </ul>
        <div className="ad-grid-2">
          <Field label={t("Instagram account ID")} hint={t("Leave empty to disconnect.")}>
            <input value={accountId} onChange={(e) => { setAccountId(e.target.value.replace(/\D/g, "")); setSaved(false); }} inputMode="numeric" maxLength={64} dir="ltr" />
          </Field>
          <Field label={t("Instagram username")} hint={t("Shown to the team, for example {example}", { example: "@sunrise.travel" })}>
            <input value={username} onChange={(e) => { setUsername(e.target.value); setSaved(false); }} maxLength={100} dir="ltr" />
          </Field>
          <Field label={t("Access token")} hint={st.token_set ? t("Saved (encrypted). Type a new one to replace it.") : t("No access token saved.")}>
            <input type="password" value={token} placeholder={st.token_set ? `•••••••• (${t("saved")})` : ""} onChange={(e) => { setToken(e.target.value); setSaved(false); }} autoComplete="new-password" dir="ltr" />
          </Field>
          <Field label={t("Instagram app secret")} hint={st.app_secret_set ? t("Saved (encrypted). Type a new one to replace it.") : t("No app secret saved.")}>
            <input type="password" value={secret} placeholder={st.app_secret_set ? `•••••••• (${t("saved")})` : ""} onChange={(e) => { setSecret(e.target.value); setSaved(false); }} autoComplete="new-password" dir="ltr" />
          </Field>
        </div>
        <ErrorBox error={error} />
        {saved && <div className="ok-box ad-notice" role="status">{t("Saved.")}</div>}
        <div className="ad-form-actions"><button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Save")}</button></div>
      </div>
    </form>
  );
}

function TestBox({ base, savePath, onResult, onSaved }: {
  base: string; savePath: string; onResult: (s: InstagramStatus) => void; onSaved: () => void;
}) {
  const { t } = useI18n();
  const [result, setResult] = useState<InstagramTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const test = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await post<InstagramTestResult>(`${base}/test`);
      setResult(r);
      onResult(r.status);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  // The token works but no account is saved yet: one click connects the token's own account.
  const useAccount = async () => {
    if (!result?.user_id) return;
    setBusy(true);
    setError(null);
    try {
      await patch(savePath, { instagram_account_id: result.user_id });
      setResult(null);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const ok = result?.result === "connected";

  return (
    <div className="wa-test">
      <p className="ad-card-note" style={{ marginTop: 0 }}>{t("Asks Instagram which account the access token belongs to, and whether it is the connected one.")}</p>
      <button type="button" className="btn btn-primary" onClick={test} disabled={busy} aria-busy={busy}>
        {busy ? <><span className="login-spin" aria-hidden="true" />{t("Testing…")}</> : <><Plugs />{t("Test connection")}</>}
      </button>
      <div aria-live="polite">
        <ErrorBox error={error} />
        {result && (
          <div className={`wa-result ${ok ? "ok" : "bad"}`}>
            {ok ? <CheckCircle weight="fill" /> : <XCircle weight="fill" />}
            <div><strong>{ok ? t("Connected") : t("Not connected")}</strong> · <span>{trServer(result.message)}</span>
              {result.user_id && (
                <div>{result.username && <bdi dir="ltr">@{result.username}</bdi>} <span>{t("Account ID:")}</span> <code dir="ltr">{result.user_id}</code></div>
              )}
              {ok && result.status.status === "needs_app_secret" && <div><span>{t("Messages from customers still need the Instagram app secret (step 2).")}</span></div>}
              {result.result === "account_missing" && result.user_id && (
                <button type="button" className="btn btn-sm btn-soft" style={{ marginTop: 8 }} onClick={useAccount} disabled={busy}>
                  {result.username ? t("Connect @{username}", { username: result.username }) : t("Connect this account")}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
