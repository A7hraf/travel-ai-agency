import { useEffect, useState } from "react";
import { get, put } from "../../api";
import { useI18n } from "../../lang";
import { Switch } from "../admin/AdminUI";
import { Sparkle } from "../Icon";
import { ErrorBox, Loading } from "../ui";
import { FeatureState, Grant, LEVEL_LABELS } from "./types";

/** Platform owner: the features and AI capabilities of one travel company, with limits, employees and prices. */
export default function FeatureControls({ companyId }: { companyId: number }) {
  const { t } = useI18n();
  const path = `/api/system/companies/${companyId}/features`;
  const [data, setData] = useState<FeatureState | null>(null);
  const [draft, setDraft] = useState<Record<string, Grant>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => { get<FeatureState>(path).then((d) => { setData(d); setDraft(d.grants); }).catch((e) => setError((e as Error).message)); }, [path]);
  if (!data) return error ? <ErrorBox error={error} /> : <Loading height={120} />;
  const set = (key: string, patch: Partial<Grant>) => { setDraft({ ...draft, [key]: { ...draft[key], ...patch } }); setSaved(false); };
  const changed = JSON.stringify(draft) !== JSON.stringify(data.grants);
  const save = async () => {
    setBusy(true); setError(null);
    try { const d = await put<FeatureState>(path, draft); setData(d); setDraft(d.grants); setSaved(true); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const num = (v: string) => (v.trim() === "" ? null : Math.max(1, Math.floor(Number(v)) || 1));
  const monthly = Object.entries(draft).filter(([, g]) => g.on && g.price).reduce((s, [, g]) => s + Number(g.price), 0);

  const row = (key: string) => {
    const f = data.catalog.find((x) => x.key === key)!;
    const g = draft[key];
    const part = f.kind === "part";
    return (
      <div key={key} className={`gx-feat ${part ? "part" : ""} ${g.on ? "on" : ""}`}>
        <div className="gx-feat-head">
          <Switch checked={g.on} disabled={busy} onChange={(v) => set(key, { on: v })}
            label={<>{f.kind === "ai" && <Sparkle weight="fill" className="gx-feat-ai" />} {t(f.label)}</>} />
          {f.metered && g.on && <span className="muted small gx-feat-use">{t("Used: {n}", { n: data.usage[key] ?? 0 })}{g.limit ? ` / ${g.limit}` : ""}</span>}
        </div>
        {g.on && !part && (
          <div className="gx-feat-opts">
            {f.metered && (
              <label>{t("Limit")}
                <span className="gx-feat-inline">
                  <input type="number" min={1} value={g.limit ?? ""} placeholder={t("No limit")} onChange={(e) => set(key, { limit: num(e.target.value) })} dir="ltr" />
                  <select value={g.period} onChange={(e) => set(key, { period: e.target.value as Grant["period"] })}>
                    <option value="month">{t("per month")}</option><option value="total">{t("in total")}</option>
                  </select>
                </span>
              </label>
            )}
            {f.kind !== "extra" && (
              <label>{t("Who may use it")}
                <span className="gx-feat-inline">
                  <select value={g.admins_only ? "admins" : g.seats != null ? "seats" : "all"} onChange={(e) => {
                    const v = e.target.value;
                    set(key, v === "admins" ? { admins_only: true, seats: null } : v === "seats" ? { admins_only: false, seats: g.seats ?? 1 } : { admins_only: false, seats: null });
                  }}>
                    <option value="all">{t("All staff")}</option>
                    <option value="admins">{t("Company admins only")}</option>
                    <option value="seats">{t("A number of employees")}</option>
                  </select>
                  {g.seats != null && !g.admins_only && (
                    <input type="number" min={1} value={g.seats} aria-label={t("Employees")} onChange={(e) => set(key, { seats: num(e.target.value) ?? 1 })} dir="ltr" />
                  )}
                </span>
              </label>
            )}
            <label>{t("Price per month")}
              <input inputMode="decimal" value={g.price ?? ""} placeholder={t("Included")} onChange={(e) => set(key, { price: e.target.value.trim() || null })} dir="ltr" />
            </label>
            {f.levels.length > 0 && (
              <fieldset className="gx-feat-levels"><legend>{key === "insights" || key === "advisor" ? t("Analytics shown") : key === "live_search" ? t("Keys it may use") : t("Capabilities given")} <small className="muted">· {t("none ticked: all")}</small></legend>
                {f.levels.map((lv) => (
                  <label key={lv} className="gx-feat-check"><input type="checkbox" checked={g.levels.includes(lv)}
                    onChange={(e) => set(key, { levels: e.target.checked ? [...g.levels, lv] : g.levels.filter((x) => x !== lv) })} />{t(LEVEL_LABELS[lv] ?? lv)}</label>
                ))}
              </fieldset>
            )}
          </div>
        )}
        {g.on && !part && data.catalog.filter((x) => x.parent === key).map((x) => row(x.key))}
      </div>
    );
  };

  return (
    <section className="gx-card">
      <h2 className="gx-card-title">{t("Features and AI")}</h2>
      <p className="gx-card-note">{t("Give this company features and AI capabilities. Limit the uses per month or in total, the number of employees who may use each one (its admin picks them), and set a monthly price.")}</p>
      <h3 className="gx-section-label">{t("Features")}</h3>
      {data.catalog.filter((f) => f.kind === "tab").map((f) => row(f.key))}
      <h3 className="gx-section-label">{t("AI capabilities")}</h3>
      {data.catalog.filter((f) => f.kind === "ai").map((f) => row(f.key))}
      <h3 className="gx-section-label">{t("Customer page and services")}</h3>
      {data.catalog.filter((f) => f.kind === "extra").map((f) => row(f.key))}
      <ErrorBox error={error} />
      <div className="gx-form-actions">
        {monthly > 0 && <span className="muted small">{t("Add-ons: {v} per month", { v: monthly.toFixed(3) })}</span>}
        {saved && !changed && <span className="muted small">{t("Saved.")}</span>}
        <button type="button" className="btn btn-primary" disabled={busy || !changed} onClick={save}>{t("Save")}</button>
      </div>
    </section>
  );
}
