import { CSSProperties, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { download, get } from "../api";
import { useAuth } from "../auth";
import { ArrowLeft, FileXls, Printer } from "../components/Icon";
import { moneyText } from "../components/Money";
import { ErrorBox, Loading } from "../components/ui";
import { LangSwitch, useI18n } from "../lang";
import { shortDate, todayIso } from "../util";
import { TICKET_STATUS_LABELS } from "../util";
import "../styles/quote.css";

interface Report {
  start: string; end: string; currency: string;
  company: { name: string; logo: string | null; primary: string };
  totals: { requests: number; paid: number; revenue: number; average_value: number | null; margin: number | null; margin_requests: number;
    cancelled: number; rejected: number; waiting_payment: number };
  by_status: Record<string, number>;
  quotations: { quoted: number; approved: number; approval_rate: number | null; average_rounds: number | null };
  by_service: { name_en: string; name_ar: string; requests: number; confirmed: number; revenue: number }[];
  by_staff: { name: string; requests: number; confirmed: number; revenue: number }[];
  destinations: [string, number][];
  suppliers: { name: string; category: string; bookings: number; cost: number; revenue: number; margin: number }[] | null;
}

type Preset = "month" | "last_month" | "quarter" | "year" | "custom";

function range(p: Preset): [string, string] {
  const today = new Date(todayIso());
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const y = today.getUTCFullYear(), m = today.getUTCMonth();
  if (p === "last_month") return [iso(new Date(Date.UTC(y, m - 1, 1))), iso(new Date(Date.UTC(y, m, 0)))];
  if (p === "quarter") return [iso(new Date(Date.UTC(y, m - 2, 1))), iso(today)];
  if (p === "year") return [iso(new Date(Date.UTC(y, 0, 1))), iso(today)];
  return [iso(new Date(Date.UTC(y, m, 1))), iso(today)];
}

/** Business report for a period, in the company's colours: printed to PDF, or downloaded as Excel. */
export default function Reports() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const excel = !!user?.company?.addons?.includes("reports_excel");
  const [preset, setPreset] = useState<Preset>("month");
  const [[start, end], setRange] = useState(range("month"));
  const [r, setR] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    setError(null);
    get<Report>(`/api/reports/summary?start=${start}&end=${end}`).then(setR).catch((e) => setError((e as Error).message));
  };
  useEffect(load, [start, end]); // eslint-disable-line react-hooks/exhaustive-deps
  const choose = (p: Preset) => { setPreset(p); if (p !== "custom") setRange(range(p)); };
  const m = (v: number | null) => (v == null ? "—" : moneyText(v, r?.currency ?? "OMR", lang));
  const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  return (
    <div className="qt-page">
      <div className="qt-tools no-print">
        <Link className="btn btn-ghost" to="/app/dashboard"><ArrowLeft className="flip" />{t("Back")}</Link>
        <select value={preset} onChange={(e) => choose(e.target.value as Preset)} aria-label={t("Period")}>
          <option value="month">{t("This month")}</option>
          <option value="last_month">{t("Last month")}</option>
          <option value="quarter">{t("Last 3 months")}</option>
          <option value="year">{t("This year")}</option>
          <option value="custom">{t("Choose dates")}</option>
        </select>
        {preset === "custom" && (
          <>
            <input type="date" value={start} onChange={(e) => setRange([e.target.value, end])} aria-label={t("From")} />
            <input type="date" value={end} onChange={(e) => setRange([start, e.target.value])} aria-label={t("To")} />
          </>
        )}
        <span className="spacer" />
        <LangSwitch className="btn btn-ghost" />
        {excel && (
          <button type="button" className="btn btn-soft" disabled={!r}
            onClick={() => download(`/api/reports/summary.xlsx?start=${start}&end=${end}`, `report-${start}-${end}.xlsx`).catch((e) => setError((e as Error).message))}>
            <FileXls />{t("Excel")}
          </button>
        )}
        <button type="button" className="btn btn-primary" onClick={() => window.print()} disabled={!r}><Printer />{t("Print or save as PDF")}</button>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {!r ? (!error && <Loading height={320} />) : (
        <article className="qt-sheet rp-sheet" style={{ "--qt-brand": r.company.primary } as CSSProperties}>
          <header className="qt-head">
            <div className="qt-brand">{r.company.logo ? <img src={r.company.logo} alt={r.company.name} className="qt-logo" /> : <strong className="qt-name">{r.company.name}</strong>}</div>
            <div className="qt-meta">
              <div className="qt-kind">{t("Business report")}</div>
              <div>{shortDate(r.start)} – {shortDate(r.end)}</div>
            </div>
          </header>
          <section className="qt-trip">
            {[[t("Requests"), String(r.totals.requests)], [t("Paid or confirmed"), String(r.totals.paid)],
              [t("Revenue"), m(r.totals.revenue)], [t("Margin"), m(r.totals.margin)],
              [t("Average value"), m(r.totals.average_value)], [t("Waiting for payment"), m(r.totals.waiting_payment)],
              [t("Quotations approved"), `${r.quotations.approved} / ${r.quotations.quoted} · ${pct(r.quotations.approval_rate)}`],
              [t("Cancelled or rejected"), String(r.totals.cancelled + r.totals.rejected)]].map(([k, v]) => (
              <div key={k} className="rp-figure"><div className="qt-label">{k}</div><div className="qt-big tnum">{v}</div></div>
            ))}
          </section>
          {r.totals.margin != null && r.totals.margin_requests < r.totals.paid && (
            <p className="qt-muted qt-small">{t("Margin counts {n} requests where every cost was written.", { n: r.totals.margin_requests })}</p>
          )}
          <section className="qt-part">
            <h2>{t("By service")}</h2>
            <table className="rp-table">
              <thead><tr><th>{t("Service")}</th><th>{t("Requests")}</th><th>{t("Paid or confirmed")}</th><th>{t("Revenue")}</th></tr></thead>
              <tbody>{r.by_service.map((s) => <tr key={s.name_en}><td>{lang === "ar" ? s.name_ar : s.name_en}</td><td className="n">{s.requests}</td><td className="n">{s.confirmed}</td><td className="n">{m(s.revenue)}</td></tr>)}</tbody>
            </table>
          </section>
          <section className="qt-part">
            <h2>{t("By team member")}</h2>
            <table className="rp-table">
              <thead><tr><th>{t("Team member")}</th><th>{t("Requests")}</th><th>{t("Paid or confirmed")}</th><th>{t("Revenue")}</th></tr></thead>
              <tbody>{r.by_staff.map((s) => <tr key={s.name}><td>{s.name === "—" ? t("Unassigned") : s.name}</td><td className="n">{s.requests}</td><td className="n">{s.confirmed}</td><td className="n">{m(s.revenue)}</td></tr>)}</tbody>
            </table>
          </section>
          <section className="qt-part">
            <h2>{t("Requests by status")}</h2>
            <table className="rp-table"><tbody>
              {Object.entries(r.by_status).map(([k, v]) => <tr key={k}><td>{t(TICKET_STATUS_LABELS[k] ?? k)}</td><td className="n">{v}</td></tr>)}
            </tbody></table>
          </section>
          {r.destinations.length > 0 && (
            <section className="qt-part">
              <h2>{t("Top destinations")}</h2>
              <p>{r.destinations.map(([d, n]) => `${d} (${n})`).join(" · ")}</p>
            </section>
          )}
          {r.suppliers && r.suppliers.length > 0 && (
            <section className="qt-part">
              <h2>{t("Top suppliers")}</h2>
              <table className="rp-table">
                <thead><tr><th>{t("Supplier")}</th><th>{t("Bookings")}</th><th>{t("You paid")}</th><th>{t("Margin")}</th></tr></thead>
                <tbody>{r.suppliers.map((s) => <tr key={s.name}><td>{s.name}</td><td className="n">{s.bookings}</td><td className="n">{m(s.cost)}</td><td className="n">{m(s.margin)}</td></tr>)}</tbody>
              </table>
            </section>
          )}
          <footer className="qt-foot"><div className="qt-contacts"><strong>{r.company.name}</strong><span>{t("Generated {date}", { date: shortDate(todayIso()) })}</span></div></footer>
        </article>
      )}
    </div>
  );
}
