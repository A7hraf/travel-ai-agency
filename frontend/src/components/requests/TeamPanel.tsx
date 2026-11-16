import { useEffect, useState } from "react";
import { get } from "../../api";
import { useI18n } from "../../lang";
import { ROLE_LABELS } from "../../util";
import { moneyText } from "../Money";
import { ErrorBox, Loading } from "../ui";

interface Row {
  id: number; name: string; role: string; open: number; late: number; waiting_client: number; steps_done: number;
  avg_step_hours: number | null; collected: number; won: number; lost: number; quoted: number; approval_rate: number | null;
}

/** Each employee's open requests and their work over a period, for the people who assign requests. */
export default function TeamPanel({ onPick }: { onPick: (userId: string) => void }) {
  const { t, lang } = useI18n();
  const [days, setDays] = useState(30);
  const [data, setData] = useState<{ people: Row[]; unassigned: { open: number; late: number }; currency: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setData(null);
    get<{ people: Row[]; unassigned: { open: number; late: number }; currency: string }>(`/api/tickets/team?days=${days}`)
      .then(setData).catch((e) => setError((e as Error).message));
  }, [days]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading height={160} />;
  return (
    <section className="gx-team">
      <div className="gx-plan-head">
        <h2>{t("Team")}</h2>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label={t("Period")}>
          <option value={7}>{t("Last 7 days")}</option><option value={30}>{t("Last 30 days")}</option><option value={90}>{t("Last 90 days")}</option>
        </select>
      </div>
      <div className="gx-team-table" role="table" aria-label={t("Team")}>
        <div role="row" className="gx-team-tr gx-team-th">
          <span role="columnheader">{t("Employee")}</span><span role="columnheader">{t("Open")}</span><span role="columnheader">{t("Late")}</span>
          <span role="columnheader">{t("Steps done")}</span><span role="columnheader">{t("Usual time per step")}</span>
          <span role="columnheader">{t("Won · lost")}</span><span role="columnheader">{t("Quotes approved")}</span><span role="columnheader">{t("Collected")}</span>
        </div>
        {data.people.map((r) => (
          <button type="button" role="row" key={r.id} className="gx-team-tr" onClick={() => onPick(String(r.id))} title={t("Show their requests")}>
            <span role="cell"><strong>{r.name}</strong><small className="muted">{t(ROLE_LABELS[r.role] ?? r.role)}</small></span>
            <span role="cell">{r.open}{r.waiting_client > 0 && <small className="muted"> · {t("{n} waiting on clients", { n: r.waiting_client })}</small>}</span>
            <span role="cell" className={r.late ? "gx-bad" : ""}>{r.late}</span>
            <span role="cell">{r.steps_done}</span>
            <span role="cell">{r.avg_step_hours == null ? "—" : t("{n} h", { n: r.avg_step_hours })}</span>
            <span role="cell">{r.won} · {r.lost}</span>
            <span role="cell">{r.approval_rate == null ? "—" : `${Math.round(r.approval_rate * 100)}%`}</span>
            <span role="cell">{moneyText(r.collected, data.currency, lang)}</span>
          </button>
        ))}
        <button type="button" role="row" className="gx-team-tr" onClick={() => onPick("none")}>
          <span role="cell"><strong>{t("Unassigned")}</strong></span><span role="cell">{data.unassigned.open}</span>
          <span role="cell" className={data.unassigned.late ? "gx-bad" : ""}>{data.unassigned.late}</span>
          <span role="cell" /><span role="cell" /><span role="cell" /><span role="cell" /><span role="cell" />
        </button>
      </div>
    </section>
  );
}
