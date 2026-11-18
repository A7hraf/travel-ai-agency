import { DragEvent, KeyboardEvent, MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AirplaneLanding, AirplaneTakeoff } from "../Icon";
import { useI18n } from "../../lang";

/** A Google-Calendar-like view of the agency's appointments and trips: a month grid, or a week or day of hours.
 *  Click an empty place to add an appointment there; drag one to move it. */

export type View = "month" | "week" | "day";
export interface GridAppt { id: number; kind: string; title: string; starts_at: string; ends_at: string | null; status: string; location: string; client: string | null }
export interface GridTrip { kind: "departure" | "return"; date: string; ticket_id: number; reference: string; client: string; destination: string }

const HOUR = 48; // px per hour in the week and day views
const pad = (n: number) => String(n).padStart(2, "0");
export const dayKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
/** Oman's week starts on Sunday; the English interface follows the UK (Monday). */
export const weekStart = (d: Date, lang: string) => { const first = lang === "ar" ? 0 : 1; return addDays(d, -((d.getDay() - first + 7) % 7)); };

/** The first and last day shown by a view around `anchor`. */
export function range(view: View, anchor: Date, lang: string): [Date, Date] {
  if (view === "day") return [anchor, anchor];
  if (view === "week") { const s = weekStart(anchor, lang); return [s, addDays(s, 6)]; }
  const s = weekStart(new Date(anchor.getFullYear(), anchor.getMonth(), 1), lang);
  return [s, addDays(s, 41)];
}

/** After a drag ends, browsers may still send a click to the place it was dropped: ignore it. */
let droppedAt = 0;
const justDropped = () => Date.now() - droppedAt < 400;
const press = (open: () => void) => ({
  onClick: (e: MouseEvent) => { e.stopPropagation(); if (!justDropped()) open(); },
  onKeyDown: (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); open(); } },
});

const mins = (a: GridAppt) => { const s = new Date(a.starts_at); return s.getHours() * 60 + s.getMinutes(); };
const length = (a: GridAppt) => a.ends_at ? Math.max(15, (new Date(a.ends_at).getTime() - new Date(a.starts_at).getTime()) / 60000) : 60;

/** Side-by-side columns for appointments that overlap in one day. */
function lanes(list: GridAppt[]): Map<number, { lane: number; of: number }> {
  const sorted = [...list].sort((a, b) => mins(a) - mins(b));
  const out = new Map<number, { lane: number; of: number }>();
  let group: GridAppt[] = []; let groupEnd = -1; let ends: number[] = [];
  const close = () => { group.forEach((a) => { out.get(a.id)!.of = ends.length; }); group = []; ends = []; };
  for (const a of sorted) {
    const s = mins(a); const e = s + Math.max(30, length(a));
    if (s >= groupEnd) { close(); groupEnd = -1; }
    let lane = ends.findIndex((x) => x <= s);
    if (lane < 0) { lane = ends.length; ends.push(e); } else ends[lane] = e;
    out.set(a.id, { lane, of: 0 }); group.push(a); groupEnd = Math.max(groupEnd, e);
  }
  close();
  return out;
}

export default function CalendarGrid({ view, anchor, appts, trips, canEdit, onOpen, onNew, onMove, onDay }: {
  view: View; anchor: Date; appts: GridAppt[]; trips: GridTrip[]; canEdit: boolean;
  onOpen: (id: number) => void; onNew: (day: string, minutes: number) => void;
  onMove: (id: number, starts: Date) => void; onDay: (day: string) => void;
}) {
  const { t, lang } = useI18n();
  const loc = lang === "ar" ? "ar-OM" : "en-GB";
  const today = dayKey(new Date());
  const [from, to] = range(view, anchor, lang);
  const days = useMemo(() => { const out: Date[] = []; for (let d = from; d <= to; d = addDays(d, 1)) out.push(d); return out; }, [from.getTime(), to.getTime()]); // eslint-disable-line react-hooks/exhaustive-deps
  const byDay = useMemo(() => {
    const m = new Map<string, { appts: GridAppt[]; trips: GridTrip[] }>();
    const at = (k: string) => { if (!m.has(k)) m.set(k, { appts: [], trips: [] }); return m.get(k)!; };
    appts.forEach((a) => at(dayKey(new Date(a.starts_at))).appts.push(a));
    trips.forEach((tr) => at(tr.date).trips.push(tr));
    m.forEach((v) => v.appts.sort((a, b) => a.starts_at.localeCompare(b.starts_at)));
    return m;
  }, [appts, trips]);
  const time = (iso: string) => new Date(iso).toLocaleTimeString(loc, { hour: "numeric", minute: "2-digit" });
  const weekday = (d: Date, style: "short" | "long" = "short") => d.toLocaleDateString(loc, { weekday: style });
  const dragged = useRef<{ id: number; grabMin: number } | null>(null);
  const drag = (a: GridAppt, grabMin = 0) => (e: DragEvent) => { dragged.current = { id: a.id, grabMin }; droppedAt = 0; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(a.id)); };

  const tripChip = (tr: GridTrip) => (
    <Link key={`${tr.kind}-${tr.ticket_id}`} to={`/app/tickets?open=${tr.ticket_id}`} className={`gx-cg-chip trip ${tr.kind}`} onClick={(e) => e.stopPropagation()}
      title={`${tr.kind === "departure" ? t("Departure") : t("Return")} · ${tr.client} · ${tr.destination} · ${tr.reference}`}>
      {tr.kind === "departure" ? <AirplaneTakeoff /> : <AirplaneLanding />}<bdi>{tr.client}</bdi>
    </Link>
  );

  if (view === "month") {
    const month = anchor.getMonth();
    const drop = (k: string) => (e: DragEvent) => {
      e.preventDefault(); droppedAt = Date.now();
      const a = appts.find((x) => x.id === dragged.current?.id); dragged.current = null;
      if (!a) return;
      const s = new Date(a.starts_at); const [y, mo, d] = k.split("-").map(Number);
      onMove(a.id, new Date(y, mo - 1, d, s.getHours(), s.getMinutes()));
    };
    return (
      <div className="gx-cg-month" role="grid" aria-label={t("Month")}>
        <div className="gx-cg-wk" role="row">{days.slice(0, 7).map((d) => <div key={d.getDay()} role="columnheader">{weekday(d)}</div>)}</div>
        {[0, 1, 2, 3, 4, 5].map((w) => (
          <div key={w} className="gx-cg-row" role="row">
            {days.slice(w * 7, w * 7 + 7).map((d) => {
              const k = dayKey(d); const v = byDay.get(k); const items: { trip?: GridTrip; appt?: GridAppt }[] = [...(v?.trips ?? []).map((x) => ({ trip: x })), ...(v?.appts ?? []).map((x) => ({ appt: x }))];
              const extra = items.length - 3;
              return (
                <div key={k} role="gridcell" className={`gx-cg-cell ${d.getMonth() !== month ? "out" : ""} ${k === today ? "today" : ""}`}
                  onClick={() => canEdit && !justDropped() && onNew(k, 10 * 60)} onDragOver={(e) => canEdit && e.preventDefault()} onDrop={drop(k)}>
                  <button type="button" className="gx-cg-num tnum" onClick={(e) => { e.stopPropagation(); onDay(k); }}
                    aria-label={d.toLocaleDateString(loc, { weekday: "long", day: "numeric", month: "long" })}>{d.getDate()}</button>
                  {items.slice(0, extra > 0 ? 2 : 3).map((it) => it.trip ? tripChip(it.trip) : (
                    <div key={it.appt!.id} role="button" tabIndex={0} className={`gx-cg-chip dot k-${it.appt!.kind} ${it.appt!.status}`} draggable={canEdit}
                      onDragStart={drag(it.appt!)} {...press(() => onOpen(it.appt!.id))} title={it.appt!.title}>
                      <i aria-hidden="true" /><span className="tnum">{time(it.appt!.starts_at)}</span> <bdi>{it.appt!.title}</bdi>
                    </div>
                  ))}
                  {extra > 0 && <button type="button" className="gx-cg-more" onClick={(e) => { e.stopPropagation(); onDay(k); }}>{t("{n} more", { n: extra + 1 })}</button>}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    );
  }
  return <TimeGrid days={days} byDay={byDay} today={today} canEdit={canEdit} weekday={weekday} time={time} tripChip={tripChip}
    onOpen={onOpen} onNew={onNew} onDay={onDay} drop={(k, minutes) => {
      const a = appts.find((x) => x.id === dragged.current?.id); const grab = dragged.current?.grabMin ?? 0; dragged.current = null;
      if (!a) return;
      const m = Math.max(0, Math.min(24 * 60 - 15, Math.round((minutes - grab) / 15) * 15)); const [y, mo, d] = k.split("-").map(Number);
      onMove(a.id, new Date(y, mo - 1, d, Math.floor(m / 60), m % 60));
    }} drag={drag} />;
}

function TimeGrid({ days, byDay, today, canEdit, weekday, time, tripChip, onOpen, onNew, onDay, drop, drag }: {
  days: Date[]; byDay: Map<string, { appts: GridAppt[]; trips: GridTrip[] }>; today: string; canEdit: boolean;
  weekday: (d: Date, s?: "short" | "long") => string; time: (iso: string) => string; tripChip: (tr: GridTrip) => JSX.Element;
  onOpen: (id: number) => void; onNew: (day: string, minutes: number) => void; onDay: (day: string) => void;
  drop: (day: string, minutes: number) => void; drag: (a: GridAppt, grabMin?: number) => (e: DragEvent) => void;
}) {
  const { t, lang } = useI18n();
  const body = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(new Date());
  useEffect(() => { const i = window.setInterval(() => setNow(new Date()), 60000); return () => window.clearInterval(i); }, []);
  useEffect(() => { if (body.current) body.current.scrollTop = 7 * HOUR; }, []);
  const minuteAt = (e: MouseEvent | DragEvent) => { const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); return ((e.clientY - r.top) / HOUR) * 60; };
  const hourLabel = (h: number) => new Date(2000, 0, 1, h).toLocaleTimeString(lang === "ar" ? "ar-OM" : "en-GB", { hour: "numeric" });
  const anyTrips = days.some((d) => byDay.get(dayKey(d))?.trips.length);
  return (
    <div className={`gx-cg-time ${days.length === 1 ? "one" : ""}`} style={{ ["--cols" as string]: days.length }}>
      <div className="gx-cg-head">
        <span />
        {days.map((d) => { const k = dayKey(d); return (
          <button key={k} type="button" className={`gx-cg-dh ${k === today ? "today" : ""}`} onClick={() => onDay(k)}>
            <span className="small">{weekday(d)}</span><strong className="tnum">{d.getDate()}</strong>
          </button>
        ); })}
      </div>
      {anyTrips && (
        <div className="gx-cg-allday">
          <span className="muted small">{t("Trips")}</span>
          {days.map((d) => <div key={dayKey(d)}>{byDay.get(dayKey(d))?.trips.map(tripChip)}</div>)}
        </div>
      )}
      <div className="gx-cg-body" ref={body}>
        <div className="gx-cg-hours" aria-hidden="true">{Array.from({ length: 24 }, (_, h) => <span key={h} style={{ top: h * HOUR }}>{h ? hourLabel(h) : ""}</span>)}</div>
        {days.map((d) => {
          const k = dayKey(d); const list = byDay.get(k)?.appts ?? []; const lane = lanes(list);
          return (
            <div key={k} className={`gx-cg-col ${k === today ? "today" : ""}`} style={{ height: 24 * HOUR }}
              onClick={(e) => canEdit && !justDropped() && onNew(k, Math.floor(minuteAt(e) / 30) * 30)}
              onDragOver={(e) => canEdit && e.preventDefault()} onDrop={(e) => { e.preventDefault(); droppedAt = Date.now(); drop(k, minuteAt(e)); }}>
              {list.map((a) => {
                const l = lane.get(a.id)!; const top = (mins(a) / 60) * HOUR; const h = Math.max(22, (length(a) / 60) * HOUR - 2);
                return (
                  <div key={a.id} role="button" tabIndex={0} className={`gx-cg-ev k-${a.kind} ${a.status} ${h < 40 ? "short" : ""}`} draggable={canEdit}
                    style={{ top, height: h, zIndex: l.lane + 1, insetInlineStart: `calc(${(l.lane / l.of) * 100}% + 2px)`,
                      width: `calc(${l.lane === l.of - 1 ? 100 / l.of : Math.min(100 - (l.lane / l.of) * 100, 170 / l.of)}% - 6px)` }}
                    onDragStart={(e) => drag(a, ((e.clientY - (e.currentTarget as HTMLElement).getBoundingClientRect().top) / HOUR) * 60)(e)}
                    {...press(() => onOpen(a.id))}>
                    <bdi className="gx-cg-ev-t">{a.title}</bdi>
                    <span className="tnum">{time(a.starts_at)}{a.ends_at ? ` – ${time(a.ends_at)}` : ""}</span>
                    {a.location && <bdi className="gx-cg-ev-l">{a.location}</bdi>}
                  </div>
                );
              })}
              {k === today && <div className="gx-cg-now" style={{ top: ((now.getHours() * 60 + now.getMinutes()) / 60) * HOUR }} aria-hidden="true" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
