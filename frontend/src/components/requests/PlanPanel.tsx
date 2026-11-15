import { useState } from "react";
import { post, put } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { PlanDay, Ticket } from "../../types";
import { shortDate } from "../../util";
import { ArrowDown, ArrowUp, Plus, Sparkle, Trash } from "../Icon";
import { ErrorBox } from "../ui";

/** The day-by-day plan of a tailor-made trip: written by the team or drafted by the AI, shown to the client
 *  in the quotation and on their trips page. */
export default function PlanPanel({ ticket, onChange }: { ticket: Ticket; onChange: (t: Ticket) => void }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const manage = can("tickets.manage") && ticket.stage !== "closed";
  const saved = ticket.itinerary ?? [];
  const [days, setDays] = useState<PlanDay[] | null>(null); // editing
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const list = days ?? saved;
  const set = (i: number, patch: Partial<PlanDay>) => setDays(list.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const renumber = (xs: PlanDay[]) => xs.map((d, i) => ({ ...d, day: i + 1 }));
  const move = (i: number, by: number) => {
    const j = i + by;
    if (j < 0 || j >= list.length) return;
    const next = [...list];
    [next[i], next[j]] = [next[j], next[i]];
    setDays(renumber(next));
  };
  const draft = async () => {
    setBusy(true); setError(null);
    try { setDays((await post<{ days: PlanDay[] }>(`/api/tickets/${ticket.id}/itinerary/ai-draft`)).days); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true); setError(null);
    try {
      onChange(await put<Ticket>(`/api/tickets/${ticket.id}/itinerary`, { days: renumber(list).map(({ day, title, details }) => ({ day, title, details })) }));
      setDays(null);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="rw-plan">
      {manage && (
        <div className="rw-row-end">
          <button type="button" className="btn btn-sm btn-soft" disabled={busy} onClick={draft}>
            <Sparkle weight="fill" />{busy && !days ? t("The AI is writing…") : saved.length ? t("Redraft with AI") : t("Draft the plan with AI")}
          </button>
          {!days && saved.length > 0 && <button type="button" className="btn btn-sm btn-ghost" onClick={() => setDays(saved)}>{t("Edit")}</button>}
        </div>
      )}
      {list.length === 0 && !days && <p className="muted">{t("No plan yet. A day-by-day plan helps the client say yes: it goes in the quotation and on their trips page.")}</p>}
      {days ? (
        <ol className="rw-plan-edit">
          {list.map((d, i) => (
            <li key={i}>
              <span className="rw-day">{t("Day {n}", { n: i + 1 })}</span>
              <div className="rw-plan-fields">
                <input value={d.title} onChange={(e) => set(i, { title: e.target.value })} maxLength={120} required dir="auto" aria-label={t("Title")} />
                <textarea value={d.details} onChange={(e) => set(i, { details: e.target.value })} rows={2} maxLength={1500} dir="auto" aria-label={t("Details")} />
              </div>
              <span className="rw-plan-btns">
                <button type="button" className="icon-btn" aria-label={t("Move up")} onClick={() => move(i, -1)}><ArrowUp /></button>
                <button type="button" className="icon-btn" aria-label={t("Move down")} onClick={() => move(i, 1)}><ArrowDown /></button>
                <button type="button" className="icon-btn" aria-label={t("Remove")} onClick={() => setDays(renumber(list.filter((_, j) => j !== i)))}><Trash /></button>
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <ol className="rw-plan-view">
          {saved.map((d) => (
            <li key={d.day}>
              <span className="rw-day">{t("Day {n}", { n: d.day })}{d.date && <span className="muted small"> · {shortDate(d.date)}</span>}</span>
              <strong dir="auto">{d.title}</strong>
              {d.details && <p dir="auto">{d.details}</p>}
            </li>
          ))}
        </ol>
      )}
      {days && (
        <div className="rw-row-end">
          <button type="button" className="btn btn-sm btn-ghost" disabled={list.length >= 60}
            onClick={() => setDays([...list, { day: list.length + 1, title: "", details: "" }])}><Plus />{t("Add a day")}</button>
          <span className="spacer" />
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => setDays(null)}>{t("Cancel")}</button>
          <button type="button" className="btn btn-sm btn-primary" disabled={busy || list.some((d) => !d.title.trim())} onClick={save}>{t("Save the plan")}</button>
        </div>
      )}
      <ErrorBox error={error} />
    </div>
  );
}
