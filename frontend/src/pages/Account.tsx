import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, patch, post, setToken } from "../api";
import { useAuth } from "../auth";
import { ConfirmSheet, initials, PageTitle } from "../components/admin/AdminUI";
import {
  ArrowRight, Buildings, Check, DeviceMobile, GearSix, IdentificationCard, Key, ShieldCheck, Translate,
} from "../components/Icon";
import { ErrorBox, Field } from "../components/ui";
import { useI18n } from "../lang";
import type { Me, PlatformStats } from "../types";
import { dateTime, PERMISSION_LABELS, ROLE_LABELS } from "../util";

/** What each role is for, in one sentence (shown to company staff). */
const ROLE_HELP: Record<string, string> = {
  company_admin: "You manage your company: team accounts, packages, the AI and WhatsApp.",
  support: "You answer customers when the AI hands a chat over to the team.",
  ticket_agent: "You handle bookings: payments and confirmations.",
};

export default function Account() {
  const { user, refresh } = useAuth();
  const { t, lang, setLang } = useI18n();

  // Profile
  const [name, setName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [profilePassword, setProfilePassword] = useState("");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileOk, setProfileOk] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);

  // Password
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);

  // Other devices
  const [confirmLogout, setConfirmLogout] = useState(false);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [logoutOk, setLogoutOk] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  const [stats, setStats] = useState<PlatformStats | null>(null);
  const isOwner = user?.role === "system_admin";

  useEffect(() => {
    if (!user) return;
    setName(user.full_name);
    setEmail(user.email);
  }, [user?.full_name, user?.email]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (isOwner) get<PlatformStats>("/api/system/stats").then(setStats).catch(() => setStats(null));
  }, [isOwner]);

  if (!user) return null;
  const emailChanged = email.trim().toLowerCase() !== user.email.toLowerCase();
  const profileChanged = name.trim() !== user.full_name || emailChanged;

  const saveProfile = async (e: FormEvent) => {
    e.preventDefault();
    if (profileBusy) return;
    setProfileError(null);
    setProfileOk(false);
    setProfileBusy(true);
    try {
      const body: Record<string, string> = { full_name: name.trim() };
      if (emailChanged) {
        body.email = email.trim();
        body.current_password = profilePassword;
      }
      await patch<Me>("/api/auth/profile", body);
      await refresh();
      setProfilePassword("");
      setProfileOk(true);
    } catch (err) {
      setProfileError((err as Error).message);
    } finally {
      setProfileBusy(false);
    }
  };

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

  const logoutOthers = async () => {
    setLogoutBusy(true);
    setLogoutError(null);
    setLogoutOk(false);
    try {
      const res = await post<{ access_token: string }>("/api/auth/logout-others");
      setToken(res.access_token);
      setLogoutOk(true);
    } catch (err) {
      setLogoutError((err as Error).message);
    } finally {
      setLogoutBusy(false);
      setConfirmLogout(false);
    }
  };

  const permissions = user.permissions ?? [];

  return (
    <div className="narrow ad-narrow">
      <PageTitle kicker={isOwner ? t("Platform console") : t("Agency workspace")} title={t("My account")}
        subtitle={t("Your profile, password, language and sign-in safety.")} />

      {/* Profile */}
      <section className="ad-card acc-card">
        <div className="acc-head">
          <span className="acc-avatar" aria-hidden="true">{initials(user.full_name)}</span>
          <div>
            <div className="acc-name" dir="auto">{user.full_name}</div>
            <bdi dir="ltr" className="acc-email">{user.email}</bdi>
          </div>
          <span className="ad-status cyan plain">{t(ROLE_LABELS[user.role] ?? user.role)}</span>
        </div>
        <dl className="acc-details">
          <div><dt>{t("Role")}</dt><dd>
            {t(ROLE_LABELS[user.role] ?? user.role)}
            {isOwner
              ? <div className="ad-card-note" style={{ margin: "4px 0 0" }}>{t("You own the platform: you create travel companies and set the AI and WhatsApp connection for all of them.")}</div>
              : ROLE_HELP[user.role] && <div className="ad-card-note" style={{ margin: "4px 0 0" }}>{t(ROLE_HELP[user.role])}</div>}
          </dd></div>
          <div><dt>{t("Company")}</dt><dd dir="auto">{user.company ? user.company.name : t("Platform (all companies)")}</dd></div>
          <div><dt>{t("Last login")}</dt><dd>{dateTime(user.last_login_at)}</dd></div>
          <div><dt>{t("Account created")}</dt><dd>{dateTime(user.created_at)}</dd></div>
        </dl>
      </section>

      {/* Owner summary */}
      {isOwner && (
        <section className="ad-card">
          <h2 className="ad-card-title"><span className="ad-card-icon"><Buildings /></span>{t("Your platform")}</h2>
          <dl className="acc-details" style={{ marginTop: 4 }}>
            <div><dt>{t("Companies")}</dt><dd className="tnum">{stats ? t("{n} ({active} active)", { n: stats.companies, active: stats.active_companies }) : "—"}</dd></div>
            <div><dt>{t("User accounts")}</dt><dd className="tnum">{stats ? stats.users : "—"}</dd></div>
          </dl>
          <p className="ad-card-note" style={{ marginTop: 16 }}>{t("Connect the AI and WhatsApp for all companies on Platform settings.")}</p>
          <div className="ad-form-actions" style={{ flexWrap: "wrap", marginTop: 12 }}>
            <Link to="/system" className="btn btn-primary"><Buildings />{t("Companies")}</Link>
            <Link to="/system/settings" className="btn"><GearSix />{t("Platform settings")}<ArrowRight className="flip" /></Link>
          </div>
        </section>
      )}

      {/* Edit profile */}
      <form className="ad-card" onSubmit={saveProfile}>
        <h2 className="ad-card-title"><span className="ad-card-icon"><IdentificationCard /></span>{t("Your details")}</h2>
        <div className="ad-grid-2">
          <Field label={t("Full name")}>
            <input value={name} maxLength={200} required dir="auto" autoComplete="name"
              onChange={(e) => { setName(e.target.value); setProfileOk(false); }} />
          </Field>
          <Field label={t("Email (login)")} hint={t("You sign in with this email.")}>
            <input type="email" value={email} maxLength={200} required dir="ltr" autoComplete="email"
              onChange={(e) => { setEmail(e.target.value); setProfileOk(false); }} />
          </Field>
          {emailChanged && (
            <Field label={t("Current password")} hint={t("Needed to change your email.")}>
              <input type="password" value={profilePassword} required autoComplete="current-password"
                onChange={(e) => setProfilePassword(e.target.value)} />
            </Field>
          )}
        </div>
        <ErrorBox error={profileError} />
        {profileOk && <div className="ok-box ad-notice" role="status">{t("Your details were saved.")}</div>}
        <div className="ad-form-actions">
          <button className="btn btn-primary" disabled={profileBusy || !profileChanged}>{profileBusy ? t("Saving…") : t("Save details")}</button>
        </div>
      </form>

      {/* Password */}
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

      {/* Language */}
      <section className="ad-card">
        <h2 className="ad-card-title"><span className="ad-card-icon"><Translate /></span>{t("Language")}</h2>
        <p className="ad-card-note">{t("The language of the dashboard on this device.")}</p>
        <div className="seg" role="group" aria-label={t("Language")}>
          <button type="button" lang="en" className={lang === "en" ? "active" : ""} aria-pressed={lang === "en"} onClick={() => setLang("en")}>English</button>
          <button type="button" lang="ar" className={lang === "ar" ? "active" : ""} aria-pressed={lang === "ar"} onClick={() => setLang("ar")}>العربية</button>
        </div>
      </section>

      {/* Other devices */}
      <section className="ad-card">
        <h2 className="ad-card-title"><span className="ad-card-icon"><DeviceMobile /></span>{t("Devices")}</h2>
        <p className="ad-card-note">{t("Forgot to log out on another phone or computer? Log it out from here. You stay logged in on this device.")}</p>
        <ErrorBox error={logoutError} />
        {logoutOk && <div className="ok-box ad-notice" role="status">{t("All your other devices were logged out.")}</div>}
        <div className="ad-form-actions">
          <button type="button" className="btn" disabled={logoutBusy} onClick={() => setConfirmLogout(true)}>{t("Log out of all other devices")}</button>
        </div>
      </section>

      {/* Permissions (company staff) */}
      {!isOwner && (
        <section className="ad-card">
          <h2 className="ad-card-title"><span className="ad-card-icon"><ShieldCheck /></span>{t("What you can do")}</h2>
          {permissions.length ? (
            <ul className="acc-perms">{permissions.map((p) => <li key={p}><Check weight="bold" />{t(PERMISSION_LABELS[p] ?? p)}</li>)}</ul>
          ) : <p className="ad-card-note">{t("No permissions yet.")}</p>}
          <p className="ad-card-note" style={{ marginTop: 12 }}>
            {user.role === "company_admin" ? t("As company admin you have every permission.") : t("Need more access? Ask your company admin.")}
          </p>
        </section>
      )}

      {confirmLogout && (
        <ConfirmSheet
          title={t("Log out of all other devices?")}
          text={t("Every other phone, tablet and computer signed in to this account must log in again.")}
          confirmLabel={t("Log out other devices")}
          tone="danger"
          busy={logoutBusy}
          onCancel={() => setConfirmLogout(false)}
          onConfirm={logoutOthers}
        />
      )}
    </div>
  );
}
