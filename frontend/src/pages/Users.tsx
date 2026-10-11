import { FormEvent, useEffect, useState } from "react";
import { del, get, patch, post } from "../api";
import { useAuth } from "../auth";
import { Badge, ErrorBox, Field, Modal, PageHeader } from "../components/ui";
import type { PermissionCatalog, Role, User, UserList } from "../types";
import { dateTime, ROLE_LABELS } from "../util";

/** Shared by the company admin's team page and the system admin's company page. */
export function UserManager({ basePath, listPath, createPath }: { basePath: string; listPath: string; createPath: string }) {
  const { user: me } = useAuth();
  const [data, setData] = useState<UserList | null>(null);
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [editing, setEditing] = useState<User | "new" | null>(null);

  const load = () => get<UserList>(listPath).then(setData).catch(() => {});
  useEffect(() => {
    load();
    get<PermissionCatalog>("/api/permissions").then(setCatalog).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listPath]);

  if (!data) return <div className="loading">Loading…</div>;
  const full = data.used >= data.max_users;

  return (
    <div>
      <div className="seat-bar">
        <div className="row-between">
          <span><strong>{data.used}</strong> of <strong>{data.max_users}</strong> accounts used</span>
          <button className="btn btn-primary" disabled={full} onClick={() => setEditing("new")}>+ Add account</button>
        </div>
        <div className="meter"><div style={{ width: `${Math.min(100, (data.used / data.max_users) * 100)}%` }} /></div>
        {full && <div className="muted small">Account limit reached. The platform admin can raise the limit.</div>}
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Permissions</th><th>Status</th><th>Last login</th><th /></tr></thead>
          <tbody>
            {data.users.map((u) => (
              <tr key={u.id}>
                <td><strong>{u.full_name}</strong>{u.id === me?.id && <span className="muted small"> (you)</span>}</td>
                <td>{u.email}</td>
                <td>{ROLE_LABELS[u.role]}</td>
                <td className="small muted">{u.role === "company_admin" ? "All" : `${u.permissions.length} permissions`}</td>
                <td>{u.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="gray">Disabled</Badge>}</td>
                <td className="small muted">{dateTime(u.last_login_at)}</td>
                <td><button className="btn btn-sm" onClick={() => setEditing(u)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && catalog && (
        <UserForm user={editing === "new" ? null : editing} catalog={catalog} basePath={basePath} createPath={createPath}
          isSelf={editing !== "new" && editing.id === me?.id}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

function UserForm({ user, catalog, basePath, createPath, isSelf, onClose, onSaved }: {
  user: User | null; catalog: PermissionCatalog; basePath: string; createPath: string; isSelf: boolean;
  onClose: () => void; onSaved: () => void;
}) {
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>(user?.role ?? "support");
  const [perms, setPerms] = useState<string[]>(user?.permissions ?? catalog.role_defaults.support ?? []);
  const [active, setActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  const changeRole = (r: Role) => {
    setRole(r);
    setPerms(r === "company_admin" ? Object.keys(catalog.permissions) : catalog.role_defaults[r] ?? []);
  };
  const toggle = (p: string) => setPerms(perms.includes(p) ? perms.filter((x) => x !== p) : [...perms, p]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      if (user) {
        const body: Record<string, unknown> = { full_name: fullName, email, permissions: perms };
        if (role !== user.role) body.role = role;
        if (active !== user.is_active) body.is_active = active;
        if (password) body.password = password;
        await patch(`${basePath}/${user.id}`, body);
      } else {
        await post(createPath, { full_name: fullName, email, password, role, permissions: perms });
      }
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const remove = async () => {
    if (!user || !confirm(`Delete the account of ${user.full_name}? This can't be undone.`)) return;
    try {
      await del(`${basePath}/${user.id}`);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <Modal title={user ? `Edit ${user.full_name}` : "New account"} onClose={onClose} wide>
      <form onSubmit={save}>
        <div className="form-grid">
          <Field label="Full name"><input value={fullName} onChange={(e) => setFullName(e.target.value)} required /></Field>
          <Field label="Email (login)"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
          <Field label={user ? "New password" : "Password"} hint={user ? "Leave empty to keep the current password" : "At least 8 characters"}>
            <input type="password" value={password} minLength={8} onChange={(e) => setPassword(e.target.value)} required={!user} />
          </Field>
          <Field label="Role">
            <select value={role} disabled={isSelf} onChange={(e) => changeRole(e.target.value as Role)}>
              <option value="company_admin">Company admin</option>
              <option value="support">Support</option>
              <option value="ticket_agent">Ticket employee</option>
            </select>
          </Field>
        </div>

        <div className="field-label">Permissions</div>
        {role === "company_admin" ? (
          <p className="muted small">Company admins always have every permission.</p>
        ) : (
          <div className="perm-grid">
            {Object.entries(catalog.permissions).map(([key, label]) => (
              <label key={key} className="perm">
                <input type="checkbox" checked={perms.includes(key)} onChange={() => toggle(key)} />
                <span><strong>{label}</strong><span className="muted small"> {key}</span></span>
              </label>
            ))}
          </div>
        )}

        {user && !isSelf && (
          <label className="check"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Account active (can log in)</label>
        )}
        <ErrorBox error={error} />
        <div className="modal-actions">
          {user && !isSelf && <button type="button" className="btn btn-danger" onClick={remove}>Delete account</button>}
          <span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary">{user ? "Save" : "Create account"}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function Users() {
  return (
    <div>
      <PageHeader title="Team & accounts" subtitle="Create accounts for your employees and choose what each one can do." />
      <UserManager basePath="/api/users" listPath="/api/users" createPath="/api/users" />
    </div>
  );
}
