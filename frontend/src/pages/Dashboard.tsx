import { useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";
import { AreaLine, DataTable, HBars, Legend, ORDINAL_BLUES, Ring, SERIES, StackedColumns } from "../components/Charts";
import { Money, moneyText } from "../components/Money";
import { Badge, CONVERSATION_TONES, PageHeader, TICKET_TONES } from "../components/ui";
import { currentLocale, useI18n } from "../lang";
import type { Analytics, Dashboard as DashboardData } from "../types";
import { CONVERSATION_STATUS_LABELS, daysText, TICKET_STATUS_LABELS, usePolling } from "../util";

const PERIODS = [7, 30, 90];

function dayLabel(iso: string, long = false): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(currentLocale(),
    long ? { weekday: "short", day: "numeric", month: "short" } : { day: "numeric", month: "short" });
}

function compact(v: number): string {
  return new Intl.NumberFormat(currentLocale(), { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

function pct(part: number, whole: number): number {
  return whole > 0 ? part / whole : 0;
}

export default function Dashboard() {
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const [data, setData] = useState<DashboardData | null>(null);
  const [days, setDays] = useState(30);
  const [a, setA] = useState<Analytics | null>(null);
  usePolling(() => { get<DashboardData>("/api/dashboard").then(setData).catch(() => {}); }, 15000);
  usePolling(() => { get<Analytics>(`/api/dashboard/analytics?days=${days}`).then(setA).catch(() => {}); }, 60000, [days]);

  if (!data) return <div className="loading">{t("Loading…")}</div>;
  const openTickets = (data.tickets_by_status.pending_payment ?? 0) + (data.tickets_by_status.in_progress ?? 0)
    + (data.tickets_by_status.paid ?? 0);
  const currency = a?.currency ?? data.currency;
  const money = (v: number) => moneyText(v, currency, lang);
  const totalChats = a ? a.daily.reduce((s, d) => s + d.web + d.whatsapp, 0) : 0;
  const totalBookings = a ? a.daily.reduce((s, d) => s + d.bookings, 0) : 0;
  const conversion = a ? pct(a.funnel.with_booking, a.funnel.conversations) : 0;
  const handledTotal = a ? a.handled_by_ai + a.handed_to_team : 0;
  const aiShare = a ? pct(a.handled_by_ai, handledTotal) : 0;
  const otherCurrencies = Object.entries(data.other_currencies ?? {}).filter(([, v]) => v > 0);
  const channels = [{ label: t("Website"), color: SERIES[0] }, { label: t("WhatsApp"), color: SERIES[1] }];
  const funnel = a ? [
    { label: t("Conversations"), value: a.funnel.conversations, color: ORDINAL_BLUES[0] },
    { label: t("Booking requested"), value: a.funnel.with_booking, color: ORDINAL_BLUES[1],
      note: t("{p}% of conversations", { p: Math.round(conversion * 100) }) },
    { label: t("Paid or confirmed"), value: a.funnel.paid_or_confirmed, color: ORDINAL_BLUES[2],
      note: t("{p}% of conversations", { p: Math.round(pct(a.funnel.paid_or_confirmed, a.funnel.conversations) * 100) }) },
  ] : [];
  const firstName = user?.full_name.split(" ")[0] ?? "";

  return (
    <div className="dash">
      <PageHeader title={t("Welcome, {name}", { name: firstName })} subtitle={t("What's happening at your agency right now.")}
        actions={
          <div className="seg" role="group" aria-label={t("Period")}>
            {PERIODS.map((p) => (
              <button key={p} className={days === p ? "active" : ""} aria-pressed={days === p} onClick={() => setDays(p)}>{daysText(p)}</button>
            ))}
          </div>
        } />

      <div className="kpis">
        <div className="kpi kpi-hero">
          <div className="kpi-label">{t("Booked value · last {period}", { period: daysText(days) })}</div>
          <div className="kpi-value">{a ? <Money value={a.booked_value} currency={currency} lang={lang} /> : "…"}</div>
          <div className="kpi-sub">{t("{n} booking tickets", { n: totalBookings })}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">{t("Paid sales")}</div>
          <div className="kpi-value">{a ? <Money value={a.paid_value} currency={currency} lang={lang} /> : "…"}</div>
          <div className="kpi-sub">{t("Paid and confirmed bookings")}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">{t("Conversations")}</div>
          <div className="kpi-value">{totalChats}</div>
          <div className="kpi-sub">{t("Website and WhatsApp")}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">{t("Conversion")}</div>
          <div className="kpi-value">{Math.round(conversion * 100)}%</div>
          <div className="kpi-sub">{t("Chats that became a booking")}</div>
        </div>
        <div className="kpi kpi-ring">
          <Ring value={aiShare} color={SERIES[2]} empty={!a || handledTotal === 0} />
          <div>
            <div className="kpi-label">{t("Handled fully by the AI")}</div>
            <div className="kpi-sub">{t("{n} handed to your team", { n: a?.handed_to_team ?? 0 })}</div>
          </div>
        </div>
      </div>

      {otherCurrencies.length > 0 && (
        <p className="muted small other-currencies">
          {t("Bookings in other currencies, not included in the totals: {list}", {
            list: otherCurrencies.map(([cur, v]) => moneyText(v, cur, lang)).join(lang === "ar" ? "، " : ", "),
          })}
        </p>
      )}

      <div className="stats stats-compact">
        <Link to="/app/conversations?status=human" className="stat stat-link">
          <div className="stat-label">{t("Chats waiting for a human")}</div>
          <div className={`stat-value ${data.conversations_waiting ? "warn" : ""}`}>{data.conversations_waiting}</div>
        </Link>
        <Link to="/app/tickets" className="stat stat-link">
          <div className="stat-label">{t("Open booking tickets")}</div>
          <div className="stat-value">{openTickets}</div>
          <div className="stat-sub"><Money value={data.pipeline_value} currency={data.currency} lang={lang} /> {t("to collect")}</div>
        </Link>
        <div className="stat">
          <div className="stat-label">{t("My open tickets")}</div>
          <div className="stat-value">{data.my_open_tickets}</div>
        </div>
        <div className="stat">
          <div className="stat-label">{t("Active packages")}</div>
          <div className="stat-value">{data.packages_active}</div>
        </div>
        <div className="stat">
          <div className="stat-label">{t("Team accounts")}</div>
          <div className="stat-value">{data.users}<span className="stat-of"> / {data.max_users}</span></div>
        </div>
      </div>

      {a && (
        <>
          <div className="grid-2">
            <section className="card chart-card">
              <div className="chart-head">
                <h3>{t("Conversations per day")}</h3>
                <Legend items={channels} />
              </div>
              <StackedColumns series={channels}
                data={a.daily.map((d) => ({ label: dayLabel(d.date), values: [d.web, d.whatsapp] }))}
                tooltipTitle={(i) => dayLabel(a.daily[i].date, true)} />
              <DataTable summary={t("View as table")} head={[t("Day"), t("Website"), t("WhatsApp")]}
                rows={a.daily.map((d) => [dayLabel(d.date, true), d.web, d.whatsapp])} />
            </section>
            <section className="card chart-card">
              <div className="chart-head">
                <h3>{t("Booked value per day")}</h3>
              </div>
              <AreaLine data={a.daily.map((d) => ({ label: dayLabel(d.date), value: d.booked_value }))}
                format={money} axisFormat={compact} tooltipTitle={(i) => dayLabel(a.daily[i].date, true)} />
              <DataTable summary={t("View as table")} head={[t("Day"), t("Bookings"), t("Booked value")]}
                rows={a.daily.map((d) => [dayLabel(d.date, true), d.bookings, money(d.booked_value)])} />
            </section>
          </div>

          <div className="grid-2">
            <section className="card chart-card">
              <div className="chart-head">
                <h3>{t("From chat to sale")}</h3>
              </div>
              <HBars items={funnel} rtl={lang === "ar"} />
              <p className="muted small">{t("Cancelled tickets are not counted.")}</p>
            </section>
            <section className="card chart-card">
              <div className="chart-head">
                <h3>{t("Top packages by booked value")}</h3>
              </div>
              {a.top_packages.length === 0 ? (
                <div className="empty">{t("No bookings in this period yet.")}</div>
              ) : (
                <HBars rtl={lang === "ar"} format={money} items={a.top_packages.map((p) => ({
                  label: p.title, value: p.value, color: SERIES[0],
                  note: t("{n} bookings", { n: p.bookings }),
                }))} />
              )}
            </section>
          </div>
        </>
      )}

      <div className="grid-2">
        <section className="card">
          <h3>{t("Conversations now")}</h3>
          <StatusBars counts={data.conversations_by_status} labels={CONVERSATION_STATUS_LABELS} tones={CONVERSATION_TONES} />
        </section>
        <section className="card">
          <h3>{t("Booking tickets now")}</h3>
          <StatusBars counts={data.tickets_by_status} labels={TICKET_STATUS_LABELS} tones={TICKET_TONES} />
        </section>
      </div>
    </div>
  );
}

function StatusBars({ counts, labels, tones }: {
  counts: Record<string, number>; labels: Record<string, string>; tones: Record<string, string>;
}) {
  const { t } = useI18n();
  const max = Math.max(1, ...Object.keys(labels).map((s) => counts[s] ?? 0));
  return (
    <div className="status-bars">
      {Object.keys(labels).map((s) => (
        <div className="status-bar" key={s}>
          <Badge tone={tones[s]}>{t(labels[s])}</Badge>
          <div className="status-track"><div style={{ width: `${((counts[s] ?? 0) / max) * 100}%` }} /></div>
          <strong>{counts[s] ?? 0}</strong>
        </div>
      ))}
    </div>
  );
}
