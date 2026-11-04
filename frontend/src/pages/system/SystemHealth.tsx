import { useEffect, useState } from "react";
import { get, post } from "../../api";
import AICheckCard from "../../components/AICheckCard";
import { PageTitle } from "../../components/admin/AdminUI";
import {
  ArrowClockwise, Bug, CheckCircle, Copy, Database, Heartbeat, InstagramLogo, WarningCircle, WhatsappLogo,
} from "../../components/Icon";
import { ErrorBox, Loading } from "../../components/ui";
import { useI18n } from "../../lang";
import type { CompanyAdmin, ErrorEventRow, SystemHealth as Health } from "../../types";
import { dateTime, timeAgo } from "../../util";

const PERIODS: [number, string][] = [[24, "Last 24 hours"], [168, "Last 7 days"]];

function buildTime(): string {
  try { return __BUILD_TIME__; } catch { return ""; }
}

const iso = (s: string | null | undefined) => (s ? new Date(s).toISOString().replace(".000Z", "Z") : "—");

/** Plain text a developer can read: in English, whatever the language of the page. */
function reportText(h: Health | null, errors: ErrorEventRow[], filters: string): string {
  const lines = ["Ghanjah system health report", `Generated: ${new Date().toISOString()}`, `Page: ${window.location.origin}`];
  if (h) {
    lines.push(
      `Server: v${h.version}, release ${h.release}, environment ${h.environment}, running since ${iso(h.started_at)}`,
      `Web app build: ${buildTime() || "unknown"}`,
      `Database: ${h.database.ok ? "ok" : "NOT OK"} (${h.database.dialect ?? "?"}, ${h.database.latency_ms} ms)${h.database.error ? ` - ${h.database.error}` : ""}`,
    );
    for (const c of h.channels) {
      lines.push(`${c.channel}: last 24h ${c.incoming_24h} incoming, ${c.replies_24h} replies, ${c.failed_24h} not delivered; last incoming ${iso(c.last_incoming_at)}; companies connected ${c.companies_connected}`);
    }
    lines.push(`Errors last 24h: ${h.errors_24h.server} server, ${h.errors_24h.client} browser`);
  }
  lines.push("", `Errors (${filters}): ${errors.length}`);
  for (const e of errors) {
    const times = e.count > 1 ? ` x${e.count} (first ${iso(e.created_at)})` : "";
    const where = [e.company_name ? `company ${e.company_name} (#${e.company_id})` : null, e.user_id ? `user #${e.user_id}` : null,
      e.page ? `page ${e.page}` : null, e.release ? `release ${e.release}` : null].filter(Boolean).join(", ");
    lines.push(`- [${iso(e.last_seen_at)}]${times} ${e.source} ${e.method ?? ""} ${e.path ?? ""} ${e.status ?? ""} ${e.error_type ?? ""}: ${e.message ?? ""}${where ? ` | ${where}` : ""}`.replace(/ +/g, " "));
  }
  return lines.join("\n");
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    /* fall back below (older browsers, http) */
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  if (!ok) throw new Error("copy failed");
}

export default function SystemHealth() {
  const { t } = useI18n();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [errors, setErrors] = useState<ErrorEventRow[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [companies, setCompanies] = useState<CompanyAdmin[]>([]);
  const [hours, setHours] = useState(24);
  const [source, setSource] = useState("");
  const [company, setCompany] = useState("");
  const [copied, setCopied] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testNote, setTestNote] = useState<string | null>(null);

  const loadHealth = () => {
    setHealthError(null);
    get<Health>("/api/system/health").then(setHealth).catch((e) => setHealthError((e as Error).message));
  };
  const loadErrors = () => {
    setListError(null);
    const q = new URLSearchParams({ hours: String(hours) });
    if (source) q.set("source", source);
    if (company) q.set("company_id", company);
    get<ErrorEventRow[]>(`/api/system/errors?${q}`).then(setErrors).catch((e) => setListError((e as Error).message));
  };
  useEffect(() => {
    loadHealth();
    get<CompanyAdmin[]>("/api/system/companies").then(setCompanies).catch(() => setCompanies([]));
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(loadErrors, [hours, source, company]);

  const refresh = () => { loadHealth(); loadErrors(); };

  const copy = async () => {
    const companyName = companies.find((c) => String(c.id) === company)?.name;
    const filters = [PERIODS.find(([h]) => h === hours)?.[1] ?? `${hours} h`, source || "all sources", companyName ?? "all companies"].join(", ");
    try {
      await copyText(reportText(health, errors ?? [], filters));
      setCopied(t("Copied. Paste it into a message to your developer."));
    } catch {
      setCopied(t("Your browser did not allow copying. Select the list and copy it by hand."));
    }
    window.setTimeout(() => setCopied(null), 4000);
  };

  const sendTest = async () => {
    setTesting(true);
    setTestNote(null);
    try {
      await post("/api/system/health/test-error");
    } catch {
      /* expected: the server answers 500 on purpose */
    } finally {
      setTesting(false);
      setTestNote(t("Test error sent. It should appear in the list below within a few seconds."));
      window.setTimeout(refresh, 600);
    }
  };

  const db = health?.database;
  return (
    <div className="narrow gx-narrow">
      <PageTitle kicker={t("Platform console")} title={t("System health")}
        subtitle={t("What the live site is running, whether the database and AI answer, webhook activity, and the errors people ran into.")}
        actions={<button type="button" className="btn btn-ghost" onClick={refresh}><ArrowClockwise aria-hidden="true" />{t("Refresh")}</button>} />

      <ErrorBox error={healthError} onRetry={loadHealth} />
      {!health && !healthError && <div style={{ marginBottom: 20 }}><Loading height={140} /></div>}
      {health && db && (
        <div className="bt-facts">
          <div className="bt-fact">
            <div className="bt-fact-label">{t("Server version")}</div>
            <div className="bt-fact-value">v{health.version}</div>
            <div className="bt-muted"><bdi dir="ltr">{health.release}</bdi> · {health.environment}</div>
          </div>
          <div className="bt-fact">
            <div className="bt-fact-label">{t("Web app built")}</div>
            <div className="bt-fact-value small">{buildTime() ? dateTime(buildTime()) : "—"}</div>
            <div className="bt-muted">{t("Server started {when}", { when: timeAgo(health.started_at) })}</div>
          </div>
          <div className="bt-fact">
            <div className="bt-fact-label"><Database aria-hidden="true" /> {t("Database")}</div>
            <div className={`bt-fact-value ${db.ok ? "ok" : "bad"}`}>{db.ok ? t("Working") : t("Not answering")}</div>
            <div className="bt-muted">{db.dialect ?? ""} · {t("{n} ms", { n: db.latency_ms })}</div>
            {db.error && <div className="bt-muted" dir="ltr">{db.error}</div>}
          </div>
          <div className="bt-fact">
            <div className="bt-fact-label"><Bug aria-hidden="true" /> {t("Errors, last 24 hours")}</div>
            <div className={`bt-fact-value ${health.errors_24h.server + health.errors_24h.client ? "bad" : "ok"}`}>
              {health.errors_24h.server + health.errors_24h.client}
            </div>
            <div className="bt-muted">{t("{a} server · {b} browser", { a: health.errors_24h.server, b: health.errors_24h.client })}</div>
          </div>
        </div>
      )}

      <AICheckCard path="/api/system/ai-check" />

      {health && (
        <section className="gx-card">
          <h2 className="gx-card-title"><span className="gx-card-icon"><Heartbeat /></span>{t("Webhook activity, last 24 hours")}</h2>
          <p className="gx-card-note">{t("Messages that arrived from WhatsApp and Instagram. Zero while customers are writing means the webhook is not reaching the server.")}</p>
          <div className="bt-channels">
            {health.channels.map((c) => (
              <div key={c.channel} className="bt-channel">
                <h3>{c.channel === "whatsapp" ? <WhatsappLogo weight="fill" color="var(--whatsapp)" /> : <InstagramLogo weight="fill" color="var(--ig)" />}
                  {c.channel === "whatsapp" ? t("WhatsApp") : t("Instagram")}</h3>
                <dl>
                  <dt>{t("Messages from customers")}</dt><dd>{c.incoming_24h}</dd>
                  <dt>{t("Replies sent")}</dt><dd>{c.replies_24h}</dd>
                  <dt>{t("Not delivered")}</dt><dd>{c.failed_24h}</dd>
                  <dt>{t("Last message from a customer")}</dt><dd>{c.last_incoming_at ? timeAgo(c.last_incoming_at) : "—"}</dd>
                  <dt>{t("Companies connected")}</dt><dd>{c.companies_connected}</dd>
                </dl>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="gx-card">
        <h2 className="gx-card-title"><span className="gx-card-icon danger"><WarningCircle /></span>{t("Errors")}
          <span className="spacer" />
          <button type="button" className="btn btn-sm btn-soft" onClick={copy}><Copy aria-hidden="true" />{t("Copy report")}</button>
        </h2>
        <p className="gx-card-note">{t("Server errors and errors people's browsers reported (failed pages and requests). Never passwords, tokens or form contents. Kept 30 days.")}</p>
        {copied && <div className="ok-box gx-notice" role="status">{copied}</div>}
        <div className="bt-toolbar">
          <div className="chips" role="group" aria-label={t("Period")}>
            {PERIODS.map(([h, label]) => (
              <button key={h} type="button" className={`chip-btn ${hours === h ? "active" : ""}`} aria-pressed={hours === h}
                onClick={() => setHours(h)}>{t(label)}</button>
            ))}
          </div>
          <select aria-label={t("Source")} value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">{t("Server and browser")}</option>
            <option value="server">{t("Server")}</option>
            <option value="client">{t("Browser")}</option>
          </select>
          <select aria-label={t("Company")} value={company} onChange={(e) => setCompany(e.target.value)}>
            <option value="">{t("All companies")}</option>
            {companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
          </select>
        </div>
        <ErrorBox error={listError} onRetry={loadErrors} />
        {errors === null && !listError && <Loading height={160} />}
        {errors && errors.length === 0 && (
          <div className="empty"><CheckCircle className="empty-icon" aria-hidden="true" />{t("No errors in this period.")}</div>
        )}
        {errors && errors.length > 0 && (
          <ul className="bt-errors">
            {errors.map((e) => (
              <li key={e.id}>
                <div className="bt-err-top">
                  <span className={`bt-src ${e.source}`}>{e.source === "server" ? t("Server") : t("Browser")}</span>
                  {e.count > 1 && <span className="bt-times">×{e.count}</span>}
                  <time dateTime={e.last_seen_at}>{dateTime(e.last_seen_at)}</time>
                  {e.company_name && <span>· <bdi>{e.company_name}</bdi></span>}
                  {e.release && <span dir="ltr">· {e.release}</span>}
                </div>
                <div className="bt-err-path" dir="ltr">{[e.method, e.path, e.status].filter((x) => x !== null && x !== "").join(" ")}
                  {e.error_type ? ` · ${e.error_type}` : ""}</div>
                {e.message && <div className="bt-err-msg" dir="auto">{e.message}</div>}
                {e.page && e.page !== e.path && <div className="bt-muted">{t("Page:")} <bdi dir="ltr">{e.page}</bdi></div>}
              </li>
            ))}
          </ul>
        )}
        <div className="gx-form-actions" style={{ marginTop: 14 }}>
          <button type="button" className="btn btn-ghost btn-sm" disabled={testing} onClick={sendTest}>
            <Bug aria-hidden="true" />{testing ? t("Please wait…") : t("Send a test error")}
          </button>
          <span className="bt-muted">{testNote ?? t("Checks that errors of this site reach this list.")}</span>
        </div>
      </section>
    </div>
  );
}
