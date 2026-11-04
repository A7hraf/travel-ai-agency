import { useEffect, useState } from "react";
import { get } from "../api";
import { trServer, useI18n } from "../lang";
import type { ActivityItem, ActivityPage } from "../types";
import { dateTime, TICKET_STATUS_LABELS } from "../util";
import { ClockCounterClockwise } from "./Icon";
import { ErrorBox } from "./ui";

const AREAS: [string, string][] = [
  ["", "Everything"],
  ["auth", "Logins"],
  ["user", "Accounts"],
  ["package", "Packages"],
  ["ticket", "Bookings"],
  ["customer", "Customers"],
  ["branding", "Page design"],
  ["ai", "AI training"],
  ["whatsapp", "WhatsApp"],
  ["instagram", "Instagram"],
  ["settings", "Settings"],
];
const PERIODS = [7, 30, 90, 365];

/** "pending_payment → paid" in words; field lists ("name, notes") word by word. */
function detailText(item: ActivityItem, t: (s: string) => string): string {
  const d = item.detail ?? "";
  if (item.action === "ticket.status") {
    return d.split(" → ").map((s) => (TICKET_STATUS_LABELS[s] ? t(TICKET_STATUS_LABELS[s]) : s)).join(" → ");
  }
  if (/^\d+ answers imported$/.test(d)) return t("{n} answers imported").replace("{n}", d.split(" ")[0]);
  return d.split(", ").map((part) => trServer(part)).join(t(", "));
}

/** The activity log of one company: `path` is /api/activity or /api/system/companies/{id}/activity. */
export default function ActivityLog({ path }: { path: string }) {
  const { t } = useI18n();
  const [days, setDays] = useState(30);
  const [area, setArea] = useState("");
  const [person, setPerson] = useState("");
  const [page, setPage] = useState<ActivityPage | null>(null);
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const query = (beforeId?: number) => {
    const q = new URLSearchParams({ days: String(days), limit: "100" });
    if (area) q.set("action", area);
    if (person) q.set("user_id", person);
    if (beforeId) q.set("before_id", String(beforeId));
    return `${path}?${q}`;
  };
  const load = () => {
    setLoading(true);
    setError(null);
    get<ActivityPage>(query())
      .then((p) => { setPage(p); setItems(p.items); })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };
  const more = () => {
    const last = items[items.length - 1];
    if (!last) return;
    setLoading(true);
    get<ActivityPage>(query(last.id))
      .then((p) => { setPage(p); setItems((list) => [...list, ...p.items]); })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [path, days, area, person]);

  return (
    <section className="ad-card">
      <div className="bt-toolbar">
        <div className="chips" role="group" aria-label={t("Period")}>
          {PERIODS.map((d) => (
            <button key={d} type="button" className={`chip-btn ${days === d ? "active" : ""}`} aria-pressed={days === d}
              onClick={() => setDays(d)}>{t("{n} days", { n: d })}</button>
          ))}
        </div>
        <select aria-label={t("Area")} value={area} onChange={(e) => setArea(e.target.value)}>
          {AREAS.map(([k, label]) => <option key={k} value={k}>{t(label)}</option>)}
        </select>
        <select aria-label={t("Person")} value={person} onChange={(e) => setPerson(e.target.value)}>
          <option value="">{t("Everyone")}</option>
          {(page?.people ?? []).filter((p) => p.user_id !== null).map((p) => (
            <option key={`${p.user_id}-${p.actor}`} value={String(p.user_id)}>{p.actor}</option>
          ))}
        </select>
      </div>

      <ErrorBox error={error} onRetry={load} />
      {!page && !error && <div className="skeleton" style={{ height: 220, borderRadius: 18 }} />}
      {page && items.length === 0 && !error && (
        <div className="empty">
          <ClockCounterClockwise className="empty-icon" aria-hidden="true" />
          {t("Nothing recorded in this period.")}
        </div>
      )}
      {items.length > 0 && (
        <ul className="bt-activity">
          {items.map((item) => (
            <li key={item.id}>
              <time dateTime={item.created_at}>{dateTime(item.created_at)}</time>
              <div className="bt-act-main">
                <div><span className="bt-act-what">{t(item.label)}</span>{item.target && <> · <bdi className="bt-act-target">{item.target}</bdi></>}</div>
                <div className="bt-act-detail">
                  <bdi>{item.actor === "Platform owner" ? t("Platform owner") : item.actor}</bdi>
                  {item.detail && <> · <span dir="auto">{detailText(item, t)}</span></>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {page?.has_more && (
        <div className="ad-form-actions">
          <button type="button" className="btn btn-ghost" disabled={loading} onClick={more}>{loading ? t("Loading…") : t("Show older")}</button>
        </div>
      )}
    </section>
  );
}
