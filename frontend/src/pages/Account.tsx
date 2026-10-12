import { FormEvent, useState } from "react";
import { post, setToken } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Field, PageHeader } from "../components/ui";
import { useI18n } from "../lang";
import { PERMISSION_LABELS, ROLE_LABELS } from "../util";

export default function Account() {
  const { user } = useAuth();
  const { t } = useI18n();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  if (!user) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setOk(false);
    try {
      // Other devices are logged out; this one gets a fresh login token.
      const res = await post<{ access_token: string }>("/api/auth/change-password", { current_password: current, new_password: next });
      setToken(res.access_token);
      setOk(true);
      setCurrent("");
      setNext("");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="narrow">
      <PageHeader title={t("My account")} />
      <div className="card">
        <dl className="details">
          <dt>{t("Name")}</dt><dd>{user.full_name}</dd>
          <dt>{t("Email")}</dt><dd>{user.email}</dd>
          <dt>{t("Role")}</dt><dd>{t(ROLE_LABELS[user.role])}</dd>
          {user.company && (<><dt>{t("Company")}</dt><dd>{user.company.name}</dd></>)}
          {user.role !== "system_admin" && (<><dt>{t("Permissions")}</dt><dd className="small"><ul className="perm-list">{user.permissions.map((p) => <li key={p}>{t(PERMISSION_LABELS[p] ?? p)}</li>)}</ul></dd></>)}
        </dl>
      </div>
      <form className="card" onSubmit={submit}>
        <h3>{t("Change password")}</h3>
        <Field label={t("Current password")}><input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required /></Field>
        <Field label={t("New password")} hint={t("At least 8 characters")}><input type="password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required /></Field>
        <ErrorBox error={error} />
        {ok && <div className="ok-box">{t("Password changed. Your other devices were logged out.")}</div>}
        <button className="btn btn-primary">{t("Change password")}</button>
      </form>
    </div>
  );
}
