import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";
import { useCountUp } from "../components/admin/AdminUI";
import { AreaChart, CHART, DayColumns, DayPoint, Meter, Ring } from "../components/Charts";
import { ChatCircleDots, Globe, Storefront, Suitcase, TrendDown, TrendUp, WhatsappLogo } from "../components/Icon";
import { Money, moneyText } from "../components/Money";
import { currentLocale, useI18n } from "../lang";
import type { Analytics, ConversationSummary, Dashboard as DashboardData } from "../types";
import { customerLabel, usePolling } from "../util";

const PERIODS = [7, 30, 90];

function day(iso: string, opts: Intl.DateTimeFormatOptions): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(currentLocale(), opts);
}

/** Bars per day; the 90-day view groups two days per bar so the columns stay readable. */
function dayPoints(a: Analytics): DayPoint[] {
  const short = (iso: string) => day(iso, { day: "numeric", month: "short" });
  const long = (iso: string) => day(iso, { weekday: "short", day: "numeric", month: "short" });
  if (a.daily.length <= 45) {
    return a.daily.map((d) => ({ label: short(d.date), long: long(d.date), web: d.web, wa: d.whatsapp }));
  }
  const out: DayPoint[] = [];
  // Pairs counted from today backwards, so the last bar ends today.
  for (let end = a.daily.length - 1; end >= 0; end -= 2) {
    const pair = a.daily.slice(Math.max(0, end - 1), end + 1);
    const first = pair[0].date;
    const last = pair[pair.length - 1].date;
    out.unshift({
      label: short(last),
      long: pair.length > 1 ? `${short(first)} – ${short(last)}` : long(last),
      web: pair.reduce((s, d) => s + d.web, 0),
      wa: pair.reduce((s, d) => s + d.whatsapp, 0),
    });
  }
  return out;
}

function greeting(hour: number): string {
  if (hour < 12) return "Good morning, {name}";
  if (hour < 17) return "Good afternoon, {name}";
  return "Good evening, {name}";
}

export default function Dashboard() {
  const { user, can } = useAuth();
  const { t, lang } = useI18n();
  const [data, setData] = useState<DashboardData | null>(null);
  const [days, setDays] = useState(30);
  const [a, setA] = useState<Analytics | null>(null);
  const [prevBooked, setPrevBooked] = useState<number | null>(null);
  const [queue, setQueue] = useState<ConversationSummary[] | null>(null);
  const [table, setTable] = useState(false);
  const [flash, setFlash] = useState<{ wa: boolean; text: string; n: number } | null>(null);
  const lastIds = useRef<Set<number> | null>(null);
  const canChats = can("conversations.view");

  usePolling(() => {
    get<DashboardData>("/api/dashboard").then(setData).catch(() => {});
    if (canChats) {
      get<ConversationSummary[]>("/api/conversations?status=human&limit=50").then((list) => {
        const waiting = list.filter((c) => !c.assigned_to);
        // A new chat waiting for a human since the last poll: short live flash.
        if (lastIds.current) {
          const fresh = waiting.filter((c) => !lastIds.current!.has(c.id));
          if (fresh.length) {
            setFlash({ wa: fresh[0].channel === "whatsapp", n: Date.now(),
              text: t("{name} is waiting for a human", { name: customerLabel(fresh[0].customer) }) });
          }
        }
        lastIds.current = new Set(waiting.map((c) => c.id));
        setQueue(waiting);
      }).catch(() => setQueue([]));
    }
  }, 15000, [canChats]);

  usePolling(() => {
    get<Analytics>(`/api/dashboard/analytics?days=${days}`).then(setA).catch(() => {});
    // The same days before this period, for the "on the previous N days" comparison.
    get<Analytics>(`/api/dashboard/analytics?days=${days * 2}`).then((x) => {
      setPrevBooked(x.daily.slice(0, days).reduce((s, d) => s + d.booked_value, 0));
    }).catch(() => setPrevBooked(null));
  }, 60000, [days]);

  useEffect(() => {
    if (!flash) return;
    const id = window.setTimeout(() => setFlash(null), 4200);
    return () => window.clearTimeout(id);
  }, [flash]);

  // Count-up on enter and whenever the data of another period arrives.
  const anim = useCountUp(a ? a.days : null);
  const now = new Date();

  if (!data) {
    return (
      <div className="dash">
        <div className="dash-skel">
          <div className="skeleton" style={{ height: 70, width: "50%" }} />
          <div className="skeleton" style={{ height: 180 }} />
          <div className="skeleton" style={{ height: 110 }} />
          <div className="skeleton" style={{ height: 300 }} />
        </div>
      </div>
    );
  }

  const ready = !!a && a.days === days;
  const k = ready ? anim : 0;
  const currency = a?.currency ?? data.currency;
  const openTickets = (data.tickets_by_status.pending_payment ?? 0) + (data.tickets_by_status.in_progress ?? 0)
    + (data.tickets_by_status.paid ?? 0);
  const web = a ? a.daily.reduce((s, d) => s + d.web, 0) : 0;
  const wa = a ? a.daily.reduce((s, d) => s + d.whatsapp, 0) : 0;
  const convs = a?.funnel.conversations ?? 0;
  const bookings = a ? a.daily.reduce((s, d) => s + d.bookings, 0) : 0;
  const conversion = convs ? (a?.funnel.with_booking ?? 0) / convs : 0;
  const handled = a ? a.handled_by_ai + a.handed_to_team : 0;
  const aiShare = handled ? (a?.handled_by_ai ?? 0) / handled : 0;
  const booked = a?.booked_value ?? 0;
  const paid = a?.paid_value ?? 0;
  const trend = prevBooked && prevBooked > 0 && ready ? (booked - prevBooked) / prevBooked : null;
  const otherCurrencies = Object.entries(data.other_currencies ?? {}).filter(([, v]) => v > 0);
  const firstName = user?.full_name.split(" ")[0] ?? "";
  const dateText = now.toLocaleDateString(currentLocale(), { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const points = a ? dayPoints(a) : [];
  const funnel = a ? [
    { label: t("Conversations"), value: a.funnel.conversations, color: CHART.funnel[0] },
    { label: t("Booking requested"), value: a.funnel.with_booking, color: CHART.funnel[1] },
    { label: t("Paid or confirmed"), value: a.funnel.paid_or_confirmed, color: CHART.funnel[2] },
  ] : [];
  const topMax = Math.max(1, ...(a?.top_packages ?? []).map((p) => p.value));
  const quiet = ready && convs === 0 && bookings === 0;
  const count = (v: number) => Math.round(v * k);
  const money = (v: number) => <Money value={v} currency={currency} lang={lang} />;
  const periodText = (n: number) => t(n === 7 ? "7 days" : n === 30 ? "30 days" : "90 days");

  return (
    <div className="dash">
      <div className="dash-glow" aria-hidden="true" />
      {flash && (
        <div className="dash-flash" key={flash.n} role="status">
          {flash.wa ? <WhatsappLogo weight="fill" style={{ color: CHART.wa }} /> : <Globe style={{ color: CHART.web }} />}
          {flash.text}
        </div>
      )}

      <header className="dash-head">
        <div className="dash-hello">
          <div className="dash-kicker"><span className="live-dot" aria-hidden="true" />{t("LIVE")} · {lang === "en" ? dateText.toUpperCase() : dateText}</div>
          <h1>{t(greeting(now.getHours()), { name: firstName })}</h1>
        </div>
        <div className="dash-period" role="group" aria-label={t("Period")}>
          {PERIODS.map((p) => (
            <button key={p} type="button" className={days === p ? "active" : ""} aria-pressed={days === p} onClick={() => setDays(p)}>
              {periodText(p)}
            </button>
          ))}
        </div>
      </header>

      <section className="dash-kpis" aria-busy={!ready}>
        <div className="kpi-card kpi-hero">
          <div className="kpi-kicker">{t("Booked value")}</div>
          <div className="kpi-big tnum">{money(booked * k)}</div>
          {trend !== null ? (
            <div className={`kpi-trend ${trend >= 0 ? "up" : "down"}`}>
              {trend >= 0 ? <TrendUp /> : <TrendDown />}
              {t("{p}% on the previous {period}", { p: Math.abs(Math.round(trend * 100)), period: periodText(days) })}
            </div>
          ) : (
            <div className="kpi-trend">{t("{n} booking tickets", { n: count(bookings) })}</div>
          )}
        </div>
        <div className="kpi-card">
          <div className="kpi-kicker muted-k">{t("Paid sales")}</div>
          <div className="kpi-mid tnum">{money(paid * k)}</div>
          <div className="kpi-note">{booked > 0
            ? t("{p}% of booked value", { p: Math.round((paid / booked) * 100) })
            : t("Paid and confirmed bookings")}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-kicker muted-k">{t("Conversations")}</div>
          <div className="kpi-num tnum">{count(convs)}</div>
          <div className="kpi-note">{t("{web} website · {wa} WhatsApp", { web: count(web), wa: count(wa) })}</div>
        </div>
        <div className="kpi-card kpi-ring">
          <Ring value={aiShare} a={k} empty={!a || handled === 0}
            label={handled ? t("{p}% handled fully by the AI", { p: Math.round(aiShare * 100) }) : t("No conversations yet")} />
          <div className="kpi-ring-text">
            <div className="kpi-pct tnum">{a && handled ? `${Math.round(aiShare * 100 * k)}%` : "—"}</div>
            <div className="kpi-note">{t("Handled fully by the AI")}</div>
            <div className="kpi-note">{convs ? t("{p}% of chats became a booking", { p: Math.round(conversion * 100) }) : t("No conversations yet")}</div>
          </div>
        </div>
      </section>

      <section className="dash-now" aria-label={t("Right now")}>
        {canChats ? (
          <Link to="/app/conversations?status=human" className={`now-card now-waiting ${data.conversations_waiting ? "" : "calm"}`}>
            <div className="now-label">{t("Waiting for a human")}</div>
            <div className="now-value tnum">{data.conversations_waiting}</div>
          </Link>
        ) : (
          <div className={`now-card now-waiting ${data.conversations_waiting ? "" : "calm"}`}>
            <div className="now-label">{t("Waiting for a human")}</div>
            <div className="now-value tnum">{data.conversations_waiting}</div>
          </div>
        )}
        {can("tickets.view") ? (
          <Link to="/app/tickets" className="now-card">
            <div className="now-label">{t("Open tickets")}</div>
            <div className="now-value tnum">{openTickets}</div>
            <div className="now-sub">{money(data.pipeline_value)} {t("to collect")}</div>
          </Link>
        ) : (
          <div className="now-card">
            <div className="now-label">{t("Open tickets")}</div>
            <div className="now-value tnum">{openTickets}</div>
            <div className="now-sub">{money(data.pipeline_value)} {t("to collect")}</div>
          </div>
        )}
        <div className="now-card">
          <div className="now-label">{t("My open tickets")}</div>
          <div className="now-value tnum">{data.my_open_tickets}</div>
        </div>
        <Link to="/app/packages" className="now-card">
          <div className="now-label">{t("Active packages")}</div>
          <div className="now-value tnum">{data.packages_active}</div>
        </Link>
        <div className="now-card">
          <div className="now-label">{t("Team accounts")}</div>
          <div className="now-value tnum">{data.users}<span className="now-of"> / {data.max_users}</span></div>
        </div>
      </section>

      {quiet && (
        <section className="dash-empty">
          <Storefront size={34} className="dash-empty-icon" />
          <div>
            <strong>{t("No activity yet")}</strong>
            <p>{t("When customers start chatting on your page, sales and conversations appear here.")}</p>
          </div>
          {data.packages_active === 0 && can("packages.manage")
            ? <Link className="btn btn-primary" to="/app/packages"><Suitcase />{t("Add your first package")}</Link>
            : user?.company && <a className="btn btn-soft" href={`/c/${user.company.slug}`} target="_blank" rel="noreferrer">{t("Open customer page")}</a>}
        </section>
      )}

      <div className="dash-row">
        <section className="dash-card dash-convs">
          <div className="dash-card-head">
            <h2>{t("Conversations per day")}</h2>
            <span className="legend"><i style={{ background: CHART.web }} />{t("Website")}</span>
            <span className="legend"><i style={{ background: CHART.wa }} />{t("WhatsApp")}</span>
            <button type="button" className="dash-toggle" aria-pressed={table} onClick={() => setTable(!table)}>
              {table ? t("View as chart") : t("View as table")}
            </button>
          </div>
          {!a ? <div className="skeleton" style={{ height: 230, marginTop: 20 }} /> : table ? (
            <div className="dash-table" role="region" aria-label={t("Conversations per day")} tabIndex={0}>
              <table>
                <thead><tr><th>{t("Day")}</th><th>{t("Website")}</th><th>{t("WhatsApp")}</th><th>{t("Bookings")}</th></tr></thead>
                <tbody>
                  {[...a.daily].reverse().map((d) => (
                    <tr key={d.date}><td>{day(d.date, { weekday: "short", day: "numeric", month: "short" })}</td><td>{d.web}</td><td>{d.whatsapp}</td><td>{d.bookings}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <DayColumns days={points} a={k} webLabel={t("Website")} waLabel={t("WhatsApp")} axisEnd={t("Today")}
              ariaLabel={t("{web} website and {wa} WhatsApp conversations in the last {period}. Use the arrow keys for each day.",
                { web, wa, period: periodText(days) })} />
          )}
        </section>

        <div className="dash-stack">
          <section className="dash-card">
            <h2>{t("From chat to sale")}</h2>
            <div className="funnel">
              {funnel.map((f) => (
                <div key={f.label}>
                  <div className="funnel-row"><span>{f.label}</span><span className="tnum">{count(f.value)}</span></div>
                  <Meter ratio={convs ? f.value / convs : 0} color={f.color} a={k} />
                </div>
              ))}
              {!a && <div className="skeleton" style={{ height: 120 }} />}
            </div>
          </section>

          {canChats && (
            <section className="dash-card dash-queue">
              <div className="dash-card-head">
                <h2>{t("Waiting for you")}</h2>
                <span className="queue-count">{t("{n} chats", { n: data.conversations_waiting })}</span>
              </div>
              {queue === null ? <div className="skeleton" style={{ height: 52, marginTop: 10 }} /> : queue.length === 0 ? (
                <p className="queue-empty"><ChatCircleDots /> {t("Nobody is waiting. The AI has it covered.")}</p>
              ) : (
                <ul className="queue">
                  {queue.slice(0, 4).map((c) => (
                    <li key={c.id}>
                      <span className="queue-dot" aria-hidden="true" />
                      <div className="queue-text">
                        <div className="queue-name">
                          {customerLabel(c.customer)}
                          {c.channel === "whatsapp"
                            ? <WhatsappLogo weight="fill" className="queue-ch wa" aria-label={t("WhatsApp")} />
                            : <Globe className="queue-ch web" aria-label={t("Website")} />}
                        </div>
                        <div className="queue-preview" dir="auto">{c.last_message_preview || "…"}</div>
                      </div>
                      {can("conversations.reply")
                        ? <Link className="take-btn" to={`/app/conversations/${c.id}`}>{t("Take over")}</Link>
                        : <Link className="take-btn" to={`/app/conversations/${c.id}`}>{t("Open")}</Link>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>
      </div>

      <div className="dash-row">
        <section className="dash-card">
          <h2>{t("Booked value per day")}</h2>
          {!a ? <div className="skeleton" style={{ height: 140, marginTop: 14 }} /> : (
            <AreaChart a={k} format={(v) => moneyText(v, currency, lang)}
              points={a.daily.map((d) => ({ long: day(d.date, { weekday: "short", day: "numeric", month: "short" }), value: d.booked_value }))}
              ariaLabel={t("Booked value per day: {total} in the last {period}.", { total: moneyText(booked, currency, lang), period: periodText(days) })} />
          )}
        </section>
        <section className="dash-card">
          <h2>{t("Top packages")}</h2>
          {a && a.top_packages.length === 0 ? (
            <p className="queue-empty">{t("No bookings in this period yet.")}</p>
          ) : (
            <div className="top-list">
              {(a?.top_packages ?? []).map((p) => (
                <div className="top-row" key={p.title} title={`${p.title} · ${t("{n} bookings", { n: p.bookings })}`}>
                  <span className="top-name" dir="auto">{p.title}</span>
                  <Meter ratio={p.value / topMax} color={CHART.web} a={k} height={8} />
                  <span className="top-val tnum" dir="ltr">{Math.round(p.value * k).toLocaleString("en-US")}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {otherCurrencies.length > 0 && (
        <p className="dash-fx">
          {t("Bookings in other currencies, not included in the totals: {list}", {
            list: otherCurrencies.map(([cur, v]) => moneyText(v, cur, lang)).join(lang === "ar" ? "، " : ", "),
          })}
        </p>
      )}
    </div>
  );
}
