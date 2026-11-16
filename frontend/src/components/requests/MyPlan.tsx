import { useEffect, useState } from "react";
import { get, post } from "../../api";
import { useI18n } from "../../lang";
import { dateTime, shortDate } from "../../util";
import { Bell, CalendarCheck, Lightning, Sparkle } from "../Icon";

type Period = "today" | "week" | "month";
interface PlanItem {
  kind: string; priority: number; ticket_id: number | null; ref?: string; client?: string; step_en?: string; step_ar?: string;
  assigned?: string | null; hours?: number; count?: number; date?: string; at?: string; title?: string; location?: string; can_remind?: boolean;
}

const TEXT: Record<string, string> = {
  check_receipt: "Check the payment receipt of {ref} ({client})",
  late: "{ref} ({client}) is late at “{step}”: {hours} h",
  your_turn: "Your turn on {ref} ({client}): {step}",
  remind_client: "{client} hasn't answered for {days} days ({ref}, {step})",
  client_answered: "{client} answered your question on {ref}",
  unassigned: "{count} requests have nobody yet",
  departure_not_ready: "{ref} leaves on {date} and the travel documents are not sent",
  departure: "{ref} ({client}) leaves on {date}",
  appointment: "{title} · {when}",
};

/** The employee's work for today, this week or this month, with the AI's short plan and a reminder button. */
export default function MyPlan({ onOpen, onUnassigned }: { onOpen: (id: number) => void; onUnassigned: () => void }) {
  const { t, lang } = useI18n();
  const [period, setPeriod] = useState<Period>("today");
  const [data, setData] = useState<{ items: PlanItem[]; summary: string | null; all_requests: boolean } | null>(null);
  const [hidden, setHidden] = useState(false);
  const [done, setDone] = useState<Record<number, string>>({});
  const load = () => get<{ items: PlanItem[]; summary: string | null; all_requests: boolean }>(`/api/tickets/plan?period=${period}&lang=${lang}`, { quiet: true })
    .then(setData).catch(() => setHidden(true));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [period, lang]);
  if (hidden) return null;

  const text = (i: PlanItem) => t(TEXT[i.kind] ?? i.kind, {
    ref: i.ref ?? "", client: i.client || t("the client"), step: (lang === "ar" ? i.step_ar : i.step_en) ?? "",
    hours: i.hours ?? 0, days: Math.floor((i.hours ?? 0) / 24), date: i.date ? shortDate(i.date) : "", title: i.title ?? "",
    when: i.at ? dateTime(i.at) : "", count: i.count ?? 0,
  });
  const remind = (id: number) => post(`/api/tickets/${id}/remind`, {})
    .then(() => setDone((d) => ({ ...d, [id]: t("Reminder sent") })))
    .catch((e) => setDone((d) => ({ ...d, [id]: (e as Error).message })));

  return (
    <section className="gx-plan" aria-label={t("My work plan")}>
      <div className="gx-plan-head">
        <h2><Sparkle weight="fill" /> {t("My work plan")}</h2>
        <div className="gx-plan-tabs" role="tablist">
          {(["today", "week", "month"] as Period[]).map((p) => (
            <button key={p} type="button" role="tab" aria-selected={period === p} className={period === p ? "on" : ""} onClick={() => setPeriod(p)}>
              {t(p === "today" ? "Today" : p === "week" ? "This week" : "This month")}
            </button>
          ))}
        </div>
      </div>
      {data?.summary && <p className="gx-plan-ai" dir="auto">{data.summary}</p>}
      {data && data.items.length === 0 && <p className="muted">{t("Nothing waiting for you. Well done!")}</p>}
      {data && data.items.length > 0 && (
        <ol className="gx-plan-list">
          {data.items.slice(0, 12).map((i, n) => (
            <li key={`${i.kind}-${i.ticket_id ?? i.at}-${n}`} className={i.priority >= 85 ? "hot" : ""}>
              {i.kind === "appointment" ? <CalendarCheck aria-hidden="true" /> : i.priority >= 85 ? <Lightning weight="fill" aria-hidden="true" /> : <span className="gx-plan-dot" aria-hidden="true" />}
              <span className="gx-plan-text" dir="auto">{text(i)}{data.all_requests && i.assigned && <small className="muted"> · {i.assigned}</small>}</span>
              <span className="gx-plan-actions">
                {i.kind === "remind_client" && i.ticket_id && (done[i.ticket_id]
                  ? <small className="muted">{done[i.ticket_id]}</small>
                  : i.can_remind && <button type="button" className="btn btn-soft btn-sm" onClick={() => remind(i.ticket_id!)}><Bell />{t("Remind")}</button>)}
                {i.kind === "unassigned" && <button type="button" className="btn btn-ghost btn-sm" onClick={onUnassigned}>{t("Show them")}</button>}
                {i.ticket_id && <button type="button" className="btn btn-ghost btn-sm" onClick={() => onOpen(i.ticket_id!)}>{t("Open it")}</button>}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
