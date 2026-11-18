import { FormEvent, useEffect, useState } from "react";
import { get, put } from "../../api";
import { useI18n } from "../../lang";
import { Switch } from "../admin/AdminUI";
import { Key, Lightning } from "../Icon";
import { ErrorBox, Field } from "../ui";

export interface Account { left: number | null; per_month: number | null; used: number | null; ok: boolean; error?: string }
interface CompanyLive {
  on: boolean; used: number; limit: number | null; left: number | null; own_serpapi: boolean; own_viator: boolean;
  own_account: Account | null; providers: Record<string, string>;
}

export function AccountLine({ a }: { a: Account | null | undefined }) {
  const { t } = useI18n();
  if (!a) return null;
  if (!a.ok) return <span className="small gx-cal-warn">{t("The key could not be checked")}{a.error ? `: ${a.error}` : ""}</span>;
  return <span className="small muted">{t("{n} searches left on this key", { n: a.left ?? "—" })}{a.per_month ? ` · ${t("{n} a month", { n: a.per_month })}` : ""}</span>;
}

/** Platform owner, on a company's page: its own keys (it then uses them instead of the central ones). */
export function CompanyLiveKeys({ companyId }: { companyId: number }) {
  const { t } = useI18n();
  const base = `/api/system/companies/${companyId}/live-data`;
  const [s, setS] = useState<CompanyLive | null>(null);
  const [serp, setSerp] = useState("");
  const [viator, setViator] = useState("");
  const [unlimited, setUnlimited] = useState(true);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { get<CompanyLive>(base).then((x) => { setS(x); setUnlimited(x.limit === null); }).catch((e) => setError((e as Error).message)); }, [base]);
  const save = (body: Record<string, unknown>) => {
    setSaved(false); setError(null);
    put<CompanyLive>(base, body).then((x) => { setS(x); setSerp(""); setViator(""); setSaved(true); }).catch((e) => setError((e as Error).message));
  };
  if (!s) return error ? <ErrorBox error={error} /> : null;
  return (
    <form className="gx-card" onSubmit={(e: FormEvent) => { e.preventDefault();
      save({ ...(serp ? { serpapi_key: serp } : {}), ...(viator ? { viator_key: viator } : {}), ...(serp || viator ? { unlimited } : {}) }); }}>
      <h2 className="gx-card-title"><Lightning weight="fill" /> {t("Live travel data")}</h2>
      <p className="gx-card-note">{t("Real prices, photos and booking links in the AI's recommendations. The company uses your central keys, unless you give it its own key here (for example when it buys its own plan).")}</p>
      <p className="small">{s.on
        ? (s.left === null ? t("{n} searches used this month, no monthly limit.", { n: s.used }) : t("{n} of {m} searches used this month.", { n: s.used, m: s.limit ?? 0 }))
        : t("Switched off for this company (Advanced features below).")}</p>
      <div className="gx-grid-2">
        <Field label={t("Own SerpApi key (Google Hotels and Flights)")}>
          <input type="password" autoComplete="off" value={serp} onChange={(e) => setSerp(e.target.value)} dir="ltr"
            placeholder={s.own_serpapi ? t("Set: type a new key to replace it") : t("Not set: uses your central key")} />
        </Field>
        <Field label={t("Own Viator key (activities)")}>
          <input type="password" autoComplete="off" value={viator} onChange={(e) => setViator(e.target.value)} dir="ltr"
            placeholder={s.own_viator ? t("Set: type a new key to replace it") : t("Not set: uses your central key")} />
        </Field>
      </div>
      {s.own_serpapi && <p><AccountLine a={s.own_account} /></p>}
      <Switch checked={unlimited} onChange={setUnlimited} label={t("No monthly limit while it uses its own key")}
        hint={t("Its own plan pays for its searches. You can still set a limit in Advanced features.")} />
      <ErrorBox error={error} />
      <div className="gx-form-actions">
        {saved && <span className="muted small">{t("Saved.")}</span>}
        {s.own_serpapi && <button type="button" className="btn btn-ghost btn-sm" onClick={() => save({ serpapi_key: "", unlimited: false })}>{t("Remove its SerpApi key")}</button>}
        {s.own_viator && <button type="button" className="btn btn-ghost btn-sm" onClick={() => save({ viator_key: "" })}>{t("Remove its Viator key")}</button>}
        <button className="btn btn-primary btn-sm" disabled={!serp && !viator}><Key />{t("Save keys")}</button>
      </div>
    </form>
  );
}
