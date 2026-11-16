import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, get, post, put } from "../api";
import { useAuth } from "../auth";
import { PageTitle, Switch } from "../components/admin/AdminUI";
import { AirplaneLanding, AirplaneTakeoff, Bell, CaretLeft, CaretRight, Plus, Trash, WarningCircle } from "../components/Icon";
import { ErrorBox, Field, Loading } from "../components/ui";
import { useI18n } from "../lang";
import type { User } from "../types";

interface Appt {
  id: number; kind: Kind; title: string; starts_at: string; ends_at: string | null; location: string; notes: string;
  ticket_id: number | null; reference: string | null; client: string | null; assigned_to_id: number | null; assigned_to: string | null;
  remind_minutes: number; remind_client: boolean; staff_reminded_at: string | null; client_reminded_at: string | null;
  client_remind_minutes: number | null; remind_owner: boolean;
  reminder_note: string | null; status: "planned" | "done" | "cancelled";
}
interface Trip { kind: "departure" | "return"; date: string; ticket_id: number; reference: string; client: string; destination: string }
type Kind = "meeting" | "airport" | "call" | "visit" | "other";
const KINDS: Record<Kind, string> = { meeting: "Meeting", airport: "Airport", call: "Call", visit: "Visit", other: "Other" };
const REMIND = [0, 15, 30, 60, 120, 240, 1440, 2880];
interface ReminderSettings { staff_minutes: number; client_minutes: number; remind_client: boolean; remind_owner: boolean }

const pad = (n: number) => String(n).padStart(2, "0");
const dayKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
/** A "datetime-local" value for the browser's time, and back to an ISO time with its zone. */
const toLocalInput = (iso: string) => { const d = new Date(iso); return `${dayKey(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const fromLocalInput = (v: string) => new Date(v).toISOString();

type Draft = { kind: Kind; title: string; starts: string; location: string; notes: string; ticket_id: number | null;
  assigned_to_id: number | null; remind_minutes: number; remind_client: boolean; client_remind_minutes: number | null;
  remind_owner: boolean; status: Appt["status"] };

function whenText(m: number, t: (k: string, v?: Record<string, string | number>) => string): string {
  return m === 0 ? t("At the time") : m < 60 ? t("{n} minutes before", { n: m }) : m < 1440 ? t("{n} hours before", { n: m / 60 })
    : m === 1440 ? t("1 day before") : t("{n} days before", { n: m / 1440 });
}

function Editor({ initial, id, team, onDone, onCancel }: { initial: Draft; id: number | null; team: User[]; onDone: () => void; onCancel: () => void }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const clientReminders = !!user?.company?.addons?.includes("calendar_client_reminders");
  const [d, setD] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    const body = { kind: d.kind, title: d.title, starts_at: fromLocalInput(d.starts), location: d.location, notes: d.notes,
      ticket_id: d.ticket_id, assigned_to_id: d.assigned_to_id, remind_minutes: d.remind_minutes, remind_client: d.remind_client,
      client_remind_minutes: d.client_remind_minutes, remind_owner: d.remind_owner, status: d.status };
    try { if (id) await put(`/api/calendar/${id}`, body); else await post("/api/calendar", body); onDone(); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!id) return;
    try { await api("DELETE", `/api/calendar/${id}`); onDone(); } catch (err) { setError((err as Error).message); }
  };
  return (
    <form className="gx-card gx-svc-editor" onSubmit={save}>
      <div className="gx-grid-2">
        <Field label={t("Title")}><input value={d.title} onChange={(e) => setD({ ...d, title: e.target.value })} required minLength={2} maxLength={200} dir="auto"
          placeholder={t("e.g. Meet the client at Muscat airport")} /></Field>
        <Field label={t("Type")}>
          <select value={d.kind} onChange={(e) => setD({ ...d, kind: e.target.value as Kind })}>
            {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
          </select>
        </Field>
        <Field label={t("Date and time")}><input type="datetime-local" value={d.starts} onChange={(e) => setD({ ...d, starts: e.target.value })} required dir="ltr" /></Field>
        <Field label={t("Place")}><input value={d.location} onChange={(e) => setD({ ...d, location: e.target.value })} maxLength={200} dir="auto" /></Field>
        <Field label={t("Person in charge")}>
          <select value={d.assigned_to_id ?? ""} onChange={(e) => setD({ ...d, assigned_to_id: e.target.value ? Number(e.target.value) : null })}>
            {!id && <option value="">{t("Me")}</option>}
            {team.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </Field>
        <Field label={t("Remind on WhatsApp")}>
          <select value={d.remind_minutes} onChange={(e) => setD({ ...d, remind_minutes: Number(e.target.value) })}>
            {REMIND.map((m) => <option key={m} value={m}>{whenText(m, t)}</option>)}
          </select>
        </Field>
      </div>
      {d.ticket_id && <p className="muted small">{t("Linked to request #{id}.", { id: d.ticket_id })}</p>}
      {d.ticket_id && clientReminders && (
        <Switch checked={d.remind_client} onChange={(v) => setD({ ...d, remind_client: v })} label={t("Remind the client too")}
          hint={t("On WhatsApp, in the client's language.")} />
      )}
      {d.ticket_id && clientReminders && d.remind_client && (
        <Field label={t("Remind the client")}>
          <select value={d.client_remind_minutes ?? d.remind_minutes} onChange={(e) => setD({ ...d, client_remind_minutes: Number(e.target.value) })}>
            {REMIND.map((m) => <option key={m} value={m}>{whenText(m, t)}</option>)}
          </select>
        </Field>
      )}
      <Switch checked={d.remind_owner} onChange={(v) => setD({ ...d, remind_owner: v })} label={t("Remind the company admins too")}
        hint={t("On WhatsApp, at the team's time, to the admins with a WhatsApp number on their account.")} />
      <Field label={t("Notes")}><textarea rows={2} value={d.notes} onChange={(e) => setD({ ...d, notes: e.target.value })} maxLength={2000} dir="auto" /></Field>
      {id && (
        <Field label={t("Status")}>
          <select value={d.status} onChange={(e) => setD({ ...d, status: e.target.value as Appt["status"] })}>
            <option value="planned">{t("Planned")}</option><option value="done">{t("Done")}</option><option value="cancelled">{t("Cancelled")}</option>
          </select>
        </Field>
      )}
      <ErrorBox error={error} />
      <div className="gx-form-actions">
        {id && <button type="button" className="btn btn-ghost btn-danger-text" onClick={remove}><Trash />{t("Delete")}</button>}
        <span className="spacer" />
        <button type="button" className="btn btn-ghost" onClick={onCancel}>{t("Cancel")}</button>
        <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Save")}</button>
      </div>
    </form>
  );
}

function RemindersCard({ onSaved }: { onSaved: (s: ReminderSettings) => void }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const [s, setS] = useState<ReminderSettings | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { get<ReminderSettings>("/api/calendar/settings/reminders").then(setS).catch(() => {}); }, []);
  if (!s) return null;
  const set = (patch: Partial<ReminderSettings>) => { setSaved(false); setS({ ...s, ...patch }); };
  return (
    <form className="gx-card" onSubmit={(e) => { e.preventDefault();
      put<ReminderSettings>("/api/calendar/settings/reminders", s).then((x) => { setSaved(true); setError(null); onSaved(x); }).catch((err) => setError((err as Error).message)); }}>
      <h2 className="gx-card-title">{t("Reminders for new appointments")}</h2>
      <p className="muted small">{t("Each appointment can still be changed. These are the usual choices.")}</p>
      <div className="gx-grid-2">
        <Field label={t("Remind the person in charge")}>
          <select value={s.staff_minutes} onChange={(e) => set({ staff_minutes: Number(e.target.value) })}>{REMIND.map((m) => <option key={m} value={m}>{whenText(m, t)}</option>)}</select>
        </Field>
        <Field label={t("Remind the client")}>
          <select value={s.client_minutes} onChange={(e) => set({ client_minutes: Number(e.target.value) })}>{REMIND.map((m) => <option key={m} value={m}>{whenText(m, t)}</option>)}</select>
        </Field>
      </div>
      {user?.company?.addons?.includes("calendar_client_reminders") && (
        <Switch checked={s.remind_client} onChange={(v) => set({ remind_client: v })} label={t("Remind clients by default")} />
      )}
      <Switch checked={s.remind_owner} onChange={(v) => set({ remind_owner: v })} label={t("Remind the company admins by default")} />
      <ErrorBox error={error} />
      <div className="gx-form-actions">{saved && <span className="muted small">{t("Saved.")}</span>}<button className="btn btn-primary btn-sm">{t("Save")}</button></div>
    </form>
  );
}

function TemplateCard() {
  const { t } = useI18n();
  const [tpl, setTpl] = useState<{ name: string; language: string } | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { get<{ name: string; language: string }>("/api/calendar/settings/template").then(setTpl).catch(() => {}); }, []);
  if (!tpl) return null;
  return (
    <details className="gx-card gx-cal-tpl">
      <summary>{t("Reminders outside WhatsApp's 24-hour window")}</summary>
      <p className="muted small">{t("WhatsApp delivers a normal message only within 24 hours of the person's last message to you. For other reminders, create a message template in Meta (WhatsApp Manager) with one variable for the text, wait for its approval, then write its name here.")}</p>
      <form className="gx-grid-2" onSubmit={(e) => { e.preventDefault(); setSaved(false);
        put("/api/calendar/settings/template", tpl).then(() => { setSaved(true); setError(null); }).catch((err) => setError((err as Error).message)); }}>
        <Field label={t("Template name")}><input value={tpl.name} onChange={(e) => setTpl({ ...tpl, name: e.target.value.toLowerCase() })} dir="ltr" placeholder="trip_reminder" maxLength={120} /></Field>
        <Field label={t("Template language")}><input value={tpl.language} onChange={(e) => setTpl({ ...tpl, language: e.target.value })} dir="ltr" placeholder="en" maxLength={10} /></Field>
        <div className="gx-form-actions">{saved && <span className="muted small">{t("Saved.")}</span>}<button className="btn btn-soft">{t("Save")}</button></div>
      </form>
      <ErrorBox error={error} />
    </details>
  );
}

export default function Calendar() {
  const { t, lang } = useI18n();
  const { can, user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [mine, setMine] = useState(false);
  const [data, setData] = useState<{ appointments: Appt[]; trips: Trip[] } | null>(null);
  const [team, setTeam] = useState<User[]>([]);
  const [reminders, setReminders] = useState<ReminderSettings | null>(null);
  useEffect(() => { get<ReminderSettings>("/api/calendar/settings/reminders").then(setReminders).catch(() => {}); }, []);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | "new" | null>(params.get("new") ? "new" : null);
  const manage = can("tickets.manage");
  const end = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const load = () => get<{ appointments: Appt[]; trips: Trip[] }>(`/api/calendar?start=${dayKey(month)}&end=${dayKey(end)}${mine ? "&mine=true" : ""}`)
    .then((x) => { setData(x); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, [month, mine]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { get<User[]>("/api/team").then(setTeam).catch(() => {}); }, []);
  const done = () => { setOpen(null); setParams({}); load(); };

  const days = useMemo(() => {
    const map = new Map<string, { appts: Appt[]; trips: Trip[] }>();
    const at = (k: string) => { if (!map.has(k)) map.set(k, { appts: [], trips: [] }); return map.get(k)!; };
    data?.appointments.forEach((a) => at(dayKey(new Date(a.starts_at))).appts.push(a));
    data?.trips.forEach((tr) => at(tr.date).trips.push(tr));
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [data]);
  const monthName = month.toLocaleDateString(lang === "ar" ? "ar-OM" : "en-GB", { month: "long", year: "numeric" });
  const dayName = (k: string) => new Date(`${k}T12:00:00`).toLocaleDateString(lang === "ar" ? "ar-OM" : "en-GB", { weekday: "long", day: "numeric", month: "long" });
  const time = (iso: string) => new Date(iso).toLocaleTimeString(lang === "ar" ? "ar-OM" : "en-GB", { hour: "2-digit", minute: "2-digit" });
  const today = dayKey(new Date());
  const ticketParam = params.get("ticket");
  const newDraft: Draft = { kind: "meeting", title: params.get("title") ?? "", starts: `${today}T10:00`, location: "", notes: "",
    ticket_id: ticketParam ? Number(ticketParam) : null, assigned_to_id: null, remind_minutes: reminders?.staff_minutes ?? 60,
    remind_client: reminders?.remind_client ?? false, client_remind_minutes: reminders?.client_minutes ?? null,
    remind_owner: reminders?.remind_owner ?? false, status: "planned" };

  return (
    <div className="narrow gx-narrow">
      <PageTitle kicker={t("Agency workspace")} title={t("Calendar")}
        subtitle={t("Meetings, airport pick-ups and calls, with reminders on WhatsApp, and the trips leaving or coming back.")}
        actions={manage ? <button type="button" className="btn btn-primary" onClick={() => setOpen("new")}><Plus />{t("New appointment")}</button> : undefined} />
      {!user?.whatsapp_number && (
        <p className="gx-rq-hint" role="note"><Bell weight="fill" /> <span>{t("Add your WhatsApp number in My account to get your reminders.")} <Link to="/app/account">{t("My account")}</Link></span></p>
      )}
      <div className="gx-cal-bar">
        <button type="button" className="icon-btn" aria-label={t("Previous month")} onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><CaretLeft className="flip" /></button>
        <strong className="gx-cal-month">{monthName}</strong>
        <button type="button" className="icon-btn" aria-label={t("Next month")} onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><CaretRight className="flip" /></button>
        <span className="spacer" />
        <button type="button" className={`gx-chip ${mine ? "on" : ""}`} aria-pressed={mine} onClick={() => setMine(!mine)}>{t("Only mine")}</button>
      </div>
      {open === "new" && <Editor initial={newDraft} id={null} team={team} onDone={done} onCancel={() => { setOpen(null); setParams({}); }} />}
      <ErrorBox error={error} onRetry={load} />
      {!data ? (!error && <Loading height={200} />) : days.length === 0 ? (
        <p className="muted">{t("Nothing this month.")}</p>
      ) : (
        <ol className="gx-cal-days">
          {days.map(([k, v]) => (
            <li key={k} className={k === today ? "today" : k < today ? "past" : ""}>
              <div className="gx-cal-day">{dayName(k)}</div>
              <ul>
                {v.trips.map((tr) => (
                  <li key={`${tr.kind}-${tr.ticket_id}`} className="gx-cal-item trip">
                    {tr.kind === "departure" ? <AirplaneTakeoff /> : <AirplaneLanding />}
                    <Link to={`/app/tickets?open=${tr.ticket_id}`}>
                      <strong>{tr.kind === "departure" ? t("Departure") : t("Return")}</strong> · <bdi>{tr.client}</bdi> · <bdi>{tr.destination}</bdi> · <bdi dir="ltr">{tr.reference}</bdi>
                    </Link>
                  </li>
                ))}
                {v.appts.map((a) => open === a.id ? (
                  <li key={a.id}><Editor id={a.id} team={team} onDone={done} onCancel={() => setOpen(null)} initial={{
                    kind: a.kind, title: a.title, starts: toLocalInput(a.starts_at), location: a.location, notes: a.notes, ticket_id: a.ticket_id,
                    assigned_to_id: a.assigned_to_id, remind_minutes: a.remind_minutes, remind_client: a.remind_client,
                    client_remind_minutes: a.client_remind_minutes, remind_owner: a.remind_owner, status: a.status }} /></li>
                ) : (
                  <li key={a.id} className={`gx-cal-item ${a.status}`}>
                    <span className="gx-cal-time tnum">{time(a.starts_at)}</span>
                    <button type="button" className="gx-cal-open" disabled={!manage} onClick={() => setOpen(a.id)}>
                      <strong dir="auto">{a.title}</strong>
                      <span className="muted small">
                        {t(KINDS[a.kind])}{a.location ? ` · ${a.location}` : ""}{a.assigned_to ? ` · ${a.assigned_to}` : ""}
                        {a.reference ? <> · <bdi dir="ltr">{a.reference}</bdi></> : null}{a.client ? ` · ${a.client}` : ""}
                      </span>
                      {a.reminder_note && <span className="small gx-cal-warn"><WarningCircle /> {t("Reminder not sent")}: {a.reminder_note.split("; ").map((n) => {
                        const [who, ...why] = n.split(": ");
                        return `${t(who)}: ${t(why.join(": "))}`;
                      }).join(" · ")}</span>}
                      {!a.reminder_note && a.staff_reminded_at && <span className="muted small"><Bell /> {t("Reminder sent")}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
      {can("settings.manage") && <RemindersCard onSaved={setReminders} />}
      {can("settings.manage") && <TemplateCard />}
    </div>
  );
}
