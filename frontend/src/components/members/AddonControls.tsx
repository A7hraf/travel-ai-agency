import { useEffect, useState } from "react";
import { get, put } from "../../api";
import { useI18n } from "../../lang";
import { Switch } from "../admin/AdminUI";
import { ErrorBox, Loading } from "../ui";

interface Addons { addons: Record<string, boolean>; catalog: Record<string, string> }

/** Platform owner: advanced features of one travel company, each switched on or off. */
export default function AddonControls({ companyId }: { companyId: number }) {
  const { t } = useI18n();
  const path = `/api/system/companies/${companyId}/addons`;
  const [data, setData] = useState<Addons | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { get<Addons>(path).then(setData).catch((e) => setError((e as Error).message)); }, [path]);
  if (!data) return error ? <ErrorBox error={error} /> : <Loading height={120} />;
  const toggle = async (key: string, on: boolean) => {
    setBusy(true);
    setError(null);
    try { setData(await put<Addons>(path, { ...data.addons, [key]: on })); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <section className="gx-card">
      <h2 className="gx-card-title">{t("Advanced features")}</h2>
      <p className="gx-card-note">{t("Switch features on or off for this company only. Its staff see them after their next page load.")}</p>
      {Object.entries(data.catalog).map(([key, label]) => (
        <Switch key={key} checked={!!data.addons[key]} disabled={busy} onChange={(v) => toggle(key, v)} label={t(label)} />
      ))}
      <ErrorBox error={error} />
    </section>
  );
}
