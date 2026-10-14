import { FormEvent, useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { get } from "../api";
import { homePath, useAuth } from "../auth";
import { GhanjahLockup } from "../components/Brand";
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
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-hero">
        <div className="login-lang"><LangSwitch className="btn btn-sm lang-switch" /></div>
        <GhanjahLockup dark />
        <p className="login-tagline">{t("From Oman to the world")}</p>
        <p>{t("Your AI travel consultant sells your packages on the web and WhatsApp, day and night, and hands every booking to your team for payment.")}</p>
      </div>
      <form className="login-card" onSubmit={submit}>
        <h2>{t("Sign in")}</h2>
        {state?.expired && !error && <div className="info-box small" role="status">{t("Your session ended, please sign in again")}</div>}
        <label className="field">
          <span className="field-label">{t("Email")}</span>
          <input type="email" autoComplete="username" dir="ltr" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="field">
          <span className="field-label">{t("Password")}</span>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <div className="error-box" role="alert">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? t("Signing in…") : t("Sign in")}</button>

        {demo.length > 0 && (
          <div className="demo-box">
            <div className="muted small">{t("Demo accounts (click to fill)")}</div>
            {demo.map((a) => (
              <button type="button" key={a.email} className="demo-account"
                onClick={() => { setEmail(a.email); setPassword(a.password); }}>
                <strong>{a.label}</strong> <span className="muted" dir="ltr">{a.email}</span>
              </button>
            ))}
            <a className="small" href="/c/sunrise-travel" target="_blank" rel="noreferrer">{t("Open the demo customer page")} ↗</a>
          </div>
        )}
      </form>
    </div>
  );
}
