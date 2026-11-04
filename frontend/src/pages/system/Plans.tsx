import { FormEvent, useEffect, useState } from "react";
import { get, post, put } from "../../api";
import { PageTitle, Switch } from "../../components/admin/AdminUI";
import { Archive, ArrowCounterClockwise, Crown, PencilSimple, Plus, Star } from "../../components/Icon";
import { Money } from "../../components/Money";
import { PlanIncludes } from "../../components/plans/PlanUI";
import { ErrorBox, Field, Loading, Modal } from "../../components/ui";
import { plural, useI18n } from "../../lang";
import { BillingOverview, Plan, planDescription, planFeatures, planName } from "../../plans";

export default function Plans() {
  const { t, lang } = useI18n();
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [grace, setGrace] = useState("");
  const [graceSaved, setGraceSaved] = useState(false);
  const [graceError, setGraceError] = useState<string | null>(null);

  const [loadError, setLoadError] = useState<string | null>(null);
  const load = () => { setLoadError(null); return get<Plan[]>("/api/system/plans").then(setPlans).catch((e) => setLoadError(e.message)); };
  useEffect(() => {
    load();
    get<BillingOverview>("/api/system/billing").then((o) => { setOverview(o); setGrace(String(o.grace_days)); }).catch(() => {});
  }, []);

  const archive = async (p: Plan, archived: boolean) => {
    setBusy(p.id);
    setError(null);
    try {
      await post(`/api/system/plans/${p.id}/archive`, { archived });
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const saveGrace = async (e: FormEvent) => {
    e.preventDefault();
    setGraceError(null);
    setGraceSaved(false);
    try {
      const o = await put<BillingOverview>("/api/system/billing/settings", { grace_days: Number(grace) });
      setOverview(o);
      setGraceSaved(true);
    } catch (err) {
      setGraceError((err as Error).message);
    }
  };

  const active = (plans ?? []).filter((p) => !p.is_archived);
  const archived = (plans ?? []).filter((p) => p.is_archived);

  const card = (p: Plan) => (
    <article key={p.id} className={`pl-card ${p.is_archived ? "archived" : ""} ${p.is_default ? "default" : ""}`}>
      <header className="pl-card-head">
        <span className="pl-card-icon" aria-hidden="true"><Crown weight="duotone" /></span>
        <div className="pl-card-name">
          <h3 dir="auto">{planName(p, lang)}</h3>
          <div className="pl-card-alt" dir="auto">{lang === "ar" ? p.name : p.name_ar}</div>
        </div>
        {p.is_default && <span className="ad-status cyan"><Star weight="fill" />{t("Default for new companies")}</span>}
        {p.is_archived && <span className="ad-status off">{t("Archived")}</span>}
      </header>
      <div className="pl-prices">
        <div><span className="pl-price"><Money value={p.price_monthly} currency="OMR" /></span><span className="pl-per">{t("/ month")}</span></div>
        <div><span className="pl-price small"><Money value={p.price_yearly} currency="OMR" /></span><span className="pl-per">{t("/ year")}</span></div>
      </div>
      <p className="pl-card-meta">
        {p.trial_days ? t("{n}-day free trial", { n: p.trial_days }) : t("No trial")}
        {" · "}{plural(p.companies, "{n} company", "{n} companies")}
      </p>
      {planDescription(p, lang) && <p className="pl-desc" dir="auto">{planDescription(p, lang)}</p>}
      <PlanIncludes plan={p} />
      {planFeatures(p, lang).length > 0 && (
        <ul className="pl-features">{planFeatures(p, lang).map((f) => <li key={f} dir="auto">{f}</li>)}</ul>
      )}
      <div className="pl-card-foot">
        <button type="button" className="btn btn-sm btn-soft" onClick={() => setEditing(p)}><PencilSimple />{t("Edit")}</button>
        {p.is_archived
          ? <button type="button" className="btn btn-sm btn-ghost" disabled={busy === p.id} onClick={() => archive(p, false)}><ArrowCounterClockwise />{t("Unarchive")}</button>
          : !p.is_default && <button type="button" className="btn btn-sm btn-ghost" disabled={busy === p.id} onClick={() => archive(p, true)}><Archive />{t("Archive")}</button>}
      </div>
    </article>
  );

  return (
    <div className="pl-page">
      <PageTitle kicker={t("Platform console")} title={t("Plans")}
        subtitle={t("The plans companies can be on: prices in Omani rials, limits and features. Changes apply to every company on the plan right away.")}
        actions={<button className="btn btn-primary" onClick={() => setEditing("new")}><Plus weight="bold" />{t("New plan")}</button>} />
      <ErrorBox error={error} />
      <div className="warn-box pl-hint">{t("The first prices are placeholders: edit each plan to set your real prices and limits.")}</div>

      {plans === null ? (loadError ? <ErrorBox error={loadError} onRetry={load} /> : <Loading height={320} />) : (
        <div className="pl-grid">{active.map(card)}</div>
      )}

      <form className="ad-card pl-grace" onSubmit={saveGrace}>
        <h2 className="ad-card-title">{t("Grace period")}</h2>
        <p className="ad-card-note">{t("After a paid period ends, the AI and the customer page keep working for this many days. Then they pause until the company renews, and staff see a renewal banner. Nothing is deleted.")}</p>
        <div className="pl-grace-row">
          <Field label={t("Days")}>
            <input type="number" min={0} max={90} value={grace} onChange={(e) => { setGrace(e.target.value); setGraceSaved(false); }} required />
          </Field>
          <button className="btn btn-primary" disabled={!overview}>{t("Save")}</button>
        </div>
        <ErrorBox error={graceError} />
        {graceSaved && <div className="ok-box ad-notice" role="status">{t("Saved.")}</div>}
      </form>

      {archived.length > 0 && (<>
        <h2 className="co-section">{t("Archived plans")}<span className="count">{archived.length}</span></h2>
        <p className="muted">{t("Archived plans can't be chosen for a company any more; companies already on them keep them.")}</p>
        <div className="pl-grid">{archived.map(card)}</div>
      </>)}

      {editing && <PlanForm plan={editing === "new" ? null : editing} onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); load(); }} />}
    </div>
  );
}

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

function PlanForm({ plan, onClose, onSaved }: { plan: Plan | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({
    name: plan?.name ?? "", name_ar: plan?.name_ar ?? "",
    price_monthly: plan ? String(plan.price_monthly) : "", price_yearly: plan ? String(plan.price_yearly) : "",
    trial_days: String(plan?.trial_days ?? 14), max_users: String(plan?.max_users ?? 5),
    max_packages: plan?.max_packages == null ? "" : String(plan.max_packages),
    max_ai_conversations: plan?.max_ai_conversations == null ? "" : String(plan.max_ai_conversations),
    allow_whatsapp: plan?.allow_whatsapp ?? true, allow_instagram: plan?.allow_instagram ?? false,
    allow_page_editor: plan?.allow_page_editor ?? true, allow_remove_powered_by: plan?.allow_remove_powered_by ?? false,
    priority_support: plan?.priority_support ?? false, is_default: plan?.is_default ?? false,
    description: plan?.description ?? "", description_ar: plan?.description_ar ?? "",
    features: (plan?.features ?? []).join("\n"), features_ar: (plan?.features_ar ?? []).join("\n"),
    sort_order: String(plan?.sort_order ?? 0),
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => { setF({ ...f, [k]: v }); setDirty(true); };
  const optional = (v: string) => (v.trim() === "" ? null : Number(v));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const body = {
      ...f, price_monthly: Number(f.price_monthly), price_yearly: Number(f.price_yearly),
      trial_days: Number(f.trial_days), max_users: Number(f.max_users), max_packages: optional(f.max_packages),
      max_ai_conversations: optional(f.max_ai_conversations), features: lines(f.features),
      features_ar: lines(f.features_ar), sort_order: Number(f.sort_order || 0),
    };
    try {
      if (plan) await put(`/api/system/plans/${plan.id}`, body);
      else await post("/api/system/plans", body);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <Modal title={plan ? t("Edit plan") : t("New plan")} onClose={onClose} wide dirty={dirty}>
      <form onSubmit={submit} className="pl-form">
        <div className="ad-grid-2">
          <Field label={t("Name (English)")}><input value={f.name} onChange={(e) => set("name", e.target.value)} required maxLength={100} dir="ltr" /></Field>
          <Field label={t("Name (Arabic)")}><input value={f.name_ar} onChange={(e) => set("name_ar", e.target.value)} maxLength={100} dir="rtl" /></Field>
          <Field label={t("Monthly price (OMR)")} hint={t("Up to 3 decimals (baisa).")}>
            <input type="number" min={0} step="0.001" value={f.price_monthly} onChange={(e) => set("price_monthly", e.target.value)} required dir="ltr" />
          </Field>
          <Field label={t("Yearly price (OMR)")}>
            <input type="number" min={0} step="0.001" value={f.price_yearly} onChange={(e) => set("price_yearly", e.target.value)} required dir="ltr" />
          </Field>
          <Field label={t("Free trial (days)")} hint={t("0: no trial, new companies start active.")}>
            <input type="number" min={0} max={365} value={f.trial_days} onChange={(e) => set("trial_days", e.target.value)} required />
          </Field>
          <Field label={t("Staff accounts")}>
            <input type="number" min={1} max={10000} value={f.max_users} onChange={(e) => set("max_users", e.target.value)} required />
          </Field>
          <Field label={t("Packages")} hint={t("Empty: unlimited. Hidden packages don't count.")}>
            <input type="number" min={1} value={f.max_packages} placeholder={t("Unlimited")} onChange={(e) => set("max_packages", e.target.value)} />
          </Field>
          <Field label={t("AI conversations per month")} hint={t("Empty: unlimited. After the limit new chats go to the team.")}>
            <input type="number" min={0} value={f.max_ai_conversations} placeholder={t("Unlimited")} onChange={(e) => set("max_ai_conversations", e.target.value)} />
          </Field>
        </div>
        <h3 className="co-form-h">{t("Channels and features")}</h3>
        <p className="field-hint">{t("The website chat is always included.")}</p>
        <div className="pl-switches">
          <Switch checked={f.allow_whatsapp} onChange={(v) => set("allow_whatsapp", v)} label={t("WhatsApp")} />
          <Switch checked={f.allow_instagram} onChange={(v) => set("allow_instagram", v)} label={t("Instagram")} />
          <Switch checked={f.allow_page_editor} onChange={(v) => set("allow_page_editor", v)} label={t("Customer page editor")} />
          <Switch checked={f.allow_remove_powered_by} onChange={(v) => set("allow_remove_powered_by", v)} label={t("Hide \"Powered by Ghanjah\"")} />
          <Switch checked={f.priority_support} onChange={(v) => set("priority_support", v)} label={t("Priority support")} hint={t("A label shown to the company.")} />
          <Switch checked={f.is_default} disabled={!!plan?.is_default} onChange={(v) => set("is_default", v)}
            label={t("Default for new companies")} hint={plan?.is_default ? t("Make another plan the default to change this.") : undefined} />
        </div>
        <h3 className="co-form-h">{t("Shown to companies")}</h3>
        <div className="ad-grid-2">
          <Field label={t("Description (English)")}><textarea rows={3} value={f.description} onChange={(e) => set("description", e.target.value)} maxLength={2000} dir="ltr" /></Field>
          <Field label={t("Description (Arabic)")}><textarea rows={3} value={f.description_ar} onChange={(e) => set("description_ar", e.target.value)} maxLength={2000} dir="rtl" /></Field>
          <Field label={t("Features (English)")} hint={t("One per line.")}><textarea rows={5} value={f.features} onChange={(e) => set("features", e.target.value)} dir="ltr" /></Field>
          <Field label={t("Features (Arabic)")} hint={t("One per line.")}><textarea rows={5} value={f.features_ar} onChange={(e) => set("features_ar", e.target.value)} dir="rtl" /></Field>
          <Field label={t("Order")} hint={t("Plans are listed from the lowest number.")}>
            <input type="number" min={0} max={1000} value={f.sort_order} onChange={(e) => set("sort_order", e.target.value)} />
          </Field>
        </div>
        <ErrorBox error={error} />
        <div className="modal-actions"><span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy} aria-busy={busy}>{busy ? t("Saving…") : plan ? t("Save") : t("Create plan")}</button>
        </div>
      </form>
    </Modal>
  );
}
