import { FormEvent, useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { get } from "../api";
import { homePath, useAuth } from "../auth";

const DEMO_ACCOUNTS = [
  { label: "Platform owner", email: "owner@example.com", password: "ChangeMe123!" },
  { label: "Company admin", email: "admin@sunrise-travel.example", password: "Admin123!" },
  { label: "Support", email: "support@sunrise-travel.example", password: "Support123!" },
  { label: "Ticket employee", email: "tickets@sunrise-travel.example", password: "Tickets123!" },
];

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    get<{ demo: boolean }>("/api/health").then((h) => setDemo(h.demo)).catch(() => {});
  }, []);

  if (user) return <Navigate to={homePath(user)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await login(email, password);
      navigate(homePath(me));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-hero">
        <div className="brand-mark big">✈</div>
        <h1>Travel AI Agency</h1>
        <p>Your AI travel consultant sells your packages on the web and WhatsApp, day and night, and hands every booking to your team for payment.</p>
      </div>
      <form className="login-card" onSubmit={submit}>
        <h2>Sign in</h2>
        <label className="field">
          <span className="field-label">Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="field">
          <span className="field-label">Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <div className="error-box">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>

        {demo && (
          <div className="demo-box">
            <div className="muted small">Demo accounts (click to fill)</div>
            {DEMO_ACCOUNTS.map((a) => (
              <button type="button" key={a.email} className="demo-account"
                onClick={() => { setEmail(a.email); setPassword(a.password); }}>
                <strong>{a.label}</strong> <span className="muted">{a.email}</span>
              </button>
            ))}
            <a className="small" href="/c/sunrise-travel" target="_blank" rel="noreferrer">Open the demo customer page ↗</a>
          </div>
        )}
      </form>
    </div>
  );
}
