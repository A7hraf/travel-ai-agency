import { FormEvent, useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError, get } from "../api";
import { homePath, useAuth } from "../auth";
import { GhanjahLockup } from "../components/Brand";
import { ArrowSquareOut, Envelope, Key, SignIn, UserCircle } from "../components/Icon";
import { LangSwitch, useI18n } from "../lang";

interface DemoAccount {
  label: string;
  email: string;
  password: string;
}

export default function Login() {
  const { user, login } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { from?: string; expired?: boolean } | null;
  const from = state?.from && state.from.startsWith("/") && !state.from.startsWith("/login") ? state.from : null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [wrong, setWrong] = useState(0);
  const [busy, setBusy] = useState(false);
  // Demo logins come from the server, only on development setups: they are never in the website code.
  const [demo, setDemo] = useState<DemoAccount[]>([]);

  useEffect(() => {
    get<DemoAccount[]>("/api/auth/demo-accounts").then(setDemo).catch(() => {});
  }, []);

  if (user) return <Navigate to={from ?? homePath(user)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await login(email, password);
      navigate(from ?? homePath(me), { replace: true });
    } catch (err) {
      const wrongPass = err instanceof ApiError && err.status === 401;
      setError(wrongPass ? t("Wrong email or password.") : (err as Error).message);
      if (wrongPass) setWrong((n) => n + 1);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div className="gj-orbs" aria-hidden="true" />
      <div className="login-top">
        <LangSwitch className="btn btn-sm lang-switch" />
      </div>
      <div className="login-grid">
        <section className="login-hero">
          <GhanjahLockup dark />
          <div className="login-kicker">{t("Agency workspace")}</div>
          <h1 className="login-title">{t("From Oman to")} <span className="accent-word">{t("the world")}</span></h1>
          <p className="login-text">{t("Your agency's AI travel consultant, on your page and on WhatsApp, with your team one tap away.")}</p>
        </section>

        <form className="login-card" onSubmit={submit} noValidate={false}>
          <h2>{t("Sign in")}</h2>
          {state?.expired && !error && (
            <div className="info-box login-note" role="status">{t("Your session ended, please sign in again.")}</div>
          )}
          <label className="field">
            <span className="field-label">{t("Email")}</span>
            <span className="login-input">
              <Envelope aria-hidden="true" />
              <input type="email" autoComplete="username" dir="ltr" value={email} required autoFocus
                className={wrong && error ? "invalid" : ""} key={`e${wrong}`}
                onChange={(e) => { setEmail(e.target.value); setError(null); }} />
            </span>
          </label>
          <label className="field">
            <span className="field-label">{t("Password")}</span>
            <span className="login-input">
              <Key aria-hidden="true" />
              <input type="password" autoComplete="current-password" value={password} required
                className={wrong && error ? "invalid" : ""} key={`p${wrong}`}
                onChange={(e) => { setPassword(e.target.value); setError(null); }} />
            </span>
          </label>
          {error && <div className="error-box" role="alert">{error}</div>}
          <button className="btn btn-primary btn-lg btn-block" disabled={busy} aria-busy={busy}>
            {busy ? <><span className="login-spin" aria-hidden="true" />{t("Signing in…")}</> : <><SignIn className="flip" />{t("Sign in")}</>}
          </button>

          {demo.length > 0 && (
            <div className="demo-box">
              <div className="demo-head">
                <strong>{t("Demo accounts")}</strong>
                <span>{t("Development only. Tap to fill the form.")}</span>
              </div>
              {demo.map((a) => (
                <button type="button" key={a.email} className={`demo-account ${email === a.email ? "active" : ""}`}
                  onClick={() => { setEmail(a.email); setPassword(a.password); setError(null); }}>
                  <UserCircle className="demo-icon" />
                  <span className="demo-text"><strong>{a.label}</strong><bdi dir="ltr">{a.email}</bdi></span>
                </button>
              ))}
              <a className="demo-link" href="/c/sunrise-travel" target="_blank" rel="noreferrer">
                {t("Open the demo customer page")} <ArrowSquareOut className="flip" />
              </a>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
