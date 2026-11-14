import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, patch, put } from "../api";
import { useAuth } from "../auth";
import { PageTitle, Switch } from "../components/admin/AdminUI";
import { ChatCircleDots, Crown } from "../components/Icon";
import MemberBadge from "../components/members/MemberBadge";
import { Empty, ErrorBox, Field, Loading } from "../components/ui";
import { useI18n } from "../lang";
import { MEMBER_LEVELS, type MemberLevel, type MemberList, type MemberRequest, type MembershipConfig } from "../types";
import { dateTime, shortDate } from "../util";

type Tab = "members" | "requests" | "levels";
const STATUS_LABEL: Record<MemberRequest["status"], { label: string; tone: string }> = {
  open: { label: "Open", tone: "warn" }, in_progress: { label: "In progress", tone: "cyan" },
  done: { label: "Done", tone: "on" }, declined: { label: "Declined", tone: "off" },
};

function MembersTab() {
  const { t, lang } = useI18n();
  const [data, setData] = useState<MemberList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState<MemberLevel | "">("");
  const load = () => get<MemberList>(`/api/members${level ? `?level=${level}` : ""}`).then((d) => { setData(d); setError(null); })
    .catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, [level]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!data) return error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={220} />;
  const name = (l: MemberLevel) => (lang === "ar" ? data.config.levels[l].name_ar : data.config.levels[l].name_en);
  return (
    <>
      <div className="gx-b2b-meters">
        {MEMBER_LEVELS.map((l) => (
          <button key={l} type="button" className={`gx-b2b-meter gx-level-meter ${level === l ? "on" : ""}`} aria-pressed={level === l}
            onClick={() => setLevel(level === l ? "" : l)}>
            <div className="gx-b2b-num tnum">{data.counts[l]}</div>
            <div className="muted small"><Crown weight={l === "vip" ? "fill" : "regular"} /> {name(l)}</div>
          </button>
        ))}
      </div>
      <p className="muted small">{t("To give a rank, open a customer (Customers page) and choose it under Membership.")}</p>
      {data.members.length === 0 ? <Empty>{t("No members yet.")}</Empty> : (
        <ul className="gx-req-list">
          {data.members.map((m) => (
            <li key={m.customer_id}>
              <Link className="gx-req-row gx-member-row" to={`/app/customers/${m.customer_id}`}>
                <MemberBadge level={m.level} />
                <span className="gx-req-main" dir="auto"><strong>{m.name ?? m.phone ?? `#${m.customer_id}`}</strong>{m.note && <span className="muted"> · {m.note}</span>}</span>
                <bdi dir="ltr" className="muted small">{m.phone ?? m.email ?? ""}</bdi>
                <span className="muted small">{t("Member since {date}", { date: shortDate(m.member_since) })}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function RequestsTab() {
  const { t } = useI18n();
  const [list, setList] = useState<MemberRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<MemberRequest["status"] | "">("open");
  const [notes, setNotes] = useState<Record<number, string>>({});
  const load = () => get<MemberRequest[]>(`/api/members/requests${status ? `?status=${status}` : ""}`)
    .then((l) => { setList(l); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps
  const update = async (r: MemberRequest, body: Record<string, unknown>) => {
    try { await patch(`/api/members/requests/${r.id}`, body); load(); } catch (e) { setError((e as Error).message); }
  };
  return (
    <>
      <div className="gx-chips" role="group" aria-label={t("Status")}>
        {(["open", "in_progress", "done", "declined", ""] as const).map((s) => (
          <button key={s || "all"} type="button" className={`gx-chip ${status === s ? "on" : ""}`} aria-pressed={status === s} onClick={() => setStatus(s)}>
            {s ? t(STATUS_LABEL[s].label) : t("All")}
          </button>
        ))}
      </div>
      <ErrorBox error={error} />
      {!list ? <Loading height={200} /> : list.length === 0 ? <Empty>{t("No requests.")}</Empty> : (
        <div className="gx-mreq-list">
          {list.map((r) => (
            <article key={r.id} className="gx-card gx-mreq">
              <div className="gx-row-between">
                <div>
                  <div className="gx-kicker">{r.kind === "join" ? t("Wants to join") : t("Special request")} · {dateTime(r.created_at)}</div>
                  <h3 dir="auto">{r.title}</h3>
                </div>
                <span className={`gx-status ${STATUS_LABEL[r.status].tone}`}>{t(STATUS_LABEL[r.status].label)}</span>
              </div>
              <div className="gx-inline">
                <Link to={`/app/customers/${r.customer_id}`}><strong dir="auto">{r.customer_name ?? r.customer_phone ?? `#${r.customer_id}`}</strong></Link>
                <MemberBadge level={r.level} />
                {r.conversation_id && <Link className="btn btn-sm btn-ghost" to={`/app/conversations/${r.conversation_id}`}><ChatCircleDots />{t("Open chat")}</Link>}
              </div>
              {r.details && <p className="gx-pre" dir="auto">{r.details}</p>}
              <form className="gx-inline" onSubmit={(e: FormEvent) => { e.preventDefault(); update(r, { staff_note: notes[r.id] ?? r.staff_note ?? "" }); }}>
                <input value={notes[r.id] ?? r.staff_note ?? ""} onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })}
                  placeholder={t("Team note (what was arranged…)")} aria-label={t("Team note")} maxLength={4000} dir="auto" />
                <button className="btn btn-sm btn-ghost">{t("Save note")}</button>
              </form>
              <div className="gx-inline">
                {r.status !== "in_progress" && r.status !== "done" && <button className="btn btn-sm btn-soft" onClick={() => update(r, { status: "in_progress" })}>{t("Start")}</button>}
                {r.status !== "done" && <button className="btn btn-sm btn-primary" onClick={() => update(r, { status: "done" })}>{t("Done")}</button>}
                {r.status !== "declined" && r.status !== "done" && <button className="btn btn-sm btn-ghost" onClick={() => update(r, { status: "declined" })}>{t("Decline")}</button>}
                {r.handled_by && <span className="muted small">{t("Handled by {name}", { name: r.handled_by })}</span>}
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}

function LevelsTab() {
  const { t } = useI18n();
  const { refresh } = useAuth();
  const [config, setConfig] = useState<MembershipConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { get<MembershipConfig>("/api/members/settings").then(setConfig).catch((e) => setError((e as Error).message)); }, []);
  if (!config) return error ? <ErrorBox error={error} /> : <Loading height={220} />;
  const setLevel = (l: MemberLevel, patch: Partial<MembershipConfig["levels"][MemberLevel]>) => {
    setSaved(false);
    setConfig({ ...config, levels: { ...config.levels, [l]: { ...config.levels[l], ...patch } } });
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try { setConfig(await put<MembershipConfig>("/api/members/settings", config)); setSaved(true); refresh?.(); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={save}>
      <Switch checked={config.show_on_page} onChange={(v) => { setSaved(false); setConfig({ ...config, show_on_page: v }); }}
        label={t("Show the levels in The Community section of the customer page")} />
      <div className="gx-levels">
        {MEMBER_LEVELS.map((l, i) => {
          const c = config.levels[l];
          return (
            <section key={l} className="gx-card">
              <h2 className="gx-card-title"><Crown weight={l === "vip" ? "fill" : "regular"} />{l === "vip" ? t("VIP (chosen by you)") : t("Level {n}", { n: i + 1 })}</h2>
              <div className="gx-grid-2">
                <Field label={t("Name (English)")}><input value={c.name_en} onChange={(e) => setLevel(l, { name_en: e.target.value })} required maxLength={40} /></Field>
                <Field label={t("Name (Arabic)")}><input value={c.name_ar} onChange={(e) => setLevel(l, { name_ar: e.target.value })} required maxLength={40} dir="rtl" lang="ar" /></Field>
                <Field label={t("Perks (English, one per line)")}><textarea rows={4} value={c.perks_en} onChange={(e) => setLevel(l, { perks_en: e.target.value })} maxLength={1000} /></Field>
                <Field label={t("Perks (Arabic, one per line)")}><textarea rows={4} value={c.perks_ar} onChange={(e) => setLevel(l, { perks_ar: e.target.value })} maxLength={1000} dir="rtl" lang="ar" /></Field>
              </div>
              <Switch checked={c.special_requests} onChange={(v) => setLevel(l, { special_requests: v })} label={t("Special requests through the AI")}
                hint={t("The AI takes their requests beyond the packages (yacht, restaurant, surprise…) and passes them to your team.")} />
              <Switch checked={c.priority} onChange={(v) => setLevel(l, { priority: v })} label={t("Priority")}
                hint={t("Their chats are marked with a gold crown in the inbox.")} />
            </section>
          );
        })}
      </div>
      <ErrorBox error={error} />
      <div className="modal-actions">
        {saved && <span className="ok-box gx-notice">{t("Saved.")}</span>}
        <span className="spacer" />
        <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Save")}</button>
      </div>
    </form>
  );
}

export default function Members() {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("members");
  return (
    <div>
      <PageTitle kicker={t("Agency workspace")} title={t("Members")}
        subtitle={t("Your community: three ranks and VIP. You choose who is in each rank; the AI greets members, uses their perks and takes their special requests.")} />
      <div className="seg gx-tabs" role="tablist" aria-label={t("Members")}>
        {([["members", "Members"], ["requests", "Special requests"], ["levels", "Levels & perks"]] as [Tab, string][]).map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{t(label)}</button>
        ))}
      </div>
      {tab === "members" ? <MembersTab /> : tab === "requests" ? <RequestsTab /> : <LevelsTab />}
    </div>
  );
}
