import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { del, get, patch } from "../../api";
import { ConfirmSheet, hueOf, initials, PageTitle } from "../../components/admin/AdminUI";
import TrainingWorkspace, { type TrainingTab } from "../../components/ai/TrainingWorkspace";
import InstagramConnect from "../../components/ai/InstagramConnect";
import WhatsAppConnect from "../../components/ai/WhatsAppConnect";
import BrandingEditor from "../../components/BrandingEditor";
import ActivityLog from "../../components/ActivityLog";
import B2BControls from "../../components/b2b/B2BControls";
import SubscriptionPanel from "../../components/plans/SubscriptionPanel";
import { ArrowLeft, ArrowSquareOut, Pause, Play, Trash, WarningOctagon } from "../../components/Icon";
import { ErrorBox, Field, Loading } from "../../components/ui";
import { useI18n } from "../../lang";
import type { CompanyAdmin } from "../../types";
import { shortDate } from "../../util";
import { UserManager } from "../Users";

export default function CompanyDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [tab, setTab] = useState<"plan" | "design" | "ai" | "whatsapp" | "instagram" | "b2b" | "activity">("plan");
  const [aiTab, setAiTab] = useState<TrainingTab>("answers");
  const [c, setC] = useState<CompanyAdmin | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [topError, setTopError] = useState<string | null>(null);
  const [usersKey, setUsersKey] = useState(0);
  const [sheet, setSheet] = useState<"suspend" | "delete" | null>(null);
  const [typed, setTyped] = useState("");

  const apply = (x: CompanyAdmin) => { setC(x); setName(x.name); };
  const [loadError, setLoadError] = useState<string | null>(null);
  const load = () => { setLoadError(null); get<CompanyAdmin>(`/api/system/companies/${id}`).then(apply).catch((e) => setLoadError(e.message)); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [id]);
  if (!c) return (
    <div className="cd">
      <Link to="/system" className="cd-back"><ArrowLeft className="flip" />{t("All companies")}</Link>
      <PageTitle kicker={t("Platform console")} title={t("Company")} />
      {loadError ? <ErrorBox error={loadError} onRetry={load} /> : <Loading height={300} />}
    </div>
  );

  const update = async (what: string, body: Record<string, unknown>) => {
    if (busy) return;
    setError(null);
    setTopError(null);
    setSaved(false);
    setBusy(what);
    try {
      const updated = await patch<CompanyAdmin>(`/api/system/companies/${c.id}`, body);
      // A status change must not reset unsaved edits of the plan form.
      if (what === "plan") apply(updated);
      else setC(updated);
      setSaved(what === "plan");
      setUsersKey((k) => k + 1);
    } catch (err) {
      (what === "plan" ? setError : setTopError)((err as Error).message);
    } finally {
      setBusy(null);
      setSheet(null);
    }
  };

  const remove = async () => {
    if (typed.trim() !== c.slug) return;
    setBusy("delete");
    setTopError(null);
    try {
      await del(`/api/system/companies/${c.id}`);
      navigate("/system");
    } catch (err) {
      setTopError((err as Error).message);
      setBusy(null);
      setSheet(null);
    }
  };

  const active = c.status === "active";

  return (
    <div className="cd">
      <Link to="/system" className="cd-back"><ArrowLeft className="flip" />{t("All companies")}</Link>
      <header className="gx-head cd-head">
        <span className="co-avatar big" style={{ ["--h" as string]: hueOf(c.slug) }} aria-hidden="true">{initials(c.name)}</span>
        <div className="gx-head-text">
          <div className="gx-kicker">{t("Platform console")}</div>
          <h1 className="gx-title" dir="auto">{c.name}</h1>
          <p className="gx-sub cd-meta">
            {active ? <span className="gx-status on">{t("Active [company]")}</span> : <span className="gx-status bad">{t("Suspended")}</span>}
            <a href={`/c/${c.slug}`} target="_blank" rel="noreferrer"><bdi dir="ltr">/c/{c.slug}</bdi> <ArrowSquareOut /></a>
            <span>{t("Created")} {shortDate(c.created_at)}</span>
          </p>
        </div>
        <div className="gx-actions">
          {active
            ? <button className="btn btn-danger" disabled={!!busy} onClick={() => setSheet("suspend")}><Pause weight="fill" />{busy === "status" ? t("Please wait…") : t("Suspend company")}</button>
            : <button className="btn btn-primary" disabled={!!busy} onClick={() => update("status", { status: "active" })}><Play weight="fill" />{busy === "status" ? t("Please wait…") : t("Reactivate")}</button>}
        </div>
      </header>

      <ErrorBox error={topError} />
      {!active && <div className="warn-box">{t("Suspended: employees can't log in, the AI and the customer page are off.")}</div>}

      <div className="cd-tabs ai-tabs" role="tablist" aria-label={c.name}>
        <button role="tab" aria-selected={tab === "plan"} className={tab === "plan" ? "active" : ""} onClick={() => setTab("plan")}>{t("Plan & accounts")}</button>
        <button role="tab" aria-selected={tab === "design"} className={tab === "design" ? "active" : ""} onClick={() => setTab("design")}>{t("Design & colours")}</button>
        <button role="tab" aria-selected={tab === "ai"} className={tab === "ai" ? "active" : ""} onClick={() => setTab("ai")}>{t("AI training")}</button>
        <button role="tab" aria-selected={tab === "whatsapp"} className={tab === "whatsapp" ? "active" : ""} onClick={() => setTab("whatsapp")}>{t("WhatsApp")}</button>
        <button role="tab" aria-selected={tab === "instagram"} className={tab === "instagram" ? "active" : ""} onClick={() => setTab("instagram")}>{t("Instagram")}</button>
        <button role="tab" aria-selected={tab === "b2b"} className={tab === "b2b" ? "active" : ""} onClick={() => setTab("b2b")}>{t("Business accounts")}</button>
        <button role="tab" aria-selected={tab === "activity"} className={tab === "activity" ? "active" : ""} onClick={() => setTab("activity")}>{t("Activity")}</button>
      </div>

      {tab === "ai" ? (
        <TrainingWorkspace base={`/api/system/companies/${c.id}/training`} tab={aiTab} onTab={setAiTab} />
      ) : tab === "whatsapp" ? (
        <WhatsAppConnect variant="owner" base={`/api/system/companies/${c.id}/whatsapp`} companyPath={`/api/system/companies/${c.id}`} />
      ) : tab === "b2b" ? (
        <B2BControls companyId={c.id} />
      ) : tab === "activity" ? (
        <ActivityLog path={`/api/system/companies/${c.id}/activity`} />
      ) : tab === "instagram" ? (
        <InstagramConnect variant="owner" base={`/api/system/companies/${c.id}/instagram`} />
      ) : tab === "design" ? (
        <BrandingEditor owner loadPath={`/api/system/companies/${c.id}/branding`} name={c.name}
          uploadPath={`/api/system/companies/${c.id}/media`} slug={c.slug} />
      ) : (<>
        <form className="gx-card" onSubmit={(e: FormEvent) => { e.preventDefault(); update("plan", { name }); }}>
          <h2 className="gx-card-title">{t("Company")}</h2>
          <p className="gx-card-note">{t("{a} of {b} accounts used", { a: c.user_count, b: c.max_users })}</p>
          <div className="pl-name-row">
            <Field label={t("Company name")}><input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={200} dir="auto" /></Field>
            <button className="btn btn-primary" disabled={!!busy}>{busy === "plan" ? t("Saving…") : t("Save")}</button>
          </div>
          <ErrorBox error={error} />
          {saved && <div className="ok-box gx-notice" role="status">{t("Saved.")}</div>}
        </form>

        <SubscriptionPanel companyId={c.id} onChanged={() => {
          get<CompanyAdmin>(`/api/system/companies/${id}`).then(setC).catch(() => {});
          setUsersKey((k) => k + 1);
        }} />

        <section className="cd-accounts">
          <h2 className="co-section">{t("Accounts")}</h2>
          <UserManager key={usersKey} basePath="/api/system/users" listPath={`/api/system/companies/${c.id}/users`}
            createPath={`/api/system/companies/${c.id}/users`}
            onChanged={() => { get<CompanyAdmin>(`/api/system/companies/${id}`).then(setC).catch(() => {}); }} />
        </section>

        <section className="gx-card cd-danger">
          <h2 className="gx-card-title"><span className="gx-card-icon danger"><WarningOctagon /></span>{t("Danger zone")}</h2>
          <div className="cd-danger-row">
            <div>
              <strong>{t("Delete permanently")}</strong>
              <p>{t("Deletes packages, conversations, tickets and accounts. This can't be undone.")}</p>
            </div>
            <button className="btn btn-danger" disabled={!!busy} onClick={() => { setTyped(""); setSheet("delete"); }}>
              <Trash />{busy === "delete" ? t("Deleting…") : t("Delete permanently")}
            </button>
          </div>
        </section>
      </>)}

      {sheet === "suspend" && (
        <ConfirmSheet title={t("Suspend {name}?", { name: c.name })} tone="accent" busy={busy === "status"}
          text={t("Staff are logged out and can't sign in, the customer page shows \"temporarily unavailable\", its images are hidden and the AI stops answering on WhatsApp. Nothing is deleted.")}
          confirmLabel={busy === "status" ? t("Please wait…") : t("Suspend company")}
          onConfirm={() => update("status", { status: "suspended" })} onCancel={() => setSheet(null)} />
      )}
      {sheet === "delete" && (
        <ConfirmSheet title={t("Delete {name} permanently?", { name: c.name })} tone="danger" busy={busy === "delete"}
          text={t("Deletes packages, conversations, tickets and accounts. This can't be undone.")}
          confirmLabel={busy === "delete" ? t("Deleting…") : t("Delete permanently")} confirmDisabled={typed.trim() !== c.slug}
          onConfirm={remove} onCancel={() => setSheet(null)}>
          <label className="field">
            <span className="field-label">{t("Type {slug} to confirm", { slug: c.slug })}</span>
            <input value={typed} onChange={(e) => setTyped(e.target.value)} dir="ltr" autoComplete="off" spellCheck={false}
              placeholder={c.slug} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); remove(); } }} />
          </label>
        </ConfirmSheet>
      )}
    </div>
  );
}
