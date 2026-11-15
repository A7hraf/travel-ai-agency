import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";
import ExportCsv from "../components/ExportCsv";
import { Binoculars, CaretLeft, CaretRight, Lightning, MagnifyingGlass, Plus, Receipt, UserCircleMinus } from "../components/Icon";
import MemberBadge from "../components/members/MemberBadge";
import { moneyText } from "../components/Money";
import NewRequest from "../components/requests/NewRequest";
import Workspace from "../components/requests/Workspace";
import { ErrorBox, Loading } from "../components/ui";
import { pollWatcher } from "../errorReporter";
import { useI18n } from "../lang";
import type { PipelineSummary, Service, Stage, Ticket, User } from "../types";
import { customerLabel, shortDate, TICKET_STATUS_LABELS, usePolling } from "../util";

type View = Stage | "open" | "all";
const PAGE = 25;
const STAGE_TABS: { key: View; label: string; hint: string }[] = [
  { key: "open", label: "All open", hint: "Everything not confirmed or closed" },
  { key: "quote", label: "To quote", hint: "New, changes asked, client chose: the team prepares choices or the final quotation" },
  { key: "client", label: "Client deciding", hint: "Choices or final quotation sent: waiting for the client" },
  { key: "payment", label: "Payment", hint: "Approved: waiting for the money, or receipts to check" },
  { key: "booking", label: "Booking", hint: "Paid: book everything and send the travel documents" },
  { key: "confirmed", label: "Confirmed", hint: "Booked trips" },
  { key: "closed", label: "Closed", hint: "Cancelled or rejected" },
  { key: "all", label: "All", hint: "Every request" },
];

/** "3 h" / "2 d" since the client's last message (or the request was made). */
function ago(iso: string | null, t: (k: string, v?: Record<string, string | number>) => string): string {
  if (!iso) return "";
  const h = (Date.now() - new Date(iso).getTime()) / 3600000;
  if (h < 1) return t("now");
  if (h < 48) return t("{n} h", { n: Math.floor(h) });
  return t("{n} d", { n: Math.floor(h / 24) });
}

export default function Tickets() {
  const { t, lang } = useI18n();
  const { user, can } = useAuth();
  const [params, setParams] = useSearchParams();
  const openId = params.get("open");
  const [view, setView] = useState<View>("open");
  const [search, setSearch] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [assigned, setAssigned] = useState("");
  const [urgentOnly, setUrgentOnly] = useState(false);
  const [sort, setSort] = useState<"urgency" | "newest" | "departure">("urgency");
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState<Ticket[] | null>(null);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<PipelineSummary | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [team, setTeam] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const poll = useRef(pollWatcher("Requests list"));
  const cur = summary?.currency ?? user?.company?.currency ?? "OMR";
  const money = (v: number | null | undefined) => (v == null ? "—" : moneyText(v, cur, lang));

  const load = () => {
    const q = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE), sort });
    if (view !== "all") q.set("stage", view);
    if (search.trim()) q.set("q", search.trim());
    if (serviceId) q.set("service_id", serviceId);
    if (assigned) q.set("assigned", assigned);
    if (urgentOnly) q.set("urgent", "true");
    const req = get<Ticket[]>(`/api/tickets?${q}`, { quiet: true, onHeaders: (h) => setTotal(Number(h.get("X-Total-Count") ?? 0)) });
    req.then((list) => { setRows(list); setError(null); poll.current.ok(); })
      .catch((e) => { setError((e as Error).message); poll.current.fail(e); });
    get<PipelineSummary>("/api/tickets/summary", { quiet: true }).then(setSummary).catch(() => {});
  };
  usePolling(load, 15000, [view, search, serviceId, assigned, urgentOnly, sort, page]);
  useEffect(() => { setPage(0); }, [view, search, serviceId, assigned, urgentOnly, sort]);
  useEffect(() => {
    get<Service[]>("/api/services").then(setServices).catch(() => {});
    get<User[]>("/api/team").then(setTeam).catch(() => {});
  }, []);

  const s = summary;
  const count = (k: View) => !s ? null : k === "open" ? s.stages.quote + s.stages.client + s.stages.payment + s.stages.booking
    : k === "all" ? null : s.stages[k as Stage];
  const svcName = (tk: Ticket) => (tk.service ? (lang === "ar" ? tk.service.name_ar : tk.service.name_en) : t("Holiday packages"));
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div className="rq-page">
      <div className="rq-head">
        <div>
          <h1 className="screen-title">{t("Requests")}</h1>
          <p className="muted">{t("Every client request from the first message to the trip: quotations, payments, documents and booking.")}</p>
        </div>
        <div className="rq-head-actions">
          {can("reports.view") && <ExportCsv className="btn btn-sm btn-ghost" />}
          {can("tickets.manage") && <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}><Plus />{t("New request")}</button>}
        </div>
      </div>

      <section className="rq-kpis" aria-label={t("At a glance")}>
        <div className="rq-kpi"><span>{t("Open requests")}</span><strong>{count("open") ?? "—"}</strong>
          <small>{s ? t("{n} urgent · {u} unassigned", { n: s.urgent, u: s.unassigned }) : ""}</small></div>
        <div className="rq-kpi"><span>{t("In quotation")}</span><strong>{money(s?.pipeline_value)}</strong><small>{t("value being quoted")}</small></div>
        <div className="rq-kpi"><span>{t("To collect")}</span><strong>{money(s?.to_collect)}</strong>
          <small>{s?.proofs_to_check ? t("{n} receipts to check", { n: s.proofs_to_check }) : t("approved, not paid yet")}</small></div>
        <div className="rq-kpi"><span>{t("Sales this month")}</span><strong>{money(s?.sales_this_month)}</strong>
          <small>{t("profit {v}", { v: money(s?.profit_this_month) })}</small></div>
      </section>

      <nav className="rq-stages" aria-label={t("Stages")}>
        {STAGE_TABS.map((x) => (
          <button key={x.key} type="button" className={`rq-stage ${view === x.key ? "on" : ""} st-${x.key}`} aria-pressed={view === x.key}
            title={t(x.hint)} onClick={() => setView(x.key)}>
            <span>{t(x.label)}</span>{count(x.key) != null && <b>{count(x.key)}</b>}
          </button>
        ))}
      </nav>

      <div className="rq-filters">
        <label className="search-field">
          <MagnifyingGlass aria-hidden="true" />
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder={t("Reference, client, phone or destination")} aria-label={t("Reference, client, phone or destination")} />
        </label>
        <select value={serviceId} onChange={(e) => setServiceId(e.target.value)} aria-label={t("Service")}>
          <option value="">{t("All services")}</option>
          {services.map((x) => <option key={x.id} value={x.id}>{lang === "ar" ? x.name_ar : x.name_en}</option>)}
        </select>
        <select value={assigned} onChange={(e) => setAssigned(e.target.value)} aria-label={t("Assigned to")}>
          <option value="">{t("Anyone")}</option>
          <option value="me">{t("Assigned to me")}</option>
          <option value="none">{t("Unassigned")}</option>
          {team.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} aria-label={t("Sort")}>
          <option value="urgency">{t("Most urgent first")}</option>
          <option value="newest">{t("Newest first")}</option>
          <option value="departure">{t("Departure date")}</option>
        </select>
        <button type="button" className={`gx-chip ${urgentOnly ? "on" : ""}`} aria-pressed={urgentOnly} onClick={() => setUrgentOnly(!urgentOnly)}>
          <Lightning weight="fill" /> {t("Urgent only")}
        </button>
      </div>

      {rows === null && error ? <ErrorBox error={error} onRetry={load} /> : rows === null ? <Loading height={260} /> : rows.length === 0 ? (
        <div className="empty">
          <Binoculars className="empty-icon" aria-hidden="true" />
          <strong>{t("No requests here")}</strong>
          {t("Try another stage or filter. New requests come from the AI in the chats, or the New request button.")}
        </div>
      ) : (
        <>
          <div className="rq-table" role="table" aria-label={t("Requests")}>
            <div className="rq-tr rq-th" role="row">
              <span role="columnheader">{t("Request")}</span>
              <span role="columnheader">{t("Client")}</span>
              <span role="columnheader">{t("Trip")}</span>
              <span role="columnheader">{t("Status")}</span>
              <span role="columnheader" className="num">{t("Price · profit")}</span>
              <span role="columnheader">{t("Team")}</span>
            </div>
            {rows.map((tk) => {
              const score = tk.urgency?.score ?? 0;
              const m = tk.money;
              const price = m.total > 0 ? m.total : m.choices_total;
              return (
                <button key={tk.id} type="button" role="row" className={`rq-tr ${score >= 45 ? "urgent" : score >= 20 ? "soon" : ""} ${String(tk.id) === openId ? "open" : ""}`}
                  onClick={() => setParams({ open: String(tk.id) })}>
                  <span role="cell" className="rq-c-ref">
                    <i className="rq-prio" aria-hidden="true" />
                    <bdi dir="ltr">{tk.reference}</bdi>
                    <small className="muted">{svcName(tk)} · {ago(tk.last_client_at ?? tk.created_at, t)}</small>
                  </span>
                  <span role="cell" className="rq-c-client">
                    <bdi>{tk.lead_traveler_name || customerLabel(tk.customer)}</bdi>
                    <MemberBadge level={tk.customer.member_level} />
                    {tk.contact_phone && <small className="muted"><bdi dir="ltr">{tk.contact_phone}</bdi></small>}
                  </span>
                  <span role="cell" className="rq-c-trip">
                    <bdi>{tk.destination || tk.package_title}</bdi>
                    <small className="muted">{tk.departure_date ? shortDate(tk.departure_date) : t("no date")}{tk.return_date ? ` – ${shortDate(tk.return_date)}` : ""} · {tk.adults + tk.children} {t("pax")}</small>
                  </span>
                  <span role="cell" className="rq-c-status">
                    <span className={`pill st-${tk.status}`}>{t(TICKET_STATUS_LABELS[tk.status])}</span>
                    {m.pending_proofs > 0 && <small className="rq-flag"><Receipt weight="fill" /> {t("receipt to check")}</small>}
                    {score >= 20 && <small className={`rq-flag ${score >= 45 ? "hot" : ""}`}><Lightning weight="fill" /> {score >= 45 ? t("Urgent") : t("Soon")}</small>}
                  </span>
                  <span role="cell" className="rq-c-money num">
                    {price ? moneyText(price, tk.currency, lang) : <span className="muted">{t("to quote")}</span>}
                    {m.profit != null && <small className={m.profit < 0 ? "neg" : "pos"}>{moneyText(m.profit, tk.currency, lang)}{m.margin_pct != null && ` · ${m.margin_pct}%`}</small>}
                    {(m.balance ?? 0) > 0 && tk.stage === "payment" && <small className="muted">{t("due {v}", { v: moneyText(m.balance ?? 0, tk.currency, lang) })}</small>}
                  </span>
                  <span role="cell" className="rq-c-team">
                    {tk.assigned_to ? <span className="rq-avatar" title={tk.assigned_to.full_name}>{tk.assigned_to.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}</span>
                      : <span className="muted small"><UserCircleMinus /> {t("Unassigned")}</span>}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="rq-pager">
            <span className="muted small">{t("{from}–{to} of {n}", { from: page * PAGE + 1, to: Math.min(total, page * PAGE + rows.length), n: total })}</span>
            <button type="button" className="icon-btn" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label={t("Previous page")}><CaretLeft className="flip" /></button>
            <span className="small">{page + 1} / {pages}</span>
            <button type="button" className="icon-btn" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)} aria-label={t("Next page")}><CaretRight className="flip" /></button>
          </div>
        </>
      )}

      {openId && <Workspace id={Number(openId)} onClose={() => setParams({})} onSaved={load} />}
      {creating && <NewRequest services={services} onClose={() => setCreating(false)}
        onCreated={(tk) => { setCreating(false); setParams({ open: String(tk.id) }); load(); }} />}
    </div>
  );
}
