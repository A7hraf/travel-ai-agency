import { FormEvent, useEffect, useState } from "react";
import { del, get, post, put } from "../api";
import { useAuth } from "../auth";
import { ConfirmSheet, PageTitle, Switch } from "../components/admin/AdminUI";
import { Binoculars, CalendarBlank, CalendarPlus, MagnifyingGlass, PencilSimple, Plus, Star, Trash, X } from "../components/Icon";
import ImageUpload from "../components/ImageUpload";
import { Money } from "../components/Money";
import { Poster } from "../components/Poster";
import { ErrorBox, Field, Modal } from "../components/ui";
import { useI18n } from "../lang";
import type { TravelPackage } from "../types";
import { daysText, shortDate, todayIso } from "../util";

type FormState = {
  title: string; destination: string; country: string; description: string; duration_days: string;
  price_per_person: string; child_price: string; currency: string; departure_dates: string[];
  includes: string; excludes: string; tags: string; hotel_name: string; hotel_stars: string;
  seats_available: string; image_url: string; is_active: boolean; is_featured: boolean;
};

const EMPTY: FormState = {
  title: "", destination: "", country: "", description: "", duration_days: "7", price_per_person: "",
  child_price: "", currency: "", departure_dates: [], includes: "", excludes: "", tags: "", hotel_name: "",
  hotel_stars: "", seats_available: "", image_url: "", is_active: true, is_featured: false,
};

function toForm(p: TravelPackage): FormState {
  return {
    title: p.title, destination: p.destination, country: p.country, description: p.description,
    duration_days: String(p.duration_days), price_per_person: String(p.price_per_person),
    child_price: p.child_price == null ? "" : String(p.child_price), currency: p.currency,
    departure_dates: p.departure_dates, includes: p.includes.join("\n"), excludes: p.excludes.join("\n"),
    tags: p.tags.join(", "), hotel_name: p.hotel_name ?? "", hotel_stars: p.hotel_stars ? String(p.hotel_stars) : "",
    seats_available: p.seats_available == null ? "" : String(p.seats_available), image_url: p.image_url ?? "",
    is_active: p.is_active, is_featured: p.is_featured,
  };
}

/** Seats are per departure date: the API adds the seats left on each upcoming date. */
const seatsLeftOn = (p: TravelPackage | null, d: string): number | undefined => p?.seats_left_by_date?.[d];

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const optNum = (s: string) => (s.trim() === "" ? null : Number(s));

export default function Packages() {
  const { can } = useAuth();
  const { t } = useI18n();
  const [items, setItems] = useState<TravelPackage[] | null>(null);
  const [editing, setEditing] = useState<TravelPackage | "new" | null>(null);
  const [filter, setFilter] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const manage = can("packages.manage");
  const today = todayIso();

  const load = () => get<TravelPackage[]>("/api/packages").then((list) => { setItems(list); return list; }).catch(() => null);
  useEffect(() => { load(); }, []);

  const shown = (items ?? []).filter((p) =>
    `${p.title} ${p.destination} ${p.country} ${p.tags.join(" ")}`.toLowerCase().includes(filter.toLowerCase()));
  const visible = (items ?? []).filter((p) => p.is_active).length;

  return (
    <div className="pk-page">
      <PageTitle
        kicker={items ? t("{n} of {m} visible to customers", { n: visible, m: items.length }) : t("Packages")}
        title={t("Packages")}
        subtitle={t("The AI only offers what is listed here, at these prices and dates.")}
        actions={manage && <button className="btn btn-primary" onClick={() => setEditing("new")}><Plus weight="bold" />{t("New package")}</button>} />
      <div className="ad-toolbar">
        <div className="ad-search">
          <MagnifyingGlass aria-hidden="true" />
          <input type="search" placeholder={t("Filter packages")} aria-label={t("Filter packages")} value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
      </div>
      {notice && <div className="ok-box ad-notice" role="status">{notice}</div>}
      {items === null ? (
        <div className="pk-grid">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 420, borderRadius: 24 }} />)}</div>
      ) : shown.length === 0 ? (
        <div className="empty">
          <Binoculars className="empty-icon" />
          <strong>{filter.trim() && items.length > 0 ? t("No results for this filter.") : t("No packages yet.")}</strong>
          {manage && !items.length && <button className="btn btn-primary" onClick={() => setEditing("new")}><Plus weight="bold" />{t("Add your first package")}</button>}
        </div>
      ) : (
        <div className="pk-grid">
          {shown.map((p, i) => {
            const next = p.departure_dates.find((d) => d >= today);
            // Seats left on the next departure (each date has its own seats).
            const nextLeft = p.seats_available == null ? null : next ? seatsLeftOn(p, next) ?? p.seats_available : p.seats_available;
            const low = nextLeft != null && nextLeft <= 6;
            return (
              <article key={p.id} className={`pk-card ${p.is_active ? "" : "inactive"}`} style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}>
                <Poster destination={p.destination} country={p.country} title={p.title} imageUrl={p.image_url} className="pk-poster">
                  <div className="pk-flags">
                    {p.is_featured && <span className="pk-flag featured"><Star weight="fill" />{t("Featured")}</span>}
                    {!p.is_active && <span className="pk-flag hidden">{t("Hidden")}</span>}
                  </div>
                  <div className="poster-body">
                    <div className="poster-country">{p.country}</div>
                    <div className="poster-name" dir="auto">{p.destination}</div>
                    <div className="poster-foot">
                      <span dir="auto" className="pk-poster-title">{p.title}</span>
                      <Money value={p.price_per_person} currency={p.currency} />
                    </div>
                  </div>
                </Poster>
                <div className="pk-body">
                  <div className="pk-meta">
                    <span>{daysText(p.duration_days)}</span>
                    {p.hotel_name && <span dir="auto">{p.hotel_name}{p.hotel_stars ? ` ${"★".repeat(p.hotel_stars)}` : ""}</span>}
                  </div>
                  <div className="pk-facts">
                    <span className="pk-fact"><CalendarBlank />{next ? <>{t("Next")} · {shortDate(next)}</> : t("Flexible dates")}</span>
                    {nextLeft != null && (p.departure_dates.length ? (
                      <span className={`pk-fact ${low ? "low" : ""}`} title={t("Seats left on the next departure. Each date has its own seats.")}>
                        {nextLeft === 1 ? t("1 seat left") : t("{n} seats left", { n: nextLeft })}
                      </span>
                    ) : (
                      <span className="pk-fact">{t("{n} seats per date", { n: nextLeft })}</span>
                    ))}
                  </div>
                  {p.tags.length > 0 && <div className="pk-tags">{p.tags.map((tag) => <span key={tag} dir="auto">{tag}</span>)}</div>}
                  {manage && (
                    <button className="btn btn-sm btn-soft pk-edit" onClick={() => setEditing(p)} aria-label={t("Edit {title}", { title: p.title })}>
                      <PencilSimple />{t("Edit")}
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
      {editing && (
        <PackageForm pkg={editing === "new" ? null : editing} onClose={() => setEditing(null)}
          onSaved={async (message, deletedId) => {
            setEditing(null);
            const list = await load();
            // A package with bookings is hidden instead of deleted: the server keeps it.
            if (deletedId != null && list?.some((x) => x.id === deletedId)) {
              message = t("This package has bookings, so it was hidden instead of deleted.");
            }
            setNotice(message);
            window.setTimeout(() => setNotice(null), 5000);
          }} />
      )}
    </div>
  );
}

function PackageForm({ pkg, onClose, onSaved }: {
  pkg: TravelPackage | null; onClose: () => void; onSaved: (message: string, deletedId?: number) => void;
}) {
  const { t } = useI18n();
  const [initial] = useState<FormState>(pkg ? toForm(pkg) : EMPTY);
  const [f, setF] = useState<FormState>(initial);
  const [newDate, setNewDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF({ ...f, [k]: v });
  const today = todayIso();
  const dirty = JSON.stringify(f) !== JSON.stringify(initial) || newDate !== "";
  const pastDates = f.departure_dates.filter((d) => d < today);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    const body: Record<string, unknown> = {
      title: f.title, destination: f.destination, country: f.country, description: f.description,
      duration_days: Number(f.duration_days), price_per_person: Number(f.price_per_person),
      child_price: optNum(f.child_price), currency: f.currency.trim() || null, departure_dates: f.departure_dates,
      includes: lines(f.includes), excludes: lines(f.excludes),
      tags: f.tags.split(/[,،]/).map((x) => x.trim()).filter(Boolean),
      hotel_name: f.hotel_name || null, hotel_stars: optNum(f.hotel_stars), seats_available: optNum(f.seats_available),
      image_url: f.image_url || null, is_active: f.is_active, is_featured: f.is_featured,
    };
    // The seat count the form was opened with: if it was not changed here, the server keeps the
    // current count (someone may have changed it meanwhile).
    if (pkg) body.seats_loaded = pkg.seats_available;
    setBusy(true);
    try {
      if (pkg) await put(`/api/packages/${pkg.id}`, body);
      else await post("/api/packages", body);
      onSaved(pkg ? t("Package saved.") : t("Package created."));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!pkg) return;
    setBusy(true);
    try {
      await del(`/api/packages/${pkg.id}`);
      setConfirmDelete(false);
      onSaved(t("Package deleted."), pkg.id);
    } catch (err) {
      setConfirmDelete(false);
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const addDate = () => {
    if (!newDate || newDate < today) return;
    if (!f.departure_dates.includes(newDate)) set("departure_dates", [...f.departure_dates, newDate].sort());
    setNewDate("");
  };

  return (
    <Modal title={pkg ? t("Edit {title}", { title: pkg.title }) : t("New package")} onClose={onClose} wide dirty={dirty}>
      <form onSubmit={save} className="pk-form">
        <div className="pk-form-section">
          <div className="ad-grid-3">
            <Field label={t("Title")}><input value={f.title} onChange={(e) => set("title", e.target.value)} required minLength={2} maxLength={200} dir="auto" /></Field>
            <Field label={t("Destination")} hint={t("City or region")}><input value={f.destination} onChange={(e) => set("destination", e.target.value)} required maxLength={120} dir="auto" /></Field>
            <Field label={t("Country")}><input value={f.country} onChange={(e) => set("country", e.target.value)} required maxLength={120} dir="auto" /></Field>
          </div>
          <div className="ad-grid-4">
            <Field label={t("Duration (days)")}><input type="number" min={1} max={365} step={1} value={f.duration_days} onChange={(e) => set("duration_days", e.target.value)} required /></Field>
            <Field label={t("Adult price")} hint={t("More than 0.")}><input type="number" min={0.001} step="0.001" value={f.price_per_person} onChange={(e) => set("price_per_person", e.target.value)} required dir="ltr" /></Field>
            <Field label={t("Child price")} hint={t("Empty = same as adult")}><input type="number" min={0} step="0.001" value={f.child_price} onChange={(e) => set("child_price", e.target.value)} dir="ltr" /></Field>
            <Field label={t("Currency")} hint={t("Empty = company currency")}><input maxLength={3} pattern="[A-Za-z]{3}" title={t("3 English letters, for example OMR")} dir="ltr" placeholder="OMR" value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></Field>
          </div>
          <div className="ad-grid-3">
            <Field label={t("Seats per departure date")} hint={t("Each date has its own seats. Empty = unlimited")}><input type="number" min={0} step={1} value={f.seats_available} onChange={(e) => set("seats_available", e.target.value)} /></Field>
            <Field label={t("Hotel")}><input value={f.hotel_name} onChange={(e) => set("hotel_name", e.target.value)} dir="auto" /></Field>
            <Field label={t("Stars")}><input type="number" min={1} max={7} value={f.hotel_stars} onChange={(e) => set("hotel_stars", e.target.value)} /></Field>
          </div>
        </div>

        <Field label={t("Description and itinerary")} hint={t("The AI reads this to answer customer questions.")}>
          <textarea rows={4} value={f.description} onChange={(e) => set("description", e.target.value)} dir="auto" />
        </Field>

        <div className="field">
          <span className="field-label">{t("Departure dates")}</span>
          <div className="date-chips">
            {f.departure_dates.map((d) => {
              const past = d < today;
              const left = past ? undefined : seatsLeftOn(pkg, d);
              return (
                <span key={d} className={`date-chip ${past ? "past" : ""}`} title={past ? t("Past date") : undefined}>
                  <span className={past ? "struck" : ""}>{shortDate(d)}</span>
                  {past && <span className="sr-only">{t("Past date")}</span>}
                  {left != null && <span className={`muted small ${left <= 6 ? "low" : ""}`}>· {t("{n} left", { n: left })}</span>}
                  <button type="button" aria-label={t("Remove {date}", { date: shortDate(d) })}
                    onClick={() => set("departure_dates", f.departure_dates.filter((x) => x !== d))}><X size={14} /></button>
                </span>
              );
            })}
            {!f.departure_dates.length && <span className="muted small">{t("Flexible dates")}</span>}
          </div>
          <div className="date-add">
            <input type="date" min={today} value={newDate} aria-label={t("New departure date")} onChange={(e) => setNewDate(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addDate(); } }} />
            <button type="button" className="btn btn-soft" disabled={!newDate || newDate < today} onClick={addDate}><CalendarPlus />{t("Add date")}</button>
          </div>
          <span className="field-hint">{pastDates.length
            ? t("Dates in the past (crossed out) are removed when you save.")
            : t("Leave empty for flexible dates on request.")}</span>
        </div>

        <div className="ad-grid-2">
          <Field label={t("Included (one per line)")}><textarea rows={4} value={f.includes} onChange={(e) => set("includes", e.target.value)} dir="auto" /></Field>
          <Field label={t("Not included (one per line)")}><textarea rows={4} value={f.excludes} onChange={(e) => set("excludes", e.target.value)} dir="auto" /></Field>
        </div>
        <Field label={t("Tags")} hint={t("Comma separated: honeymoon, family, beach, umrah… helps the AI match requests.")}>
          <input value={f.tags} onChange={(e) => set("tags", e.target.value)} dir="auto" />
        </Field>
        <div className="field">
          <span className="field-label">{t("Cover photo")}</span>
          <ImageUpload value={f.image_url || null} onChange={(url) => set("image_url", url ?? "")} label={undefined} />
          <span className="field-hint">{t("JPEG, PNG or WebP. Resized to 1600 px.")}</span>
        </div>
        <div className="pk-switches">
          <Switch checked={f.is_active} onChange={(v) => set("is_active", v)} label={t("Visible to customers")} hint={t("Customers and the AI can offer it.")} />
          <Switch checked={f.is_featured} onChange={(v) => set("is_featured", v)} label={t("Featured")} hint={t("Shown first on your customer page.")} />
        </div>
        <ErrorBox error={error} />
        <div className="modal-actions pk-actions">
          {pkg && <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setConfirmDelete(true)}><Trash />{t("Delete package")}</button>}
          <span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Save package")}</button>
        </div>
      </form>
      {confirmDelete && pkg && (
        <ConfirmSheet title={t("Delete \"{title}\"?", { title: pkg.title })} tone="danger" busy={busy}
          text={t("If this package has bookings, it will be hidden instead of deleted.")}
          confirmLabel={busy ? t("Deleting…") : t("Delete package")} onConfirm={remove} onCancel={() => setConfirmDelete(false)} />
      )}
    </Modal>
  );
}
