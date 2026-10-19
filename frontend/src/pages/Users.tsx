import { FormEvent, useEffect, useState } from "react";
import { del, get, patch, post } from "../api";
import { useAuth } from "../auth";
import { ConfirmSheet, initials, PageTitle, Switch } from "../components/admin/AdminUI";
import { LockSimple, PencilSimple, Plus, Trash } from "../components/Icon";
import { ErrorBox, Field, Modal } from "../components/ui";
import { useI18n } from "../lang";
import type { PermissionCatalog, Role, User, UserList } from "../types";
import { dateTime, ROLE_LABELS } from "../util";

/** Shared by the company admin's team page and the system admin's company page. */
export function UserManager({ basePath, listPath, createPath, onChanged }: {
  basePath: string; listPath: string; createPath: string;
  /** Called after an account was added, changed or deleted (the owner's company page refreshes its counts). */
  onChanged?: () => void;
}) {
  const { user: me } = useAuth();
  const { t } = useI18n();
  const [data, setData] = useState<UserList | null>(null);
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [editing, setEditing] = useState<User | "new" | null>(null);

  const load = () => get<UserList>(listPath).then(setData).catch(() => {});
  const changed = () => { load(); onChanged?.(); };
  useEffect(() => {
    load();
    get<PermissionCatalog>("/api/permissions").then(setCatalog).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listPath]);

  if (!data) return <div className="skeleton" style={{ height: 240, borderRadius: 24 }} />;
  const full = data.used >= data.max_users;
  // An employee with users.manage who is not a company admin cannot manage admin accounts.
  const delegate = !!me && me.role !== "company_admin" && me.role !== "system_admin";

  const pct = Math.min(100, (data.used / Math.max(1, data.max_users)) * 100);
  return (
    <div className="tm">
      <div className="tm-seats">
        <div className="tm-seats-num">
          <span className="tnum">{data.used}</span><span className="tm-of"> / {data.max_users}</span>
        </div>
        <div className="tm-seats-main">
          <div className="tm-seats-label">{t("{n} of {max} accounts used", { n: data.used, max: data.max_users })}</div>
          <div className={`tm-meter ${full ? "full" : ""}`} role="meter" aria-valuemin={0} aria-valuemax={data.max_users} aria-valuenow={data.used}
            aria-label={t("Accounts used")}><div style={{ width: `${pct}%` }} /></div>
          <div className="tm-seats-note">
            {full ? t("Account limit reached. The platform admin can raise the limit.") : t("Disabled accounts don't count toward the limit.")}
          </div>
        </div>
        <button className="btn btn-primary" disabled={full} onClick={() => setEditing("new")}><Plus weight="bold" />{t("Add account")}</button>
      </div>

      <ul className="tm-list">
        {data.users.map((u) => {
          // A delegate can't manage admins, nor colleagues who have a permission the delegate lacks.
          const lockedReason = !delegate || u.id === me?.id ? null
            : u.role === "company_admin" ? "Only a company admin can manage admin accounts"
            : u.permissions.some((p) => !(me?.permissions ?? []).includes(p))
              ? "Only a company admin can manage an account with permissions you don't have" : null;
          const locked = !!lockedReason;
          return (
            <li key={u.id} className={`tm-row ${u.is_active ? "" : "off"}`}>
              <span className={`tm-avatar role-${u.role}`} aria-hidden="true">{initials(u.full_name)}</span>
              <div className="tm-who">
                <div className="tm-name" dir="auto">{u.full_name}{u.id === me?.id && <span className="tm-you">{t("you")}</span>}</div>
                <bdi dir="ltr" className="tm-email">{u.email}</bdi>
              </div>
              <div className="tm-role">
                <span className="ad-status cyan plain">{t(ROLE_LABELS[u.role])}</span>
                <span className="tm-perms">{u.role === "company_admin" ? t("All permissions") : t("{n} permissions", { n: u.permissions.length })}</span>
              </div>
              <div className="tm-state">
                {u.is_active ? <span className="ad-status on">{t("Active")}</span> : <span className="ad-status off">{t("Disabled")}</span>}
                <span className="tm-login">{t("Last login")}: {dateTime(u.last_login_at)}</span>
              </div>
              <div className="tm-action">
                {locked
                  ? <span className="tm-locked" title={t(lockedReason ?? "")}><LockSimple />{t("Admin only")}</span>
                  : <button className="btn btn-sm btn-soft" onClick={() => setEditing(u)} aria-label={t("Edit {name}", { name: u.full_name })}><PencilSimple />{t("Edit")}</button>}
              </div>
            </li>
          );
        })}
      </ul>

      {editing && catalog && (
        <UserForm user={editing === "new" ? null : editing} catalog={catalog} basePath={basePath} createPath={createPath}
          isSelf={editing !== "new" && editing.id === me?.id} delegate={delegate} myPermissions={me?.permissions ?? []}
          limitReached={full}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); changed(); }} />
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
  const [confirmDelete, setConfirmDelete] = useState(false);
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
    if (!user) return;
    setBusy(true);
    try {
      await del(`${basePath}/${user.id}`);
      setConfirmDelete(false);
      onSaved();
    } catch (err) {
      setConfirmDelete(false);
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
          {isSelf ? (
            // Your own password is changed on My account, which asks for the current one.
            <Field label={t("Password")} hint={t("Change your own password on the My account page.")}>
              <input type="password" value="" disabled placeholder="••••••••" />
            </Field>
          ) : (
            <Field label={user ? t("New password") : t("Password")} hint={user ? t("Leave empty to keep the current password") : t("8 to 72 characters")}>
              <input type="password" value={password} minLength={8} maxLength={72} autoComplete="new-password"
                onChange={(e) => setPassword(e.target.value)} required={!user} />
            </Field>
          )}
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
                <label key={key} className={`perm ${allowed(key) ? "" : "perm-locked"} ${perms.includes(key) ? "on" : ""}`} title={key}>
                  <input type="checkbox" checked={perms.includes(key)} disabled={isSelf || !allowed(key)} onChange={() => toggle(key)} />
                  <span>{t(label)}</span>
                </label>
              ))}
            </div>
          </>
        )}

        {user && !isSelf && (
          <>
            <Switch checked={active} disabled={cannotReenable && !active} onChange={setActive} label={t("Account active (can log in)")} />
            {cannotReenable && <div className="muted small">{t("The account limit is reached: free a place (or ask the platform admin to raise the limit) before re-enabling this account.")}</div>}
            {!active && user.is_active && <div className="muted small">{t("A disabled account is logged out and no longer counts toward the account limit.")}</div>}
          </>
        )}
        <ErrorBox error={error} />
        <div className="modal-actions">
          {user && !isSelf && <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setConfirmDelete(true)}><Trash />{t("Delete account")}</button>}
          <span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : user ? t("Save") : t("Create account")}</button>
        </div>
      </form>
      {confirmDelete && user && (
        <ConfirmSheet title={t("Delete the account of {name}?", { name: user.full_name })} text={t("This can't be undone.")}
          tone="danger" busy={busy} confirmLabel={busy ? t("Deleting…") : t("Delete account")}
          onConfirm={remove} onCancel={() => setConfirmDelete(false)} />
      )}
    </Modal>
  );
}

export default function Users() {
  const { t } = useI18n();
  return (
    <div>
      <PageTitle kicker={t("Agency workspace")} title={t("Team & accounts")} subtitle={t("Create accounts for your employees and choose what each one can do.")} />
      <UserManager basePath="/api/users" listPath="/api/users" createPath="/api/users" />
    </div>
  );
}
