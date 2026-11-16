import { FormEvent, useState } from "react";
import { post, put } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { Ticket, WorkflowStep } from "../../types";
import { dateTime } from "../../util";
import { CalendarCheck, Check, CheckCircle, PencilSimple, Prohibit } from "../Icon";
import { ErrorBox } from "../ui";
import WorkflowEditor, { stepBody, STEP_LABEL, workflowProblems } from "../workflow/WorkflowEditor";

// Steps the team marks done itself; the others finish when their work is done (see the server's workflow.py).
const TEAM_DONE = ["intake", "review", "documents", "schedule", "booking", "delivery", "trip", "feedback", "task"];

/** datetime-local value of an ISO time, in this browser's time zone. */
function localInput(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function Appointment({ ticket, step, onChange }: { ticket: Ticket; step: WorkflowStep; onChange: (t: Ticket) => void }) {
  const { t } = useI18n();
  const answers = ticket.answers ?? {};
  const [times, setTimes] = useState(step.client_times ?? [answers.preferred_times, answers.impossible_times && `${t("Not possible")}: ${answers.impossible_times}`].filter(Boolean).join(" · "));
  const [at, setAt] = useState(localInput(step.appointment?.at));
  const [place, setPlace] = useState(step.appointment?.location ?? "");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const url = `/api/tickets/${ticket.id}/workflow/${step.key}`;
  const run = async (fn: () => Promise<Ticket>) => {
    setBusy(true); setError(null);
    try { onChange(await fn()); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const book = (e: FormEvent) => {
    e.preventDefault();
    run(() => put<Ticket>(`${url}/appointment`, { client_times: times, starts_at: at ? new Date(at).toISOString() : null, location: place, notes }));
  };
  return (
    <form className="gx-wf-appt" onSubmit={book}>
      <label className="rw-lbl"><span>{t("The client's times (possible and not possible)")}</span>
        <textarea rows={2} dir="auto" maxLength={1000} value={times} onChange={(e) => setTimes(e.target.value)} /></label>
      <div className="gx-wf-appt-row">
        <label className="rw-lbl"><span>{t("Time you booked")}</span>
          <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} /></label>
        <label className="rw-lbl"><span>{t("Place")}</span>
          <input dir="auto" maxLength={200} value={place} onChange={(e) => setPlace(e.target.value)} placeholder={t("Embassy, airport terminal…")} /></label>
      </div>
      <label className="rw-lbl"><span>{t("Note for the calendar")}</span>
        <input dir="auto" maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      <div className="gx-wf-appt-actions">
        <button className="btn btn-sm btn-primary" disabled={busy}>{at ? t("Save and ask the client to confirm") : t("Save the client's times")}</button>
        {step.appointment && (
          <button type="button" className="btn btn-sm btn-soft" disabled={busy} onClick={() => run(() => post<Ticket>(`${url}/confirm`, {}))}>
            <CalendarCheck />{t("The client confirmed")}</button>
        )}
      </div>
      {step.appointment && <p className="muted small">{t("Booked: {when}", { when: step.appointment.text })}{step.appointment.location && ` · ${step.appointment.location}`} · {t("on the calendar, with reminders")}</p>}
      <ErrorBox error={error} />
    </form>
  );
}

export default function ProcessPanel({ ticket, onChange }: { ticket: Ticket; onChange: (t: Ticket) => void }) {
  const { t, lang } = useI18n();
  const { user, can } = useAuth();
  const manage = can("tickets.manage");
  const isAdmin = user?.role === "company_admin";
  const process = ticket.process;
  const [editing, setEditing] = useState<WorkflowStep[] | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!process) return null;
  const closed = ticket.stage === "closed";
  const steps = process.steps;
  const active = steps.find((s) => s.state === "active");
  const locked = steps.filter((s) => s.state && s.state !== "pending").length;
  const money = (v: number) => new Intl.NumberFormat(lang === "ar" ? "ar-OM" : "en-GB", { maximumFractionDigits: 3 }).format(v) + ` ${ticket.currency}`;
  const label = (s: { label_en: string; label_ar: string }) => (lang === "ar" ? s.label_ar : s.label_en);

  const run = async (fn: () => Promise<Ticket>) => {
    setBusy(true); setError(null);
    try { onChange(await fn()); setNote(""); return true; } catch (e) { setError((e as Error).message); return false; } finally { setBusy(false); }
  };
  const done = (skip = false) => active && run(() => post<Ticket>(`/api/tickets/${ticket.id}/workflow/done`, { key: active.key, note: note.trim() || null, skip }));
  const save = async () => {
    if (!editing) return;
    if (await run(() => put<Ticket>(`/api/tickets/${ticket.id}/workflow`, { steps: editing.map(stepBody) }))) setEditing(null);
  };
  const canDone = active && manage && !closed && (TEAM_DONE.includes(active.type) || (active.type === "payment" && isAdmin));
  const doneLabel = active?.type === "payment" ? t("Mark as paid outside the system") : active?.type === "documents" ? t("The documents are complete")
    : active?.type === "review" ? t("Reviewed: continue") : t("Mark this step done");

  return (
    <div className="gx-wf-panel">
      {process.cancel && (
        <div className="gx-wf-closed" role="status">
          <Prohibit weight="fill" />
          <div>
            <strong>{process.cancel.by === "client" ? t("Cancelled by the client") : t("Cancelled by the team")}</strong>
            <span>{process.cancel.reason || "—"}</span>
            <small className="muted">{t("At the step: {step}", { step: (lang === "ar" ? process.cancel.step_ar : process.cancel.step_en) || "—" })} · <bdi>{process.cancel.name}</bdi> · {dateTime(process.cancel.at)}</small>
          </div>
        </div>
      )}

      {editing ? (
        <section className="rw-card">
          <h3>{t("This request's steps")}</h3>
          <p className="muted small">{t("Only the steps not started yet can change. The service's own steps stay as they are.")}</p>
          <WorkflowEditor steps={editing} onChange={setEditing} locked={locked} currency={ticket.currency} />
          <div className="gx-wf-save">
            <button type="button" className="btn btn-sm btn-primary" disabled={busy || workflowProblems(editing).length > 0} onClick={save}>{t("Save the steps")}</button>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setEditing(null)}>{t("Cancel")}</button>
          </div>
        </section>
      ) : (
        <ol className="gx-wf-track">
          {steps.map((s, i) => (
            <li key={s.key} className={s.state ?? "pending"}>
              <span className="gx-wf-n">{s.state === "done" ? <Check weight="bold" /> : s.state === "skipped" ? "–" : i + 1}</span>
              <div className="gx-wf-body">
                <strong><bdi>{label(s)}</bdi></strong>
                {s.label_en !== STEP_LABEL[s.type]?.en && <span className="muted small"> · {lang === "ar" ? STEP_LABEL[s.type]?.ar : STEP_LABEL[s.type]?.en}</span>}
                {(s.state === "done" || s.state === "skipped") && (
                  <small className="muted">{s.state === "skipped" ? t("Skipped") : t("Done")} · <bdi>{s.by}</bdi>{s.done_at && ` · ${dateTime(s.done_at)}`}{s.note && ` · “${s.note}”`}</small>
                )}
                {s.state === "active" && s.started_at && <small className="muted">{t("Since {when}", { when: dateTime(s.started_at) })}</small>}
                {s.type === "payment" && (() => {
                  const row = process.installments.find((x) => x.key === s.key);
                  return row && ticket.money.total > 0 ? <small className={row.covered ? "gx-wf-paid" : "muted"}>{money(row.amount)}{row.covered && ` · ${t("paid")}`}</small> : null;
                })()}
                {s.state === "active" && s.type === "schedule" && manage && !closed && <Appointment ticket={ticket} step={s} onChange={onChange} />}
              </div>
            </li>
          ))}
          {!active && !closed && <li className="done end"><span className="gx-wf-n"><CheckCircle weight="fill" /></span><div className="gx-wf-body"><strong>{t("Every step is done")}</strong></div></li>}
        </ol>
      )}

      {!editing && canDone && (
        <section className="rw-card gx-wf-act">
          <label className="rw-lbl"><span>{t("Note (optional)")}</span>
            <input dir="auto" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="gx-wf-save">
            <button type="button" className="btn btn-sm btn-primary" disabled={busy || (active!.type === "schedule" && !active!.appointment)} onClick={() => done(false)}>{doneLabel}</button>
            {isAdmin && active!.type !== "payment" && <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={() => done(true)}>{t("Skip this step")}</button>}
          </div>
        </section>
      )}
      {!editing && manage && !closed && (
        <button type="button" className="btn btn-soft btn-sm" onClick={() => setEditing(steps.map((s) => ({ ...s })))}><PencilSimple />{t("Change this request's steps")}</button>
      )}
      <ErrorBox error={error} />
    </div>
  );
}
