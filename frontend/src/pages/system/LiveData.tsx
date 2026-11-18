import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, put } from "../../api";
import { PageTitle } from "../../components/admin/AdminUI";
import { AccountLine, type Account } from "../../components/features/LiveKeys";
import { Key } from "../../components/Icon";
import { ErrorBox, Field, Loading } from "../../components/ui";
import { useI18n } from "../../lang";

interface Data {
  keys: { serpapi: { set: boolean; account: Account | null }; viator: { set: boolean; account: null } };
  companies: { id: number; name: string; on: boolean; used: number; limit: number | null; own_serpapi: boolean; own_viator: boolean }[];
}

/** Platform owner: the central keys for live prices and photos, and each company's searches this month. */
export default function LiveData() {
  const { t } = useI18n();
  const [data, setData] = useState<Data | null>(null);
  const [serp, setSerp] = useState("");
  const [viator, setViator] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = () => get<Data>("/api/system/live-data").then((d) => { setData(d); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);
  const save = (body: Record<string, string>) => {
    setSaved(false);
    put("/api/system/live-data", body).then(() => { setSerp(""); setViator(""); setSaved(true); load(); }).catch((e) => setError((e as Error).message));
  };
  return (
    <div className="narrow gx-narrow">
      <PageTitle kicker={t("Owner console")} title={t("Live travel data")}
        subtitle={t("Real hotels and flights from Google (through SerpApi) and activities from Viator, with today's prices, photos, features and booking links, inside the AI's recommendations. Every company uses these central keys unless you give it its own on its page.")} />
      <ErrorBox error={error} onRetry={load} />
      {!data ? (!error && <Loading height={260} />) : (<>
        <form className="gx-card" onSubmit={(e: FormEvent) => { e.preventDefault(); save({ ...(serp ? { serpapi_key: serp } : {}), ...(viator ? { viator_key: viator } : {}) }); }}>
          <h2 className="gx-card-title">{t("Central keys")}</h2>
          <div className="gx-grid-2">
            <Field label={t("SerpApi key (Google Hotels and Flights)")}>
              <input type="password" autoComplete="off" dir="ltr" value={serp} onChange={(e) => setSerp(e.target.value)}
                placeholder={data.keys.serpapi.set ? t("Set: type a new key to replace it") : t("Not set")} />
            </Field>
            <Field label={t("Viator key (activities)")}>
              <input type="password" autoComplete="off" dir="ltr" value={viator} onChange={(e) => setViator(e.target.value)}
                placeholder={data.keys.viator.set ? t("Set: type a new key to replace it") : t("Not set")} />
            </Field>
          </div>
          {data.keys.serpapi.set && <p><AccountLine a={data.keys.serpapi.account} /></p>}
          <p className="muted small">{t("SerpApi has a free plan (250 searches a month) and paid plans; the Viator affiliate key is free and earns a commission on bookings made on Viator. Each AI draft uses one search per part (hotels, flights, activities). Every company gets 20 searches a month by default: change it in its Advanced features.")}</p>
          <ErrorBox error={null} />
          <div className="gx-form-actions">
            {saved && <span className="muted small">{t("Saved.")}</span>}
            {data.keys.serpapi.set && <button type="button" className="btn btn-ghost btn-sm" onClick={() => save({ serpapi_key: "" })}>{t("Remove the SerpApi key")}</button>}
            {data.keys.viator.set && <button type="button" className="btn btn-ghost btn-sm" onClick={() => save({ viator_key: "" })}>{t("Remove the Viator key")}</button>}
            <button className="btn btn-primary btn-sm" disabled={!serp && !viator}><Key />{t("Save keys")}</button>
          </div>
        </form>
        <section className="gx-card">
          <h2 className="gx-card-title">{t("Companies this month")}</h2>
          <div className="gx-seg-table"><table className="table">
            <thead><tr><th>{t("Company")}</th><th>{t("Searches")}</th><th>{t("Key")}</th></tr></thead>
            <tbody>{data.companies.map((c) => (
              <tr key={c.id}>
                <td><Link to={`/system/companies/${c.id}`}>{c.name}</Link></td>
                <td className="tnum">{!c.on ? <span className="muted">{t("Off")}</span> : c.limit === null ? t("{n} used · no limit", { n: c.used }) : `${c.used} / ${c.limit}`}</td>
                <td>{c.own_serpapi || c.own_viator ? <strong>{t("Its own key")}</strong> : <span className="muted">{t("Central")}</span>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        </section>
      </>)}
    </div>
  );
}
