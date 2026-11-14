import { FormEvent, useEffect, useState } from "react";
import { api, get, post, put } from "../api";
import { useAuth } from "../auth";
import { PageTitle, Switch } from "../components/admin/AdminUI";
import { ArrowSquareOut, MagnifyingGlass, Plus, Star, Trash } from "../components/Icon";
import ImageUpload from "../components/ImageUpload";
import { moneyText } from "../components/Money";
import { PART_LABELS, PARTS } from "../components/requests/QuotePanel";
import { Empty, ErrorBox, Field, Loading } from "../components/ui";
import { useI18n } from "../lang";
import type { ServicePart, Supplier } from "../types";

type Draft = Omit<Supplier, "id" | "bookings">;
const blank = (category: ServicePart): Draft => ({
  category, name: "", place: "", stars: null, link: null, image_url: null, description: "", notes: "",
  usual_cost: null, usual_price: null, preferred: false, is_active: true,
});
const toDraft = ({ id: _id, bookings: _b, ...rest }: Supplier): Draft => rest;

interface Stats {
  days: number;
  suppliers: { supplier_id: number | null; name: string; category: ServicePart; place: string; stars: number | null; bookings: number;
    cost: number; revenue: number; margin: number; in_library: boolean }[];
  by_part: Record<string, { bookings: number; cost: number; revenue: number; margin: number }>;
  hotel_stars: Record<string, number>;
  not_saved: number;
}

function Editor({ initial, id, onDone, onCancel }: { initial: Draft; id: number | null; onDone: () => void; onCancel: () => void }) {
  const { t } = useI18n();
  const [d, setD] = useState<Draft>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const num = (v: string) => (v.trim() === "" ? null : v);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (id) await put(`/api/library/${id}`, d); else await post("/api/library", d);
      onDone();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!id) return;
    try { await api("DELETE", `/api/library/${id}`); onDone(); } catch (err) { setError((err as Error).message); }
  };
  return (
    <form className="gx-card gx-svc-editor" onSubmit={save}>
      <div className="gx-grid-2">
        <Field label={t("Part")}>
          <select value={d.category} onChange={(e) => setD({ ...d, category: e.target.value as ServicePart })}>
            {PARTS.map((p) => <option key={p} value={p}>{t(PART_LABELS[p])}</option>)}
          </select>
        </Field>
        <Field label={t("Name")}><input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} required minLength={2} maxLength={200} dir="auto" /></Field>
        <Field label={t("City or country")} hint={t("Empty: suggested for any place (airlines, insurance…)")}>
          <input value={d.place} onChange={(e) => setD({ ...d, place: e.target.value })} maxLength={120} dir="auto" />
        </Field>
        {d.category === "hotel" && (
          <Field label={t("Stars")}>
            <select value={d.stars ?? ""} onChange={(e) => setD({ ...d, stars: e.target.value ? Number(e.target.value) : null })}>
              <option value="">—</option>
              {[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n}★</option>)}
            </select>
          </Field>
        )}
        <Field label={t("Link")}><input value={d.link ?? ""} onChange={(e) => setD({ ...d, link: e.target.value || null })} type="url" maxLength={500} dir="ltr" placeholder="https://" /></Field>
        <Field label={t("Your usual cost")}><input value={d.usual_cost ?? ""} onChange={(e) => setD({ ...d, usual_cost: num(e.target.value) })} inputMode="decimal" dir="ltr" /></Field>
        <Field label={t("Usual client price")}><input value={d.usual_price ?? ""} onChange={(e) => setD({ ...d, usual_price: num(e.target.value) })} inputMode="decimal" dir="ltr" /></Field>
      </div>
      <Field label={t("Description for clients (shown in quotations)")}>
        <textarea rows={2} value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} maxLength={2000} dir="auto" />
      </Field>
      <Field label={t("Notes for your team (contacts, contract rates…)")}>
        <textarea rows={2} value={d.notes} onChange={(e) => setD({ ...d, notes: e.target.value })} maxLength={2000} dir="auto" />
      </Field>
      <ImageUpload value={d.image_url} onChange={(url) => setD({ ...d, image_url: url })} label={t("Photo (your own or the supplier's official photo)")} />
      <Switch checked={d.preferred} onChange={(v) => setD({ ...d, preferred: v })} label={t("Preferred")} hint={t("Suggested first for requests to this place.")} />
      <Switch checked={d.is_active} onChange={(v) => setD({ ...d, is_active: v })} label={t("In use")} />
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

function Figures() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const cur = user?.company?.currency ?? "OMR";
  const [stats, setStats] = useState<Stats | null>(null);
  const [margins, setMargins] = useState<Record<string, { margin_pct: number; samples: number }> | null>(null);
  const has = (k: string) => !!user?.company?.addons?.includes(k);
  useEffect(() => {
    if (has("library_analytics")) get<Stats>("/api/library/stats").then(setStats).catch(() => {});
    if (has("library_margins")) get<Record<string, { margin_pct: number; samples: number }>>("/api/library/margins").then(setMargins).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!stats && !margins) return null;
  const m = (v: number) => moneyText(v, cur, lang);
  return (
    <section className="gx-card">
      <div className="gx-card-title">{t("Spending and margins (last 12 months, paid requests)")}</div>
      {stats && (
        <>
          <div className="gx-b2b-meters">
            {Object.entries(stats.by_part).map(([part, v]) => (
              <div key={part} className="gx-b2b-meter">
                <div className="muted small">{t(PART_LABELS[part as ServicePart] ?? "Other")}</div>
                <div className="gx-b2b-num tnum">{m(v.cost)}</div>
                <div className="muted small">{t("{n} bookings · margin {v}", { n: v.bookings, v: m(v.margin) })}</div>
              </div>
            ))}
          </div>
          {stats.suppliers.length === 0 ? <p className="muted small">{t("No paid requests yet: the figures appear after the first payments.")}</p> : (
            <table className="gx-lib-table">
              <thead><tr><th>{t("Supplier")}</th><th>{t("Bookings")}</th><th>{t("You paid")}</th><th>{t("Clients paid")}</th><th>{t("Margin")}</th></tr></thead>
              <tbody>
                {stats.suppliers.slice(0, 15).map((s, i) => (
                  <tr key={i}>
                    <td><bdi>{s.name}</bdi> <span className="muted small">· {t(PART_LABELS[s.category] ?? "Other")}{s.stars ? ` · ${s.stars}★` : ""}{!s.in_library ? ` · ${t("not saved")}` : ""}</span></td>
                    <td className="tnum">{s.bookings}</td><td className="tnum">{m(s.cost)}</td><td className="tnum">{m(s.revenue)}</td><td className="tnum">{m(s.margin)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {Object.keys(stats.hotel_stars).length > 0 && (
            <p className="muted small">{t("Hotels booked by stars:")} {Object.entries(stats.hotel_stars).map(([k, v]) => `${k}★ × ${v}`).join(" · ")}</p>
          )}
        </>
      )}
      {margins && Object.keys(margins).length > 0 && (
        <p className="muted small">{t("Your usual margin:")} {Object.entries(margins).map(([p, v]) => `${t(PART_LABELS[p as ServicePart] ?? "Other")} ${v.margin_pct}% (${v.samples})`).join(" · ")}</p>
      )}
    </section>
  );
}

export default function Library() {
  const { t, lang } = useI18n();
  const { can, user } = useAuth();
  const cur = user?.company?.currency ?? "OMR";
  const [part, setPart] = useState<ServicePart | "">("");
  const [q, setQ] = useState("");
  const [list, setList] = useState<Supplier[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | "new" | null>(null);
  const manage = can("tickets.manage");
  const load = () => {
    const p = new URLSearchParams();
    if (part) p.set("category", part);
    if (q.trim()) p.set("q", q.trim());
    get<Supplier[]>(`/api/library?${p}`).then((x) => { setList(x); setError(null); }).catch((e) => setError((e as Error).message));
  };
  useEffect(load, [part, q]); // eslint-disable-line react-hooks/exhaustive-deps
  const done = () => { setOpen(null); load(); };

  return (
    <div className="narrow gx-narrow">
      <PageTitle kicker={t("Agency workspace")} title={t("Supplier library")}
        subtitle={t("The hotels, airlines, transport and activities you work with. Saved once, suggested again for requests to the same place, and counted in your spending.")}
        actions={manage ? <button type="button" className="btn btn-primary" onClick={() => setOpen("new")}><Plus />{t("Add a supplier")}</button> : undefined} />
      <Figures />
      <div className="gx-chips" role="group" aria-label={t("Part")}>
        <button type="button" className={`gx-chip ${part === "" ? "on" : ""}`} aria-pressed={part === ""} onClick={() => setPart("")}>{t("All")}</button>
        {PARTS.map((p) => (
          <button key={p} type="button" className={`gx-chip ${part === p ? "on" : ""}`} aria-pressed={part === p} onClick={() => setPart(p)}>{t(PART_LABELS[p])}</button>
        ))}
      </div>
      <label className="search-field gx-lib-search">
        <MagnifyingGlass aria-hidden="true" />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Name or place")} aria-label={t("Name or place")} />
      </label>
      {open === "new" && <Editor initial={blank(part || "hotel")} id={null} onDone={done} onCancel={() => setOpen(null)} />}
      <ErrorBox error={error} onRetry={load} />
      {!list ? (!error && <Loading height={200} />) : list.length === 0 ? (
        <Empty>{t("Nothing saved yet. Add suppliers here, or save a choice from a request with the bookmark button.")}</Empty>
      ) : (
        <div className="gx-lib-grid">
          {list.map((s) => open === s.id ? (
            <Editor key={s.id} initial={toDraft(s)} id={s.id} onDone={done} onCancel={() => setOpen(null)} />
          ) : (
            <button key={s.id} type="button" className={`gx-card gx-lib-card ${s.is_active ? "" : "off"}`} disabled={!manage} onClick={() => setOpen(s.id)}>
              {s.image_url ? <img src={s.image_url} alt="" className="gx-lib-img" /> : <span className="gx-lib-img empty" aria-hidden="true" />}
              <span className="gx-lib-body">
                <span className="gx-row-between">
                  <strong dir="auto">{s.name}</strong>
                  {s.preferred && <Star weight="fill" className="gx-lib-star" aria-label={t("Preferred")} />}
                </span>
                <span className="muted small">
                  {t(PART_LABELS[s.category])}{s.place ? ` · ${s.place}` : ` · ${t("anywhere")}`}{s.stars ? ` · ${s.stars}★` : ""}
                </span>
                <span className="small">
                  {s.usual_price != null && <>{moneyText(Number(s.usual_price), cur, lang)}</>}
                  {s.bookings > 0 && <span className="muted"> · {t("chosen {n} times", { n: s.bookings })}</span>}
                  {s.link && <ArrowSquareOut className="gx-lib-link" aria-hidden="true" />}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
