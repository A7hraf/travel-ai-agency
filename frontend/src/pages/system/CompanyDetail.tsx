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
  const [usersKey, setUsersKey] = useState(0);

  const apply = (x: CompanyAdmin) => { setC(x); setName(x.name); setMaxUsers(String(x.max_users)); };
  useEffect(() => { get<CompanyAdmin>(`/api/system/companies/${id}`).then(apply).catch((e) => setError(e.message)); }, [id]);
  if (!c) return <div className="loading">{error ?? t("Loading…")}</div>;

  const update = async (body: Record<string, unknown>) => {
    setError(null);
    setSaved(false);
    try {
      apply(await patch<CompanyAdmin>(`/api/system/companies/${c.id}`, body));
      setSaved(true);
      setUsersKey((k) => k + 1);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const remove = async () => {
    const typed = prompt(t("This permanently deletes {name} with all its accounts, packages, chats and tickets.\nType the company slug \"{slug}\" to confirm:", { name: c.name, slug: c.slug }));
    if (typed !== c.slug) return;
    await del(`/api/system/companies/${c.id}`);
    navigate("/system");
  };

  return (
    <div>
      <Link to="/system" className="muted small">{t("← All companies")}</Link>
      <PageHeader title={c.name}
        subtitle={<>{t("Customer page:")} <a href={`/c/${c.slug}`} target="_blank" rel="noreferrer">/c/{c.slug}</a></>}
        actions={c.status === "active"
          ? <button className="btn btn-danger" onClick={() => update({ status: "suspended" })}>{t("Suspend company")}</button>
          : <button className="btn btn-primary" onClick={() => update({ status: "active" })}>{t("Re-activate company")}</button>} />

      {c.status === "suspended" && <div className="error-box">{t("Suspended: employees can't log in, the AI and the customer page are off.")}</div>}

      <div className="tabs page-tabs">
        <button className={`tab ${tab === "plan" ? "active" : ""}`} onClick={() => setTab("plan")}>{t("Plan & accounts")}</button>
        <button className={`tab ${tab === "design" ? "active" : ""}`} onClick={() => setTab("design")}>{t("Design & colours")}</button>
      </div>

      {tab === "design" ? (
        <BrandingEditor owner loadPath={`/api/system/companies/${c.id}/branding`}
          uploadPath={`/api/system/companies/${c.id}/media`} slug={c.slug} />
      ) : (<>
      <form className="card" onSubmit={(e: FormEvent) => { e.preventDefault(); update({ name, max_users: Number(maxUsers) }); }}>
        <h3>{t("Plan & limits")} <Badge tone={c.status === "active" ? "green" : "red"}>{t(c.status === "active" ? "Active" : "Suspended")}</Badge></h3>
        <div className="form-grid">
          <Field label={t("Company name")}><input value={name} onChange={(e) => setName(e.target.value)} required /></Field>
          <Field label={t("Maximum accounts")} hint={t("Currently using {n}.", { n: c.user_count })}>
            <input type="number" min={1} value={maxUsers} onChange={(e) => setMaxUsers(e.target.value)} required />
          </Field>
        </div>
        <ErrorBox error={error} />
        {saved && <div className="ok-box">{t("Saved.")}</div>}
        <button className="btn btn-primary">{t("Save")}</button>
      </form>

      <section className="card">
        <h3>{t("Accounts")}</h3>
        <UserManager key={usersKey} basePath="/api/system/users" listPath={`/api/system/companies/${c.id}/users`}
          createPath={`/api/system/companies/${c.id}/users`} />
      </section>

      <section className="card danger-zone">
        <h3>{t("Danger zone")}</h3>
        <button className="btn btn-danger" onClick={remove}>{t("Delete company permanently")}</button>
      </section>
      </>)}
    </div>
  );
}
