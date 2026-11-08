import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../../api";
import { hueOf, initials, PageTitle, Switch } from "../../components/admin/AdminUI";
import AICheckCard from "../../components/AICheckCard";
import {
  ArrowRight, ArrowSquareOut, Buildings, ChatsCircle, Check, Copy, Globe, Plus, Sparkle, Suitcase, Ticket, UsersThree,
  WarningCircle, WhatsappLogo,
} from "../../components/Icon";
import { ErrorBox, Field, Loading, Modal } from "../../components/ui";
import { useI18n } from "../../lang";
import type { CompanyAdmin, PlatformStats } from "../../types";
import { shortDate, slugify } from "../../util";
import { Money } from "../../components/Money";
import { endText, StateBadge } from "../../components/plans/PlanUI";
import { BillingOverview, Plan, planName, SubscriptionBrief } from "../../plans";

// "Expiring" on the companies list: the paid period or trial ends within this many days.
const EXPIRING_DAYS = 14;
type SubFilter = "all" | "trial" | "active" | "past_due" | "expired" | "cancelled" | "expiring";
const FILTERS: [SubFilter, string][] = [
  ["all", "All"], ["expiring", "Expiring in 14 days"], ["trial", "Trial"], ["active", "Active [plan]"],
  ["past_due", "Payment due"], ["expired", "Expired"], ["cancelled", "Cancelled [plan]"],
];
const matchesFilter = (s: SubscriptionBrief | undefined, f: SubFilter) => {
  if (f === "all") return true;
  if (!s) return false;
  if (f === "expiring") return isExpiring(s);
  if (f === "past_due") return s.state === "past_due" || s.state === "grace";
  return s.state === f;
};
const isExpiring = (s: SubscriptionBrief) =>
  s.days_left !== null && s.days_left >= 0 && s.days_left <= EXPIRING_DAYS && s.state !== "expired";

// Same list as the server (backend/app/schemas.py).
const RESERVED_SLUGS = ["api", "app", "system", "login", "admin", "c", "static", "assets", "docs", "health", "www"];

export default function Companies() {
  const { t, lang } = useI18n();
  const [companies, setCompanies] = useState<CompanyAdmin[] | null>(null);
  const [subs, setSubs] = useState<Record<number, SubscriptionBrief>>({});
  const [billing, setBilling] = useState<BillingOverview | null>(null);
  const [filter, setFilter] = useState<SubFilter>("all");
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [creating, setCreating] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [demo, setDemo] = useState<DemoCompany | null>(null);

  const [loadError, setLoadError] = useState<string | null>(null);
  const load = () => {
    setLoadError(null);
    get<CompanyAdmin[]>("/api/system/companies").then(setCompanies).catch((e) => setLoadError((e as Error).message));
    get<PlatformStats>("/api/system/stats").then(setStats).catch((e) => setLoadError((e as Error).message));
    get<SubscriptionBrief[]>("/api/system/subscriptions")
      .then((rows) => setSubs(Object.fromEntries(rows.map((r) => [r.company_id, r])))).catch(() => {});
    get<BillingOverview>("/api/system/billing").then(setBilling).catch(() => {});
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
        actions={<>
          <button className="btn btn-soft" onClick={() => setDemoOpen(true)}><Sparkle />{t("Create demo company")}</button>
          <button className="btn btn-primary" onClick={() => setCreating(true)}><Plus weight="bold" />{t("New company")}</button>
        </>} />

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

      {billing && (
        <div className="co-billing" aria-label={t("Subscriptions")}>
          <div className="co-stat">
            <div className="co-stat-label">{t("Monthly recurring revenue")}</div>
            <div className="co-stat-value tnum"><Money value={billing.mrr} currency="OMR" /></div>
            <div className="co-stat-sub">{t("Active and payment-due plans; yearly prices ÷ 12")}</div>
            {billing.expiring_soon > 0 && (
              <button type="button" className="co-expiring" onClick={() => setFilter("expiring")}>
                {t("{n} expiring in 14 days", { n: billing.expiring_soon })}</button>
            )}
          </div>
          {([["active", "Active [plan]"], ["trial", "Trial"], ["past_due", "Payment due"], ["expired", "Expired"]] as const).map(([k, label]) => (
            <button type="button" key={k} className={`co-stat co-stat-btn ${filter === k ? "active" : ""}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>
              <div className="co-stat-label">{t(label)}</div>
              <div className="co-stat-value tnum">{billing.counts[k] ?? 0}</div>
            </button>
          ))}
        </div>
      )}

      <AICheckCard path="/api/system/ai-check" />

      <h2 className="co-section">{t("Companies")}{companies && <span className="count">{companies.length}</span>}</h2>
      {companies && companies.length > 0 && (
        <div className="co-filter" role="group" aria-label={t("Filter by plan status")}>
          {FILTERS.map(([k, label]) => (
            <button type="button" key={k} className={filter === k ? "active" : ""} aria-pressed={filter === k} onClick={() => setFilter(k)}>
              {t(label)}<span className="count">{companies.filter((c) => matchesFilter(subs[c.id], k)).length}</span>
            </button>
          ))}
        </div>
      )}
      <ErrorBox error={loadError} onRetry={load} />
      {companies === null ? (loadError ? null : <Loading height={220} />) : companies.length === 0 ? (
        <div className="empty"><Buildings className="empty-icon" /><strong>{t("No companies yet.")}</strong></div>
      ) : (
        <div className="co-grid">
          {companies.filter((c) => matchesFilter(subs[c.id], filter)).map((c) => {
            const full = c.user_count >= c.max_users;
            const sub = subs[c.id];
            const soon = !!sub && isExpiring(sub);
            return (
              <article key={c.id} className={`co-card ${c.status} ${soon ? "expiring" : ""}`}>
                <div className="co-card-head">
                  <span className="co-avatar" style={{ ["--h" as string]: hueOf(c.slug) }} aria-hidden="true">{initials(c.name)}</span>
                  <div className="co-name-wrap">
                    <h3 className="co-name" dir="auto">{c.name}</h3>
                    <bdi dir="ltr" className="co-slug">/c/{c.slug}</bdi>
                  </div>
                  {c.status === "active"
                    ? <span className="gx-status on">{t("Active [company]")}</span>
                    : <span className="gx-status bad">{t("Suspended")}</span>}
                </div>
                <div className="co-usage">
                  <div className="co-usage-row"><span>{t("Accounts")}</span><span className="tnum" dir="ltr">{c.user_count} / {c.max_users}</span></div>
                  <div className={`tm-meter ${full ? "full" : ""}`}><div style={{ width: `${Math.min(100, (c.user_count / Math.max(1, c.max_users)) * 100)}%` }} /></div>
                </div>
                {sub && (
                  <div className="co-plan">
                    <strong dir="auto">{planName({ name: sub.plan_name, name_ar: sub.plan_name_ar }, lang)}</strong>
                    <StateBadge state={sub.state} />
                    <span className={`co-renew ${soon ? "soon" : ""}`}>{endText(sub.state, sub.ends_on, t)}</span>
                  </div>
                )}
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
      {demoOpen && <CreateDemo onClose={() => setDemoOpen(false)} onCreated={(d) => { setDemoOpen(false); setDemo(d); load(); }} />}
      {demo && <DemoLogins demo={demo} onClose={() => setDemo(null)} />}
    </div>
  );
}

function CreateCompany({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { t } = useI18n();
  const { lang } = useI18n();
  const [f, setF] = useState({ name: "", slug: "", max_users: "", currency: "OMR", contact_email: "",
    admin_full_name: "", admin_email: "", admin_password: "", plan_id: "", billing_cycle: "monthly" });
  const [plans, setPlans] = useState<Plan[]>([]);
  useEffect(() => {
    get<Plan[]>("/api/system/plans").then((rows) => {
      const usable = rows.filter((p) => !p.is_archived);
      setPlans(usable);
      const def = usable.find((p) => p.is_default) ?? usable[0];
      if (def) setF((x) => (x.plan_id ? x : { ...x, plan_id: String(def.id) }));
    }).catch(() => {});
  }, []);
  const chosen = plans.find((p) => String(p.id) === f.plan_id);
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
        ...f, slug: slug || null, contact_email: f.contact_email.trim() || null,
        max_users: f.max_users.trim() ? Number(f.max_users) : null, plan_id: f.plan_id ? Number(f.plan_id) : null,
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
        <div className="gx-grid-2">
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
          <Field label={t("Plan")} hint={chosen ? (chosen.trial_days ? t("Starts with a {n}-day free trial.", { n: chosen.trial_days }) : t("Starts active for one billing period.")) : undefined}>
            <select value={f.plan_id} onChange={(e) => set("plan_id", e.target.value)}>
              {plans.map((p) => <option key={p.id} value={p.id}>{planName(p, lang)}</option>)}
            </select>
          </Field>
          <Field label={t("Billing")}>
            <select value={f.billing_cycle} onChange={(e) => set("billing_cycle", e.target.value)}>
              <option value="monthly">{t("Monthly")}</option>
              <option value="yearly">{t("Yearly")}</option>
            </select>
          </Field>
          <Field label={t("Account limit")} hint={t("Empty: follows the plan ({n} accounts). A number is this company's own limit.", { n: chosen?.max_users ?? "—" })}>
            <input type="number" min={1} max={10000} step={1} value={f.max_users} placeholder={chosen ? String(chosen.max_users) : ""} onChange={(e) => set("max_users", e.target.value)} />
          </Field>
          <Field label={t("Currency")}><input maxLength={3} pattern="[A-Za-z]{3}" title={t("3 English letters, for example OMR")} dir="ltr" value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} required /></Field>
          <Field label={t("Contact email")}><input type="email" dir="ltr" value={f.contact_email} onChange={(e) => set("contact_email", e.target.value)} /></Field>
        </div>
        <h3 className="co-form-h">{t("First admin")}</h3>
        <div className="gx-grid-2">
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

interface DemoLogin { role: string; label: string; full_name: string; email: string; password: string }
interface DemoCompany { company: CompanyAdmin; logins: DemoLogin[]; customer_page: string; counts: Record<string, number> }

/** A ready-made Omani travel agency with packages, staff, trained answers and sample activity, to present the system. */
function CreateDemo({ onClose, onCreated }: { onClose: () => void; onCreated: (d: DemoCompany) => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({ name: "Muscat Horizons Travel", slug: "", admin_email: "", language: "both", profile: "family", include_activity: true });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const preview = slugify(f.name);
  const slug = f.slug.trim();
  const reserved = !!slug && RESERVED_SLUGS.includes(slug);
  const address = slug || preview || "demo-travel";

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
      onCreated(await post<DemoCompany>("/api/system/demo-company", {
        name: f.name, slug: slug || null, admin_email: f.admin_email.trim() || null,
        language: f.language, profile: f.profile, include_activity: f.include_activity,
      }));
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <Modal title={t("Create demo company")} onClose={busy ? () => {} : onClose} wide>
      <form onSubmit={submit} className="co-form">
        <p className="muted" style={{ marginTop: 0 }}>
          {t("A ready-made travel agency in Muscat to present the system: 12 packages, 4 staff logins, trained answers, a designed customer page and, if you like, a month of sample chats and bookings. Sample customers are fictional and no WhatsApp message is sent.")}
        </p>
        <div className={`co-address ${reserved ? "bad" : ""}`} aria-live="polite">
          <Globe aria-hidden="true" />
          <bdi dir="ltr">{window.location.host}/c/<b>{address}</b></bdi>
        </div>
        <div className="gx-grid-2">
          <Field label={t("Company name")}>
            <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required minLength={2} maxLength={200} dir="auto" />
          </Field>
          <Field label={t("Web address")} hint={reserved ? <span className="error-text">{t("This web address is reserved, choose another one")}</span> : t("Letters, numbers and dashes")}>
            <input value={f.slug} placeholder={preview || "demo-travel"} dir="ltr" maxLength={80}
              className={reserved ? "invalid-soft" : ""}
              pattern="[a-z0-9]+(-[a-z0-9]+)*" title={t("English lowercase letters, digits and dashes, for example sunrise-travel.")}
              onChange={(e) => setF({ ...f, slug: e.target.value.toLowerCase().replace(/\s+/g, "-") })} />
          </Field>
          <Field label={t("Package texts")}>
            <select value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })}>
              <option value="both">{t("English and Arabic")}</option>
              <option value="en">{t("English")}</option>
              <option value="ar">{t("Arabic")}</option>
            </select>
          </Field>
          <Field label={t("Kind of agency")}>
            <select value={f.profile} onChange={(e) => setF({ ...f, profile: e.target.value })}>
              <option value="family">{t("Family travel agency")}</option>
              <option value="luxury">{t("Luxury travel & private concierge")}</option>
            </select>
          </Field>
          <Field label={t("Admin login email (optional)")} hint={t("Empty: admin@{address}.example", { address })}>
            <input type="email" dir="ltr" autoComplete="off" value={f.admin_email} onChange={(e) => setF({ ...f, admin_email: e.target.value })} />
          </Field>
        </div>
        <Switch checked={f.include_activity} onChange={(v) => setF({ ...f, include_activity: v })}
          label={t("Include sample activity")}
          hint={t("30 days of web and WhatsApp chats and bookings in every status, so the dashboard, inbox and tickets look alive.")} />
        <ErrorBox error={error} />
        <div className="modal-actions"><span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy} aria-busy={busy}><Sparkle />{busy ? t("Creating…") : t("Create demo company")}</button>
        </div>
      </form>
    </Modal>
  );
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <button type="button" className="btn btn-sm btn-soft" aria-label={`${t("Copy")}: ${label}`} onClick={() => {
      navigator.clipboard?.writeText(value).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }).catch(() => {});
    }}>{copied ? <><Check />{t("Copied")}</> : <><Copy />{t("Copy")}</>}</button>
  );
}

/** The demo logins, shown once: the passwords are not stored anywhere in plain text. */
function DemoLogins({ demo, onClose }: { demo: DemoCompany; onClose: () => void }) {
  const { t } = useI18n();
  const [saved, setSaved] = useState(false);
  const page = `${window.location.origin}${demo.customer_page}`;
  const all = [`${demo.company.name}`, `${t("Customer page")}: ${page}`, `${t("Login page")}: ${window.location.origin}/login`, "",
    ...demo.logins.map((l) => `${t(l.label)} (${l.full_name})\n${l.email}\n${l.password}`)].join("\n");
  const close = () => {
    if (!saved && !window.confirm(t("Close? The passwords will not be shown again."))) return;
    onClose();
  };

  return (
    <Modal title={t("Demo company ready")} onClose={close} wide>
      <div className="warn-box" role="alert" style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <WarningCircle weight="fill" style={{ flexShrink: 0, fontSize: 20, marginTop: 2 }} aria-hidden="true" />
        <span>{t("Save these logins now. The passwords are shown only once and can't be shown again (you can set new ones on the company page).")}</span>
      </div>
      <p className="muted">
        <bdi dir="auto"><b>{demo.company.name}</b></bdi>{" · "}
        {t("{n} packages", { n: demo.counts.packages ?? 0 })}{" · "}
        {t("{n} conversations", { n: demo.counts.conversations ?? 0 })}{" · "}
        {t("{n} tickets", { n: demo.counts.tickets ?? 0 })}
      </p>
      <div style={{ display: "grid", gap: 12 }}>
        {demo.logins.map((l) => (
          <div key={l.email} className="card" style={{ padding: 14, margin: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
              <strong>{t(l.label)}</strong><span className="muted" dir="auto">{l.full_name}</span>
            </div>
            <div className="copy-row" style={{ marginBottom: 6 }}>
              <code dir="ltr" aria-label={t("Email")}>{l.email}</code><CopyButton value={l.email} label={t("Email")} />
            </div>
            <div className="copy-row">
              <code dir="ltr" aria-label={t("Password")}>{l.password}</code><CopyButton value={l.password} label={t("Password")} />
            </div>
          </div>
        ))}
      </div>
      <div className="modal-actions" style={{ flexWrap: "wrap" }}>
        <CopyButton value={all} label={t("All logins")} />
        <a className="btn btn-sm btn-soft" href={demo.customer_page} target="_blank" rel="noopener noreferrer">
          <ArrowSquareOut />{t("Open customer page")}
        </a>
        <Link className="btn btn-sm btn-soft" to={`/system/companies/${demo.company.id}`}>{t("Manage")}<ArrowRight className="flip" /></Link>
        <span className="spacer" />
        <label className="check"><input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />{t("I saved the logins")}</label>
        <button type="button" className="btn btn-primary" onClick={close}>{t("Done")}</button>
      </div>
    </Modal>
  );
}
