import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { del, get, patch } from "../../api";
import { ConfirmSheet, hueOf, initials } from "../../components/admin/AdminUI";
import TrainingWorkspace, { type TrainingTab } from "../../components/ai/TrainingWorkspace";
import WhatsAppConnect from "../../components/ai/WhatsAppConnect";
import BrandingEditor from "../../components/BrandingEditor";
import { ArrowLeft, ArrowSquareOut, Pause, Play, Trash, WarningOctagon } from "../../components/Icon";
import { ErrorBox, Field } from "../../components/ui";
import { useI18n } from "../../lang";
import type { CompanyAdmin } from "../../types";
import { shortDate } from "../../util";
import { UserManager } from "../Users";

export default function CompanyDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [tab, setTab] = useState<"plan" | "design" | "ai" | "whatsapp">("plan");
  const [aiTab, setAiTab] = useState<TrainingTab>("answers");
  const [c, setC] = useState<CompanyAdmin | null>(null);
  const [name, setName] = useState("");
  const [maxUsers, setMaxUsers] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [topError, setTopError] = useState<string | null>(null);
  const [usersKey, setUsersKey] = useState(0);
  const [sheet, setSheet] = useState<"suspend" | "delete" | null>(null);
  const [typed, setTyped] = useState("");

  const apply = (x: CompanyAdmin) => { setC(x); setName(x.name); setMaxUsers(String(x.max_users)); };
  useEffect(() => { get<CompanyAdmin>(`/api/system/companies/${id}`).then(apply).catch((e) => setError(e.message)); }, [id]);
  if (!c) return error ? <div className="error-box">{error}</div> : <div className="skeleton" style={{ height: 300, borderRadius: 24 }} />;

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
      <header className="ad-head cd-head">
        <span className="co-avatar big" style={{ ["--h" as string]: hueOf(c.slug) }} aria-hidden="true">{initials(c.name)}</span>
        <div className="ad-head-text">
          <div className="ad-kicker">{t("Platform console")}</div>
          <h1 className="ad-title" dir="auto">{c.name}</h1>
          <p className="ad-sub cd-meta">
            {active ? <span className="ad-status on">{t("Active [company]")}</span> : <span className="ad-status bad">{t("Suspended")}</span>}
            <a href={`/c/${c.slug}`} target="_blank" rel="noreferrer"><bdi dir="ltr">/c/{c.slug}</bdi> <ArrowSquareOut /></a>
            <span>{t("Created")} {shortDate(c.created_at)}</span>
          </p>
        </div>
        <div className="ad-actions">
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
      </div>

      {tab === "ai" ? (
        <TrainingWorkspace base={`/api/system/companies/${c.id}/training`} tab={aiTab} onTab={setAiTab} />
      ) : tab === "whatsapp" ? (
        <WhatsAppConnect variant="owner" base={`/api/system/companies/${c.id}/whatsapp`} companyPath={`/api/system/companies/${c.id}`} />
      ) : tab === "design" ? (
        <BrandingEditor owner loadPath={`/api/system/companies/${c.id}/branding`} name={c.name}
          uploadPath={`/api/system/companies/${c.id}/media`} slug={c.slug} />
      ) : (<>
        <form className="ad-card" onSubmit={(e: FormEvent) => { e.preventDefault(); update("plan", { name, max_users: Number(maxUsers) }); }}>
          <h2 className="ad-card-title">{t("Plan & limits")}</h2>
          <p className="ad-card-note">{t("{a} of {b} accounts used", { a: c.user_count, b: c.max_users })}</p>
          <div className="ad-grid-2">
            <Field label={t("Company name")}><input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={200} dir="auto" /></Field>
            <Field label={t("Account limit")} hint={t("Currently {n} accounts. Disabled accounts don't count; the limit can't be lower than the active accounts.", { n: c.user_count })}>
              <input type="number" min={1} max={10000} step={1} value={maxUsers} onChange={(e) => setMaxUsers(e.target.value)} required />
            </Field>
          </div>
          <ErrorBox error={error} />
          {saved && <div className="ok-box ad-notice" role="status">{t("Saved.")}</div>}
          <div className="ad-form-actions"><button className="btn btn-primary" disabled={!!busy}>{busy === "plan" ? t("Saving…") : t("Save")}</button></div>
        </form>

        <section className="cd-accounts">
          <h2 className="co-section">{t("Accounts")}</h2>
          <UserManager key={usersKey} basePath="/api/system/users" listPath={`/api/system/companies/${c.id}/users`}
            createPath={`/api/system/companies/${c.id}/users`}
            onChanged={() => { get<CompanyAdmin>(`/api/system/companies/${id}`).then(setC).catch(() => {}); }} />
        </section>

        <section className="ad-card cd-danger">
          <h2 className="ad-card-title"><span className="ad-card-icon danger"><WarningOctagon /></span>{t("Danger zone")}</h2>
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
