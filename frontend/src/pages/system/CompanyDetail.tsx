import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { del, get, patch } from "../../api";
import BrandingEditor from "../../components/BrandingEditor";
import { Badge, ErrorBox, Field, PageHeader } from "../../components/ui";
import { useI18n } from "../../lang";
import type { CompanyAdmin } from "../../types";
import { UserManager } from "../Users";

export default function CompanyDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [tab, setTab] = useState<"plan" | "design">("plan");
  const [c, setC] = useState<CompanyAdmin | null>(null);
  const [name, setName] = useState("");
  const [maxUsers, setMaxUsers] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [topError, setTopError] = useState<string | null>(null);
  const [usersKey, setUsersKey] = useState(0);

  const apply = (x: CompanyAdmin) => { setC(x); setName(x.name); setMaxUsers(String(x.max_users)); };
  useEffect(() => { get<CompanyAdmin>(`/api/system/companies/${id}`).then(apply).catch((e) => setError(e.message)); }, [id]);
  if (!c) return <div className="loading">{error ?? t("Loading…")}</div>;

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
    }
  };

  const suspend = () => {
    if (!confirm(t("Suspend {name}?\n\nWhile suspended:\n• its employees are logged out and can't sign in\n• the AI stops answering on the website and WhatsApp\n• the customer page is offline\n\nNothing is deleted; you can re-activate it at any time.", { name: c.name }))) return;
    update("status", { status: "suspended" });
  };

  const remove = async () => {
    const typed = prompt(t("This permanently deletes {name} with all its accounts, packages, chats and tickets.\nType the company slug \"{slug}\" to confirm:", { name: c.name, slug: c.slug }));
    if (typed === null) return;
    if (typed.trim() !== c.slug) {
      alert(t("The web address did not match. Nothing was deleted."));
      return;
    }
    setBusy("delete");
    setTopError(null);
    try {
      await del(`/api/system/companies/${c.id}`);
      navigate("/system");
    } catch (err) {
      setTopError((err as Error).message);
      setBusy(null);
    }
  };

  return (
    <div>
      <Link to="/system" className="muted small">{t("← All companies")}</Link>
      <PageHeader title={c.name}
        subtitle={<>{t("Customer page:")} <a href={`/c/${c.slug}`} target="_blank" rel="noreferrer" dir="ltr">/c/{c.slug}</a></>}
        actions={c.status === "active"
          ? <button className="btn btn-danger" disabled={!!busy} onClick={suspend}>{busy === "status" ? t("Please wait…") : t("Suspend company")}</button>
          : <button className="btn btn-primary" disabled={!!busy} onClick={() => update("status", { status: "active" })}>{busy === "status" ? t("Please wait…") : t("Re-activate company")}</button>} />

      <ErrorBox error={topError} />
      {c.status === "suspended" && <div className="error-box">{t("Suspended: employees can't log in, the AI and the customer page are off.")}</div>}

      <div className="tabs page-tabs">
        <button className={`tab ${tab === "plan" ? "active" : ""}`} onClick={() => setTab("plan")}>{t("Plan & accounts")}</button>
        <button className={`tab ${tab === "design" ? "active" : ""}`} onClick={() => setTab("design")}>{t("Design & colours")}</button>
      </div>

      {tab === "design" ? (
        <BrandingEditor owner loadPath={`/api/system/companies/${c.id}/branding`}
          uploadPath={`/api/system/companies/${c.id}/media`} slug={c.slug} />
      ) : (<>
      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault(); update("plan", { name, max_users: Number(maxUsers) }); }}>
        <h3>{t("Plan & limits")} <Badge tone={c.status === "active" ? "green" : "red"}>{t(c.status === "active" ? "Active" : "Suspended")}</Badge></h3>
        <div className="form-grid">
          <Field label={t("Company name")}><input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={200} dir="auto" /></Field>
          <Field label={t("Maximum accounts")} hint={t("Currently {n} accounts. Disabled accounts don't count; the limit can't be lower than the active accounts.", { n: c.user_count })}>
            <input type="number" min={1} max={10000} step={1} value={maxUsers} onChange={(e) => setMaxUsers(e.target.value)} required />
          </Field>
        </div>
        <ErrorBox error={error} />
        {saved && <div className="ok-box">{t("Saved.")}</div>}
        <button className="btn btn-primary" disabled={!!busy}>{busy === "plan" ? t("Saving…") : t("Save")}</button>
      </form>

      <section className="card">
        <h3>{t("Accounts")}</h3>
        <UserManager key={usersKey} basePath="/api/system/users" listPath={`/api/system/companies/${c.id}/users`}
          createPath={`/api/system/companies/${c.id}/users`} />
      </section>

      <section className="card danger-zone">
        <h3>{t("Danger zone")}</h3>
        <button className="btn btn-danger" disabled={!!busy} onClick={remove}>{busy === "delete" ? t("Deleting…") : t("Delete company permanently")}</button>
      </section>
      </>)}
    </div>
  );
}
