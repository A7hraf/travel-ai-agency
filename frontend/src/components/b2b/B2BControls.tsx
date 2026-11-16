import { FormEvent, useEffect, useState } from "react";
import { get, put } from "../../api";
import { useI18n } from "../../lang";
import type { B2BOverview, B2BSettings, PartnerKind } from "../../types";
import { Switch } from "../admin/AdminUI";
import { ErrorBox, Field, Loading } from "../ui";

/** Platform owner: switch business accounts on for one travel company, set limits and allowed features. */
export default function B2BControls({ companyId }: { companyId: number }) {
  const { t } = useI18n();
  const path = `/api/system/companies/${companyId}/b2b`;
  const [data, setData] = useState<B2BOverview | null>(null);
  const [s, setS] = useState<B2BSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = () => get<B2BOverview>(path).then((d) => { setData(d); setS(d.settings); setError(null); })
    .catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, [path]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!data || !s) return error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={240} />;
  const set = (patch: Partial<B2BSettings>) => { setSaved(false); setS({ ...s, ...patch }); };
  const switchOn = (v: boolean) => set(v ? { enabled: true, max_clients: s.max_clients || 5, max_vendors: s.max_vendors || 5 } : { enabled: false });
  const toggle = (f: string) => {
    const on = !s.features.includes(f);
    set({ features: on ? [...s.features, f] : s.features.filter((x) => x !== f), ...(on && !s.enabled ? { enabled: true, max_clients: s.max_clients || 5, max_vendors: s.max_vendors || 5 } : {}) });
  };
  const num = (v: string) => Math.max(0, Math.min(10000, Math.floor(Number(v) || 0)));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const d = await put<B2BOverview>(path, s);
      setData(d); setS(d.settings); setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const group = (kind: PartnerKind, title: string) => (
    <div>
      <div className="gx-section-label">{t(title)}</div>
      <div className="perm-grid">
        {Object.entries(data.catalog).filter(([f]) => f.startsWith(`${kind}.`)).map(([f, label]) => (
          <label key={f} className={`perm ${s.features.includes(f) ? "on" : ""}`}>
            <input type="checkbox" checked={s.features.includes(f)} onChange={() => toggle(f)} />
            <span>{t(label)}</span>
          </label>
        ))}
      </div>
    </div>
  );

  return (
    <form className="gx-card" onSubmit={save}>
      <h2 className="gx-card-title">{t("Business accounts")}</h2>
      <p className="gx-card-note">{t("Let this travel company open accounts for business clients (who request travel) and vendors (who arrange it). You decide how many and which features it can give them.")}</p>
      <Switch checked={s.enabled} onChange={switchOn} label={t("Business accounts switched on")}
        hint={t("When off, the company's business accounts can't sign in and the page is hidden from its staff.")} />
      <div className="form-grid">
        <Field label={t("Business clients (maximum)")} hint={t("{n} in use", { n: data.usage.clients })}>
          <input type="number" min={0} max={10000} value={s.max_clients} onChange={(e) => set({ max_clients: num(e.target.value) })} />
        </Field>
        <Field label={t("Vendors (maximum)")} hint={t("{n} in use", { n: data.usage.vendors })}>
          <input type="number" min={0} max={1000} value={s.max_vendors} onChange={(e) => set({ max_vendors: Math.min(1000, num(e.target.value)) })} />
        </Field>
        <Field label={t("Logins per account (maximum)")}>
          <input type="number" min={1} max={1000} value={s.max_users_per_partner}
            onChange={(e) => set({ max_users_per_partner: Math.max(1, Math.min(1000, num(e.target.value))) })} />
        </Field>
      </div>
      {!s.enabled && <p className="warn-box">{t("Switched off: the company can't add business clients or vendors. Tick a feature below or flip the switch, then Save.")}</p>}
      <p className="gx-card-note">{t("Features the company may give. Taking one back stops it at once for every account of this company.")}</p>
      {group("client", "Business clients")}
      {group("vendor", "Vendors")}
      <ErrorBox error={error} />
      <div className="modal-actions">
        {saved && <span className="ok-box gx-notice">{t("Saved.")}</span>}
        <span className="spacer" />
        <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Save")}</button>
      </div>
    </form>
  );
}
