import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../../api";
import { hueOf, initials, PageTitle } from "../../components/admin/AdminUI";
import AICheckCard from "../../components/AICheckCard";
import { ArrowRight, Buildings, ChatsCircle, Globe, Plus, Suitcase, Ticket, UsersThree, WhatsappLogo } from "../../components/Icon";
import { ErrorBox, Field, Modal } from "../../components/ui";
import { useI18n } from "../../lang";
import type { CompanyAdmin, PlatformStats } from "../../types";
import { shortDate, slugify } from "../../util";

// Same list as the server (backend/app/schemas.py).
const RESERVED_SLUGS = ["api", "app", "system", "login", "admin", "c", "static", "assets", "docs", "health", "www"];

export default function Companies() {
  const { t } = useI18n();
  const [companies, setCompanies] = useState<CompanyAdmin[] | null>(null);
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [creating, setCreating] = useState(false);

  const load = () => {
    get<CompanyAdmin[]>("/api/system/companies").then(setCompanies).catch(() => {});
    get<PlatformStats>("/api/system/stats").then(setStats).catch(() => {});
  };
  useEffect(load, []);

  const statCards = stats ? [
    { icon: <Buildings />, label: t("Companies"), value: stats.companies, sub: t("{n} active", { n: stats.active_companies }) },
    { icon: <UsersThree />, label: t("Employee accounts"), value: stats.users },
    { icon: <ChatsCircle />, label: t("Conversations"), value: stats.conversations },
    { icon: <Ticket />, label: t("Tickets"), value: stats.tickets },
  ] : [];

  return (
    <div className="co-page">
      <PageTitle kicker={t("Platform console")} title={t("Travel companies")}
        subtitle={t("Every company has its own accounts, packages and customers, served by the same AI brain.")}
        actions={<button className="btn btn-primary" onClick={() => setCreating(true)}><Plus weight="bold" />{t("New company")}</button>} />

      <div className="co-stats">
        {stats ? statCards.map((s) => (
          <div className="co-stat" key={s.label}>
            <span className="co-stat-icon" aria-hidden="true">{s.icon}</span>
            <div className="co-stat-label">{s.label}</div>
            <div className="co-stat-value tnum">{s.value}</div>
            {s.sub && <div className="co-stat-sub">{s.sub}</div>}
          </div>
        )) : [0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 118, borderRadius: 22 }} />)}
      </div>

      <AICheckCard path="/api/system/ai-check" />

      <h2 className="co-section">{t("Companies")}{companies && <span className="count">{companies.length}</span>}</h2>
      {companies === null ? <div className="skeleton" style={{ height: 220, borderRadius: 24 }} /> : companies.length === 0 ? (
        <div className="empty"><Buildings className="empty-icon" /><strong>{t("No companies yet.")}</strong></div>
      ) : (
        <div className="co-grid">
          {companies.map((c) => {
            const full = c.user_count >= c.max_users;
            return (
              <article key={c.id} className={`co-card ${c.status}`}>
                <div className="co-card-head">
                  <span className="co-avatar" style={{ ["--h" as string]: hueOf(c.slug) }} aria-hidden="true">{initials(c.name)}</span>
                  <div className="co-name-wrap">
                    <h3 className="co-name" dir="auto">{c.name}</h3>
                    <bdi dir="ltr" className="co-slug">/c/{c.slug}</bdi>
                  </div>
                  {c.status === "active"
                    ? <span className="ad-status on">{t("Active [company]")}</span>
                    : <span className="ad-status bad">{t("Suspended")}</span>}
                </div>
                <div className="co-usage">
                  <div className="co-usage-row"><span>{t("Accounts")}</span><span className="tnum" dir="ltr">{c.user_count} / {c.max_users}</span></div>
                  <div className={`tm-meter ${full ? "full" : ""}`}><div style={{ width: `${Math.min(100, (c.user_count / Math.max(1, c.max_users)) * 100)}%` }} /></div>
                </div>
                <div className="co-facts">
                  <span><Suitcase />{t("{n} packages", { n: c.package_count })}</span>
                  <span className={c.open_tickets ? "hot" : ""}><Ticket />{t("{n} open tickets", { n: c.open_tickets })}</span>
                  <span className={c.whatsapp_connected ? "wa" : "off"}><WhatsappLogo weight={c.whatsapp_connected ? "fill" : "duotone"} />
                    {c.whatsapp_connected ? t("WhatsApp connected") : t("WhatsApp not connected")}</span>
                </div>
                <div className="co-foot">
                  <span className="co-created">{t("Created")} {shortDate(c.created_at)}</span>
                  <Link className="btn btn-sm btn-soft" to={`/system/companies/${c.id}`} aria-label={`${t("Manage")}: ${c.name}`}>
                    {t("Manage")}<ArrowRight className="flip" />
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      )}
      {creating && <CreateCompany onClose={() => setCreating(false)} onCreated={() => { setCreating(false); load(); }} />}
    </div>
  );
}

function CreateCompany({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({ name: "", slug: "", max_users: "5", currency: "OMR", contact_email: "",
    admin_full_name: "", admin_email: "", admin_password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  const dirty = !!(f.name || f.slug || f.contact_email || f.admin_full_name || f.admin_email || f.admin_password);
  // The server makes the web address from the name (English letters and digits only).
  const preview = slugify(f.name);
  const slug = f.slug.trim();
  const slugNeeded = !preview && !!f.name.trim();
  const reserved = !!slug && RESERVED_SLUGS.includes(slug);
  const address = slug || preview;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (reserved) {
      setError(t("This web address is reserved, choose another one"));
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await post("/api/system/companies", {
        ...f, slug: slug || null, contact_email: f.contact_email.trim() || null, max_users: Number(f.max_users),
      });
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={t("New company")} onClose={onClose} wide dirty={dirty}>
      <form onSubmit={submit} className="co-form">
        <div className={`co-address ${slugNeeded && !slug ? "need" : ""} ${reserved ? "bad" : ""}`} aria-live="polite">
          <Globe aria-hidden="true" />
          <bdi dir="ltr">{window.location.host}/c/<b>{address || "…"}</b></bdi>
        </div>
        <div className="ad-grid-2">
          <Field label={t("Company name")}>
            <input value={f.name} onChange={(e) => set("name", e.target.value)} required minLength={2} maxLength={200} dir="auto" />
          </Field>
          <Field label={slugNeeded ? `${t("Web address")} *` : t("Web address")}
            hint={reserved ? <span className="error-text">{t("This web address is reserved, choose another one")}</span>
              : slugNeeded ? <span className="error-text">{t("Arabic names need an English web address.")}</span>
              : t("Letters, numbers and dashes")}>
            <input value={f.slug} placeholder={preview || "sunrise-travel"} dir="ltr" required={slugNeeded} maxLength={80}
              className={reserved || (slugNeeded && !slug) ? "invalid-soft" : ""}
              pattern="[a-z0-9]+(-[a-z0-9]+)*" title={t("English lowercase letters, digits and dashes, for example sunrise-travel.")}
              onChange={(e) => set("slug", e.target.value.toLowerCase().replace(/\s+/g, "-"))} />
          </Field>
          <Field label={t("Account limit")} hint={t("How many employee accounts this company may create (admin included).")}>
            <input type="number" min={1} max={10000} step={1} value={f.max_users} onChange={(e) => set("max_users", e.target.value)} required />
          </Field>
          <Field label={t("Currency")}><input maxLength={3} pattern="[A-Za-z]{3}" title={t("3 English letters, for example OMR")} dir="ltr" value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} required /></Field>
          <Field label={t("Contact email")}><input type="email" dir="ltr" value={f.contact_email} onChange={(e) => set("contact_email", e.target.value)} /></Field>
        </div>
        <h3 className="co-form-h">{t("First admin")}</h3>
        <div className="ad-grid-2">
          <Field label={t("Name")}><input value={f.admin_full_name} onChange={(e) => set("admin_full_name", e.target.value)} required minLength={2} maxLength={200} dir="auto" /></Field>
          <Field label={t("Email")}><input type="email" dir="ltr" autoComplete="off" value={f.admin_email} onChange={(e) => set("admin_email", e.target.value)} required /></Field>
          <Field label={t("Temporary password")} hint={t("8 to 72 characters. Ask them to change it.")}><input minLength={8} maxLength={72} autoComplete="new-password" dir="ltr" value={f.admin_password} onChange={(e) => set("admin_password", e.target.value)} required /></Field>
        </div>
        <ErrorBox error={error} />
        <div className="modal-actions"><span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy} aria-busy={busy}>{busy ? t("Creating…") : t("Create company")}</button>
        </div>
      </form>
    </Modal>
  );
}
