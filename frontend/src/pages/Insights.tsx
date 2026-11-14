import { useEffect, useState } from "react";
import { get } from "../api";
import { PageTitle } from "../components/admin/AdminUI";
import ReportCard, { type Report } from "../components/insights/ReportCard";
import { moneyText } from "../components/Money";
import { ErrorBox, Loading } from "../components/ui";
import { useI18n } from "../lang";

interface Learned { provider: string; suggested: number; sent: number; removed: number; chosen: number }
interface Metrics {
  days: number; currency: string;
  chats: { total: number; by_channel: Record<string, number>; handed_to_staff: number; handover_rate: number | null };
  customers: { new: number; chatted: number; booked: number; conversion_rate: number | null };
  bookings: { total: number; paid_or_confirmed: number; revenue: number; average_value: number | null; cancelled: number };
  packages: { active: number; top_booked: [string, number][]; never_booked: string[] };
  feedback: { average: number | null; count: number };
  members: Record<string, number>;
  trip_requests: { total: number; business: number; individual: number; margin: number };
  ai_learned: Record<string, Learned[]>;
  customers_searched_for?: [string, number][];
  low_ratings?: { rating: number; comment: string | null }[];
}

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);

export function MetricCards({ m }: { m: Metrics }) {
  const { t, lang } = useI18n();
  const cards: [string, string, string?][] = [
    [t("Chats"), String(m.chats.total), t("{p} handed to staff", { p: pct(m.chats.handover_rate) })],
    [t("Customers who booked"), `${m.customers.booked} / ${m.customers.chatted}`, t("Conversion {p}", { p: pct(m.customers.conversion_rate) })],
    [t("Paid bookings"), String(m.bookings.paid_or_confirmed), t("{n} cancelled", { n: m.bookings.cancelled })],
    [t("Revenue"), moneyText(m.bookings.revenue, m.currency, lang), m.bookings.average_value !== null ? t("Average {v}", { v: moneyText(m.bookings.average_value, m.currency, lang) }) : undefined],
    [t("Rating"), m.feedback.average !== null ? `${m.feedback.average} / 5` : "—", t("{n} ratings", { n: m.feedback.count })],
    [t("Trip requests"), String(m.trip_requests.total), t("Margin {v}", { v: moneyText(m.trip_requests.margin, m.currency, lang) })],
  ];
  return (
    <div className="gx-b2b-meters gx-insight-cards">
      {cards.map(([label, value, sub]) => (
        <div key={label} className="gx-b2b-meter"><div className="muted small">{label}</div><div className="gx-b2b-num tnum">{value}</div>{sub && <div className="muted small">{sub}</div>}</div>
      ))}
    </div>
  );
}

export default function Insights() {
  const { t } = useI18n();
  const [data, setData] = useState<{ metrics: Metrics; report: Report | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => get<{ metrics: Metrics; report: Report | null }>("/api/insights").then((d) => { setData(d); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);
  const head = <PageTitle kicker={t("Agency workspace")} title={t("AI insights")}
    subtitle={t("Your business over the last 90 days, what your customers want, and a growth plan written by the AI.")} />;
  if (!data) return <div>{head}{error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={300} />}</div>;
  const m = data.metrics;
  const learned = Object.entries(m.ai_learned).filter(([, rows]) => rows.some((r) => r.chosen || r.sent));
  return (
    <div>
      {head}
      <MetricCards m={m} />
      <div className="gx-insight-grid">
        <section className="gx-card">
          <h2 className="gx-card-title">{t("What customers search for")}</h2>
          {(m.customers_searched_for ?? []).length === 0 ? <p className="muted">{t("Not enough chats yet.")}</p> : (
            <div className="gx-parts">{m.customers_searched_for!.map(([w, n]) => <span key={w} className="gx-part" dir="auto">{w} · {n}</span>)}</div>
          )}
          <h3 className="gx-insight-h3">{t("Most booked packages")}</h3>
          {m.packages.top_booked.length === 0 ? <p className="muted small">—</p> : <ol className="gx-insight-list">{m.packages.top_booked.map(([title, n]) => <li key={title} dir="auto">{title} · {n}</li>)}</ol>}
          {m.packages.never_booked.length > 0 && (<>
            <h3 className="gx-insight-h3">{t("Packages nobody booked")}</h3>
            <p className="muted small" dir="auto">{m.packages.never_booked.join(" · ")}</p>
          </>)}
        </section>
        <section className="gx-card">
          <h2 className="gx-card-title">{t("What the AI planner learned")}</h2>
          {learned.length === 0 ? <p className="muted">{t("Nothing yet: it learns from the options your team sends and your clients choose.")}</p> : learned.map(([part, rows]) => (
            <div key={part} className="gx-learned">
              <strong>{t({ flight: "Flight", hotel: "Hotel", transport: "Transport", activity: "Activities", food: "Food" }[part] ?? part)}</strong>
              {rows.map((r) => <div key={r.provider} className="muted small" dir="auto">{r.provider}: {t("chosen {c} of {s} sent", { c: r.chosen, s: r.sent })}{r.removed ? ` · ${t("dropped {n}", { n: r.removed })}` : ""}</div>)}
            </div>
          ))}
          {(m.low_ratings ?? []).length > 0 && (<>
            <h3 className="gx-insight-h3">{t("Recent low ratings")}</h3>
            {m.low_ratings!.map((r, i) => <p key={i} className="small" dir="auto">{"★".repeat(r.rating)} {r.comment ? `“${r.comment}”` : ""}</p>)}
          </>)}
        </section>
      </div>
      <ReportCard report={data.report} path="/api/insights/report" title={t("The AI's analysis and growth plan")}
        note={t("The AI reads your figures (never another agency's) and writes what your customers want, what to improve, a 90-day growth plan and marketing ideas.")}
        onNew={(r) => setData({ ...data, report: r })} />
    </div>
  );
}
