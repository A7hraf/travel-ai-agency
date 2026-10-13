import { FormEvent, useEffect, useState } from "react";
import { del, get, patch, post } from "../api";
import { useAuth } from "../auth";
import { Badge, ErrorBox, Field, Modal, PageHeader } from "../components/ui";
import { useI18n } from "../lang";
import type { PermissionCatalog, Role, User, UserList } from "../types";
import { dateTime, ROLE_LABELS } from "../util";

/** Shared by the company admin's team page and the system admin's company page. */
export function UserManager({ basePath, listPath, createPath }: { basePath: string; listPath: string; createPath: string }) {
  const { user: me } = useAuth();
  const { t } = useI18n();
  const [data, setData] = useState<UserList | null>(null);
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [editing, setEditing] = useState<User | "new" | null>(null);

  const load = () => get<UserList>(listPath).then(setData).catch(() => {});
  useEffect(() => {
    load();
    get<PermissionCatalog>("/api/permissions").then(setCatalog).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listPath]);

  if (!data) return <div className="loading">{t("Loading…")}</div>;
  const full = data.used >= data.max_users;
  // An employee with users.manage who is not a company admin cannot manage admin accounts.
  const delegate = !!me && me.role !== "company_admin" && me.role !== "system_admin";

  return (
    <div>
      <div className="seat-bar">
        <div className="row-between">
          <span>{t("{n} of {max} accounts used", { n: data.used, max: data.max_users })}</span>
          <button className="btn btn-primary" disabled={full} onClick={() => setEditing("new")}>+ {t("Add account")}</button>
        </div>
        <div className="meter"><div style={{ width: `${Math.min(100, (data.used / data.max_users) * 100)}%` }} /></div>
        <div className="muted small">
          {full ? t("Account limit reached. The platform admin can raise the limit.") : t("Disabled accounts don't count toward the limit.")}
        </div>
      </div>

      <div className="table-wrap">
        <table className="table cards">
          <thead><tr><th>{t("Name")}</th><th>{t("Email")}</th><th>{t("Role")}</th><th>{t("Permissions")}</th><th>{t("Status")}</th><th>{t("Last login")}</th><th /></tr></thead>
          <tbody>
            {data.users.map((u) => {
              const locked = delegate && u.role === "company_admin" && u.id !== me?.id;
              return (
                <tr key={u.id}>
                  <td data-label={t("Name")}><span><strong>{u.full_name}</strong>{u.id === me?.id && <span className="muted small"> ({t("you")})</span>}</span></td>
                  <td data-label={t("Email")}><bdi dir="ltr">{u.email}</bdi></td>
                  <td data-label={t("Role")}>{t(ROLE_LABELS[u.role])}</td>
                  <td data-label={t("Permissions")} className="small muted">{u.role === "company_admin" ? t("All") : t("{n} permissions", { n: u.permissions.length })}</td>
                  <td data-label={t("Status")}>{u.is_active ? <Badge tone="green">{t("Active")}</Badge> : <Badge tone="gray">{t("Disabled")}</Badge>}</td>
                  <td data-label={t("Last login")} className="small muted">{dateTime(u.last_login_at)}</td>
                  <td data-label="" className="cell-action">
                    {locked
                      ? <span className="muted small" title={t("Only a company admin can manage admin accounts")}>{t("Admin only")}</span>
                      : <button className="btn btn-sm" onClick={() => setEditing(u)}>{t("Edit")}</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {editing && catalog && (
        <UserForm user={editing === "new" ? null : editing} catalog={catalog} basePath={basePath} createPath={createPath}
          isSelf={editing !== "new" && editing.id === me?.id} delegate={delegate} myPermissions={me?.permissions ?? []}
          limitReached={full}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

function UserForm({ user, catalog, basePath, createPath, isSelf, delegate, myPermissions, limitReached, onClose, onSaved }: {
  user: User | null; catalog: PermissionCatalog; basePath: string; createPath: string; isSelf: boolean;
  delegate: boolean; myPermissions: string[]; limitReached: boolean;
  onClose: () => void; onSaved: () => void;
}) {
  const { t } = useI18n();
  // A delegate can only give the permissions they have themselves.
  const allowed = (p: string) => !delegate || myPermissions.includes(p);
  const defaultsFor = (r: Role) =>
    (r === "company_admin" ? Object.keys(catalog.permissions) : catalog.role_defaults[r] ?? []).filter(allowed);
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>(user?.role ?? "support");
  const [perms, setPerms] = useState<string[]>(user?.permissions ?? defaultsFor("support"));
  const [active, setActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const samePerms = (a: string[], b: string[]) => a.length === b.length && a.every((p) => b.includes(p));
  const dirty = user
    ? fullName !== user.full_name || email !== user.email || !!password || role !== user.role
      || !samePerms(perms, user.permissions) || active !== user.is_active
    : !!(fullName || email || password);
  // Re-enabling an account needs a free place within the account limit.
  const cannotReenable = !!user && !user.is_active && limitReached;

  const changeRole = (r: Role) => {
    setRole(r);
    setPerms(defaultsFor(r));
  };
  const toggle = (p: string) => setPerms(perms.includes(p) ? perms.filter((x) => x !== p) : [...perms, p]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      if (user) {
        const body: Record<string, unknown> = {};
        if (fullName !== user.full_name) body.full_name = fullName;
        if (email !== user.email) body.email = email;
        // Unchanged permissions are not sent (a delegate may not re-send permissions they don't have).
        if (!samePerms(perms, user.permissions) && !isSelf) body.permissions = perms;
        if (role !== user.role) body.role = role;
        if (active !== user.is_active) body.is_active = active;
        if (password) body.password = password;
        if (Object.keys(body).length) await patch(`${basePath}/${user.id}`, body);
      } else {
        await post(createPath, { full_name: fullName, email, password, role, permissions: perms });
      }
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!user || !confirm(t("Delete the account of {name}? This can't be undone.", { name: user.full_name }))) return;
    setBusy(true);
    try {
      await del(`${basePath}/${user.id}`);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={user ? t("Edit {name}", { name: user.full_name }) : t("New account")} onClose={onClose} wide dirty={dirty}>
      <form onSubmit={save}>
        <div className="form-grid">
          <Field label={t("Full name")}><input value={fullName} onChange={(e) => setFullName(e.target.value)} required maxLength={200} dir="auto" autoComplete="off" /></Field>
          <Field label={t("Email (login)")}><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required dir="ltr" autoComplete="off" /></Field>
          <Field label={user ? t("New password") : t("Password")} hint={user ? t("Leave empty to keep the current password") : t("8 to 72 characters")}>
            <input type="password" value={password} minLength={8} maxLength={72} autoComplete="new-password"
              onChange={(e) => setPassword(e.target.value)} required={!user} />
          </Field>
          <Field label={t("Role")}>
            <select value={role} disabled={isSelf} onChange={(e) => changeRole(e.target.value as Role)}>
              {(!delegate || role === "company_admin") && <option value="company_admin">{t("Company admin")}</option>}
              <option value="support">{t("Support")}</option>
              <option value="ticket_agent">{t("Ticket employee")}</option>
            </select>
          </Field>
        </div>

        <div className="field-label">{t("Permissions")}</div>
        {role === "company_admin" ? (
          <p className="muted small">{t("Company admins always have every permission.")}</p>
        ) : (
          <>
            {delegate && <p className="muted small">{t("You can only give permissions you have yourself.")}</p>}
            <div className="perm-grid">
              {Object.entries(catalog.permissions).map(([key, label]) => (
                <label key={key} className={`perm ${allowed(key) ? "" : "perm-locked"}`} title={key}>
                  <input type="checkbox" checked={perms.includes(key)} disabled={isSelf || !allowed(key)} onChange={() => toggle(key)} />
                  <span>{t(label)}</span>
                </label>
              ))}
            </div>
          </>
        )}

        {user && !isSelf && (
          <>
            <label className="check">
              <input type="checkbox" checked={active} disabled={cannotReenable && !active}
                onChange={(e) => setActive(e.target.checked)} /> {t("Account active (can log in)")}
            </label>
            {cannotReenable && <div className="muted small">{t("The account limit is reached: free a place (or ask the platform admin to raise the limit) before re-enabling this account.")}</div>}
            {!active && user.is_active && <div className="muted small">{t("A disabled account is logged out and no longer counts toward the account limit.")}</div>}
          </>
        )}
        <ErrorBox error={error} />
        <div className="modal-actions">
          {user && !isSelf && <button type="button" className="btn btn-danger" disabled={busy} onClick={remove}>{t("Delete account")}</button>}
          <span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : user ? t("Save") : t("Create account")}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function Users() {
  const { t } = useI18n();
  return (
    <div>
      <PageHeader title={t("Team & accounts")} subtitle={t("Create accounts for your employees and choose what each one can do.")} />
      <UserManager basePath="/api/users" listPath="/api/users" createPath="/api/users" />
    </div>
  );
}
