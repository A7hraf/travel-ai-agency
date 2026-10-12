import { FormEvent, useState } from "react";
import { post, setToken } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Field, PageHeader } from "../components/ui";
import { ROLE_LABELS } from "../util";

export default function Account() {
  const { user } = useAuth();
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
      <PageHeader title="My account" />
      <div className="card">
        <dl className="details">
          <dt>Name</dt><dd>{user.full_name}</dd>
          <dt>Email</dt><dd>{user.email}</dd>
          <dt>Role</dt><dd>{ROLE_LABELS[user.role]}</dd>
          {user.company && (<><dt>Company</dt><dd>{user.company.name}</dd></>)}
          {user.role !== "system_admin" && (<><dt>Permissions</dt><dd className="small">{user.permissions.join(", ")}</dd></>)}
        </dl>
      </div>
      <form className="card" onSubmit={submit}>
        <h3>Change password</h3>
        <Field label="Current password"><input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required /></Field>
        <Field label="New password" hint="At least 8 characters"><input type="password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required /></Field>
        <ErrorBox error={error} />
        {ok && <div className="ok-box">Password changed. Your other devices were logged out.</div>}
        <button className="btn btn-primary">Change password</button>
      </form>
    </div>
  );
}
