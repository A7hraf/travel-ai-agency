import { useEffect, useState } from "react";
import { get } from "../../api";
import { PageTitle } from "../../components/admin/AdminUI";
import { ErrorBox, Loading } from "../../components/ui";
import { useI18n } from "../../lang";

interface Place { destination: string; requests: number; booked: number; travellers: number; companies: number; value: Record<string, number>; conversion: number | null }
interface Partner { category: string; provider: string; bookings: number; companies: number; sold: number; cost: number; why: string }
interface Market {
  days: number; requests: number; companies: number;
  funnel: { requests: number; quoted: number; booked: number; conversion: number | null };
  destinations: Place[]; season: { month: string; trips: number }[]; partners: Partner[];
  lost_reasons: { reason: string; count: number }[]; booking_window_days: number | null;
  ai_learning: { suggested: number; chosen: number; chosen_rate: number | null; team_added: number };
  busiest_companies: { company: string; requests: number }[];
}
const CATEGORY: Record<string, string> = { flight: "Airline", hotel: "Hotel", activity: "Activity", transport: "Transport" };
const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);

/** Platform owner only: the market across every agency — where and when people travel, which suppliers the agencies
 *  book most (partners to negotiate with), how quotations turn into bookings and why requests are lost. */
export default function OwnerMarket() {
  const { t, lang } = useI18n();
  const [days, setDays] = useState(365);
  const [data, setData] = useState<Market | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => get<Market>(`/api/system/market?days=${days}`).then((d) => { setData(d); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { setData(null); load(); }, [days]); // eslint-disable-line react-hooks/exhaustive-deps
  const loc = lang === "ar" ? "ar-OM" : "en-GB";
  const num = (v: number) => v.toLocaleString(loc);
  const value = (v: Record<string, number>) => Object.entries(v).map(([c, n]) => `${num(Math.round(n))} ${c}`).join(" · ") || "—";
  const month = (m: string) => new Date(`${m}-15`).toLocaleDateString(loc, { month: "short", year: "2-digit" });
  const top = data ? Math.max(1, ...data.season.map((s) => s.trips)) : 1;

  return (
    <div>
      <PageTitle kicker={t("Owner console")} title={t("Market")}
        subtitle={t("Across every agency: where and when people travel, the suppliers booked most (partners to negotiate with) and why requests are lost. Totals only: never clients' names, numbers or chats.")}
        actions={<select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label={t("Period")}>
          <option value={90}>{t("Last 3 months")}</option><option value={365}>{t("Last 12 months")}</option><option value={730}>{t("Last 2 years")}</option>
        </select>} />
      <ErrorBox error={error} onRetry={load} />
      {!data ? (!error && <Loading height={300} />) : (
        <>
          <div className="gx-mk-cards">
            {([
              [t("Requests"), num(data.requests)], [t("Agencies"), num(data.companies)],
              [t("Quotations that became bookings"), pct(data.funnel.conversion)],
              [t("Usual booking window"), data.booking_window_days === null ? "—" : t("{n} days before the trip", { n: data.booking_window_days })],
              [t("AI suggestions chosen by clients"), pct(data.ai_learning.chosen_rate)],
            ] as [string, string][]).map(([k, v]) => <div key={k} className="gx-card gx-mk-card"><span className="muted small">{k}</span><strong>{v}</strong></div>)}
          </div>

          <section className="gx-card">
            <h2 className="gx-card-title">{t("Travel season")}</h2>
            <p className="muted small">{t("Trips by month of departure, across every agency.")}</p>
            {data.season.length === 0 ? <p className="muted">{t("No trips yet.")}</p> : (
              <div className="gx-mk-bars" role="img" aria-label={t("Trips by month of departure, across every agency.")}>
                {data.season.map((s) => (
                  <div key={s.month} className="gx-mk-bar" title={`${month(s.month)}: ${s.trips}`}>
                    <span className="tnum small">{s.trips}</span><i style={{ height: `${(s.trips / top) * 100}%` }} /><span className="muted small">{month(s.month)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="gx-card">
            <h2 className="gx-card-title">{t("Partner opportunities")}</h2>
            <p className="muted small">{t("Hotels, airlines and activity companies the agencies book most. Booked by several agencies: negotiate a platform rate or a commission.")}</p>
            <div className="gx-seg-table"><table className="table">
              <thead><tr><th>{t("Supplier")}</th><th>{t("Type")}</th><th>{t("Bookings")}</th><th>{t("Agencies")}</th><th>{t("Sold")}</th><th>{t("Margin")}</th></tr></thead>
              <tbody>{data.partners.map((p) => (
                <tr key={p.category + p.provider} className={p.companies >= 2 ? "gx-mk-hot" : ""}>
                  <td><bdi>{p.provider}</bdi></td><td>{t(CATEGORY[p.category] ?? "Other")}</td><td className="tnum">{num(p.bookings)}</td>
                  <td className="tnum">{num(p.companies)}</td><td className="tnum">{num(Math.round(p.sold))}</td>
                  <td className="tnum">{p.sold ? pct((p.sold - p.cost) / p.sold) : "—"}</td>
                </tr>
              ))}</tbody>
            </table></div>
            {data.partners.length === 0 && <p className="muted">{t("No booked suppliers yet.")}</p>}
          </section>

          <section className="gx-card">
            <h2 className="gx-card-title">{t("Where people travel")}</h2>
            <div className="gx-seg-table"><table className="table">
              <thead><tr><th>{t("Destination")}</th><th>{t("Requests")}</th><th>{t("Booked")}</th><th>{t("Conversion")}</th><th>{t("Travellers")}</th><th>{t("Agencies")}</th><th>{t("Value")}</th></tr></thead>
              <tbody>{data.destinations.map((d) => (
                <tr key={d.destination}><td><bdi>{d.destination}</bdi></td><td className="tnum">{num(d.requests)}</td><td className="tnum">{num(d.booked)}</td>
                  <td className="tnum">{pct(d.conversion)}</td><td className="tnum">{num(d.travellers)}</td><td className="tnum">{num(d.companies)}</td><td className="tnum">{value(d.value)}</td></tr>
              ))}</tbody>
            </table></div>
          </section>

          <div className="gx-grid-2">
            <section className="gx-card">
              <h2 className="gx-card-title">{t("Why requests are lost")}</h2>
              {data.lost_reasons.length === 0 ? <p className="muted">{t("Nothing lost in this period.")}</p> : (
                <ul className="gx-mk-list">{data.lost_reasons.map((r) => <li key={r.reason}><bdi>{t(r.reason)}</bdi><span className="tnum">{num(r.count)}</span></li>)}</ul>
              )}
            </section>
            <section className="gx-card">
              <h2 className="gx-card-title">{t("Busiest agencies")}</h2>
              <ul className="gx-mk-list">{data.busiest_companies.map((c) => <li key={c.company}><bdi>{c.company}</bdi><span className="tnum">{num(c.requests)}</span></li>)}</ul>
              <p className="muted small">{t("The AI suggested {s} options; clients chose {c}. Teams added {a} options themselves, which the AI learns from.",
                { s: data.ai_learning.suggested, c: data.ai_learning.chosen, a: data.ai_learning.team_added })}</p>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
