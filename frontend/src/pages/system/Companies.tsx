import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../../api";
import AICheckCard from "../../components/AICheckCard";
import { Badge, Empty, ErrorBox, Field, Modal, PageHeader } from "../../components/ui";
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

  return (
    <div>
      <PageHeader title={t("Travel companies")} subtitle={t("Every company has its own accounts, packages and customers, served by the same AI brain.")}
        actions={<button className="btn btn-primary" onClick={() => setCreating(true)}>+ {t("New company")}</button>} />
      {stats && (
        <div className="stats">
          <div className="stat"><div className="stat-label">{t("Companies")}</div><div className="stat-value">{stats.active_companies}<span className="stat-of"> / {stats.companies} {t("active")}</span></div></div>
          <div className="stat"><div className="stat-label">{t("Employee accounts")}</div><div className="stat-value">{stats.users}</div></div>
          <div className="stat"><div className="stat-label">{t("Conversations")}</div><div className="stat-value">{stats.conversations}</div></div>
          <div className="stat"><div className="stat-label">{t("Booking tickets")}</div><div className="stat-value">{stats.tickets}</div></div>
        </div>
      )}
      <AICheckCard path="/api/system/ai-check" />
      {companies === null ? <div className="loading">{t("Loading…")}</div> : companies.length === 0 ? <Empty>{t("No companies yet.")}</Empty> : (
        <div className="table-wrap">
          <table className="table cards">
            <thead><tr><th>{t("Company")}</th><th>{t("Status")}</th><th>{t("Accounts")}</th><th>{t("Packages")}</th><th>{t("Open tickets")}</th><th>{t("WhatsApp")}</th><th>{t("Created")}</th><th /></tr></thead>
            <tbody>
              {companies.map((c) => (
                <tr key={c.id}>
                  <td data-label={t("Company")}><div><strong>{c.name}</strong><div className="muted small"><span dir="ltr">/c/{c.slug}</span></div></div></td>
                  <td data-label={t("Status")}>{c.status === "active" ? <Badge tone="green">{t("Active")}</Badge> : <Badge tone="red">{t("Suspended")}</Badge>}</td>
                  <td data-label={t("Accounts")}><span dir="ltr">{c.user_count} / {c.max_users}</span></td>
                  <td data-label={t("Packages")}>{c.package_count}</td>
                  <td data-label={t("Open tickets")}>{c.open_tickets}</td>
                  <td data-label={t("WhatsApp")}>{c.whatsapp_connected ? t("Connected") : <span className="muted">—</span>}</td>
                  <td data-label={t("Created")} className="small muted">{shortDate(c.created_at)}</td>
                  <td data-label="" className="cell-action"><Link className="btn btn-sm" to={`/system/companies/${c.id}`}>{t("Manage")}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
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
    <Modal title={t("New travel company")} onClose={onClose} wide dirty={dirty}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label={t("Company name")} hint={f.name.trim() ? (
            preview || slug
              ? <>{t("Customer page:")} <span dir="ltr">/c/{slug || preview}</span></>
              : <span className="error-text">{t("The name has no English letters: choose a web address in English letters below.")}</span>
          ) : undefined}>
            <input value={f.name} onChange={(e) => set("name", e.target.value)} required minLength={2} maxLength={200} dir="auto" />
          </Field>
          <Field label={slugNeeded ? `${t("Web address (slug)")} *` : t("Web address (slug)")}
            hint={reserved ? <span className="error-text">{t("This web address is reserved, choose another one")}</span>
              : slugNeeded ? t("Required. English lowercase letters, digits and dashes, for example sunrise-travel.")
              : t("Optional. English lowercase letters, digits and dashes.")}>
            <input value={f.slug} placeholder={preview || "sunrise-travel"} dir="ltr" required={slugNeeded} maxLength={80}
              pattern="[a-z0-9]+(-[a-z0-9]+)*" title={t("English lowercase letters, digits and dashes, for example sunrise-travel.")}
              onChange={(e) => set("slug", e.target.value.toLowerCase().replace(/\s+/g, "-"))} />
          </Field>
          <Field label={t("Account limit")} hint={t("How many employee accounts this company may create (admin included).")}>
            <input type="number" min={1} max={10000} step={1} value={f.max_users} onChange={(e) => set("max_users", e.target.value)} required />
          </Field>
          <Field label={t("Currency")}><input maxLength={3} pattern="[A-Za-z]{3}" title={t("3 English letters, for example OMR")} dir="ltr" value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} required /></Field>
          <Field label={t("Contact email")}><input type="email" dir="ltr" value={f.contact_email} onChange={(e) => set("contact_email", e.target.value)} /></Field>
        </div>
        <h3>{t("First company admin")}</h3>
        <div className="form-grid">
          <Field label={t("Full name")}><input value={f.admin_full_name} onChange={(e) => set("admin_full_name", e.target.value)} required minLength={2} maxLength={200} dir="auto" /></Field>
          <Field label={t("Email (login)")}><input type="email" dir="ltr" autoComplete="off" value={f.admin_email} onChange={(e) => set("admin_email", e.target.value)} required /></Field>
          <Field label={t("Temporary password")} hint={t("8 to 72 characters. Ask them to change it.")}><input minLength={8} maxLength={72} autoComplete="new-password" dir="ltr" value={f.admin_password} onChange={(e) => set("admin_password", e.target.value)} required /></Field>
        </div>
        <ErrorBox error={error} />
        <div className="modal-actions"><span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Create company")}</button>
        </div>
      </form>
    </Modal>
  );
}
