import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../../api";
import { PageTitle } from "../../components/admin/AdminUI";
import ReportCard, { type Report } from "../../components/insights/ReportCard";
import { ErrorBox, Loading } from "../../components/ui";
import { useI18n } from "../../lang";
import { dateTime } from "../../util";

interface Row {
  id: number; name: string; slug: string; status: string; plan: string | null; staff: number; chats_30d: number; bookings_30d: number;
  paid_30d: number; revenue_30d: number; conversion: number | null; handover_rate: number | null; rating: number | null;
  repeat_customers: number; last_activity: string | null; addons: string[]; b2b: boolean; opportunities: string[];
}
interface Overview { totals: { companies: number; active: number; chats_30d: number; bookings_30d: number; revenue_30d_of_agencies: number; at_risk: number; addon_use: Record<string, number> }; companies: Row[] }

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);

/** Platform owner: how every agency is doing, who to help or upsell, and the AI's strategy report. */
export default function OwnerInsights() {
  const { t } = useI18n();
  const [data, setData] = useState<{ metrics: Overview; report: Report | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => get<{ metrics: Overview; report: Report | null }>("/api/system/insights").then((d) => { setData(d); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);
  const head = <PageTitle kicker={t("Owner console")} title={t("Insights")}
    subtitle={t("Every agency's last 30 days, who needs help or an upgrade, and what to build and market next. Totals only: never customers' chats or names.")} />;
  if (!data) return <div>{head}{error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={300} />}</div>;
  const { totals, companies } = data.metrics;
  const cards: [string, string][] = [
    [t("Active agencies"), `${totals.active} / ${totals.companies}`], [t("Chats (30 days)"), String(totals.chats_30d)],
    [t("Bookings (30 days)"), String(totals.bookings_30d)], [t("At risk"), String(totals.at_risk)],
  ];
  return (
    <div>
      {head}
      <div className="gx-b2b-meters">{cards.map(([l, v]) => <div key={l} className="gx-b2b-meter"><div className="muted small">{l}</div><div className="gx-b2b-num tnum">{v}</div></div>)}</div>
      <section className="gx-card">
        <h2 className="gx-card-title">{t("Agencies")}</h2>
        <div className="table-wrap">
          <table className="table">
            <thead><tr>
              <th>{t("Agency")}</th><th>{t("Plan")}</th><th>{t("Chats")}</th><th>{t("Bookings")}</th><th>{t("Conversion")}</th>
              <th>{t("Handed over")}</th><th>{t("Rating")}</th><th>{t("Last activity")}</th><th>{t("What to do")}</th>
            </tr></thead>
            <tbody>
              {companies.map((r) => (
                <tr key={r.id} className={r.status !== "active" ? "off" : ""}>
                  <td><Link to={`/system/companies/${r.id}`} dir="auto">{r.name}</Link>{r.addons.length > 0 && <div className="muted small">{r.addons.join(" · ")}</div>}</td>
                  <td>{r.plan ?? "—"}</td><td className="tnum">{r.chats_30d}</td><td className="tnum">{r.bookings_30d}</td>
                  <td className="tnum">{pct(r.conversion)}</td><td className="tnum">{pct(r.handover_rate)}</td>
                  <td className="tnum">{r.rating ?? "—"}</td><td className="small">{r.last_activity ? dateTime(r.last_activity) : "—"}</td>
                  <td className="small">{r.opportunities.length ? <ul className="gx-tips">{r.opportunities.map((o) => <li key={o}>{t(o)}</li>)}</ul> : <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <ReportCard report={data.report} path="/api/system/insights/report" title={t("The AI's strategy report")}
        note={t("From the totals above: which agencies to act on, trends in the travel business, features to build next and how to market the platform.")}
        onNew={(r) => setData({ ...data, report: r })} />
    </div>
  );
}
