import { FormEvent, useState } from "react";
import { post, setToken } from "../api";
import { useAuth } from "../auth";
import { initials, PageTitle } from "../components/admin/AdminUI";
import { Check, Key } from "../components/Icon";
import { ErrorBox, Field } from "../components/ui";
import { useI18n } from "../lang";
import { PERMISSION_LABELS, ROLE_LABELS } from "../util";

export default function Account() {
  const { user } = useAuth();
  const { t } = useI18n();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!user) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setOk(false);
    setBusy(true);
    try {
      // Other devices are logged out; this one gets a fresh login token.
      const res = await post<{ access_token: string }>("/api/auth/change-password", { current_password: current, new_password: next });
      setToken(res.access_token);
      setOk(true);
      setCurrent("");
      setNext("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="narrow ad-narrow">
      <PageTitle kicker={user.role === "system_admin" ? t("Platform console") : t("Agency workspace")} title={t("My account")} />
      <section className="ad-card acc-card">
        <div className="acc-head">
          <span className="acc-avatar" aria-hidden="true">{initials(user.full_name)}</span>
          <div>
            <div className="acc-name" dir="auto">{user.full_name}</div>
            <bdi dir="ltr" className="acc-email">{user.email}</bdi>
          </div>
          <span className="ad-status cyan plain">{t(ROLE_LABELS[user.role])}</span>
        </div>
        <dl className="acc-details">
          {user.company && (<div><dt>{t("Company")}</dt><dd dir="auto">{user.company.name}</dd></div>)}
          {user.role !== "system_admin" && (
            <div><dt>{t("Permissions")}</dt><dd>
              <ul className="acc-perms">{user.permissions.map((p) => <li key={p}><Check weight="bold" />{t(PERMISSION_LABELS[p] ?? p)}</li>)}</ul>
            </dd></div>
          )}
        </dl>
      </section>
      <form className="ad-card" onSubmit={submit}>
        <h2 className="ad-card-title"><span className="ad-card-icon"><Key /></span>{t("Change password")}</h2>
        <p className="ad-card-note">{t("Your other devices are logged out when you change it.")}</p>
        <div className="ad-grid-2">
          <Field label={t("Current password")}><input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required /></Field>
          <Field label={t("New password")} hint={t("8 to 72 characters")}><input type="password" minLength={8} maxLength={72} autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required /></Field>
        </div>
        <ErrorBox error={error} />
        {ok && <div className="ok-box ad-notice" role="status">{t("Password changed. Your other devices were logged out.")}</div>}
        <div className="ad-form-actions"><button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Change password")}</button></div>
      </form>
    </div>
  );
}
