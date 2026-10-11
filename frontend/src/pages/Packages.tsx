import { FormEvent, useEffect, useState } from "react";
import { del, get, post, put } from "../api";
import { useAuth } from "../auth";
import { Badge, Empty, ErrorBox, Field, Modal, PageHeader } from "../components/ui";
import type { TravelPackage } from "../types";
import { gradientFor, money, shortDate } from "../util";

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

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const optNum = (s: string) => (s.trim() === "" ? null : Number(s));

export default function Packages() {
  const { can } = useAuth();
  const [items, setItems] = useState<TravelPackage[] | null>(null);
  const [editing, setEditing] = useState<TravelPackage | "new" | null>(null);
  const [filter, setFilter] = useState("");

  const load = () => get<TravelPackage[]>("/api/packages").then(setItems).catch(() => {});
  useEffect(() => { load(); }, []);

  const shown = (items ?? []).filter((p) =>
    `${p.title} ${p.destination} ${p.country} ${p.tags.join(" ")}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div>
      <PageHeader title="Travel packages" subtitle="The AI only offers what is listed here, at these prices and dates."
        actions={can("packages.manage") && <button className="btn btn-primary" onClick={() => setEditing("new")}>+ New package</button>} />
      <div className="toolbar"><input placeholder="Filter packages" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
      {items === null ? <div className="loading">Loading…</div> : shown.length === 0 ? <Empty>No packages yet.</Empty> : (
        <div className="pkg-grid">
          {shown.map((p) => (
            <div key={p.id} className={`pkg-card ${p.is_active ? "" : "inactive"}`}>
              <div className="pkg-cover" style={{ background: p.image_url ? `center / cover no-repeat url(${JSON.stringify(p.image_url)})` : gradientFor(p.destination) }}>
                <span>{p.destination}, {p.country}</span>
                {p.is_featured && <span className="pkg-flag">★ Featured</span>}
              </div>
              <div className="pkg-body">
                <h3>{p.title}</h3>
                <div className="muted small">{p.duration_days} days · {p.hotel_name ?? "Hotel TBA"}{p.hotel_stars ? ` ${"★".repeat(p.hotel_stars)}` : ""}</div>
                <div className="pkg-price">{money(p.price_per_person, p.currency)} <span className="muted small">/ person</span></div>
                <div className="muted small">
                  {p.departure_dates.length ? `Next: ${p.departure_dates.slice(0, 3).map(shortDate).join(", ")}` : "Flexible dates"}
                  {p.seats_available != null && ` · ${p.seats_available} seats`}
                </div>
                <div className="tag-row">
                  {!p.is_active && <Badge tone="gray">Hidden</Badge>}
                  {p.tags.map((t) => <span key={t} className="tag">{t}</span>)}
                </div>
                {can("packages.manage") && <button className="btn btn-sm" onClick={() => setEditing(p)}>Edit</button>}
              </div>
            </div>
          ))}
        </div>
      )}
      {editing && (
        <PackageForm pkg={editing === "new" ? null : editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

function PackageForm({ pkg, onClose, onSaved }: { pkg: TravelPackage | null; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<FormState>(pkg ? toForm(pkg) : EMPTY);
  const [newDate, setNewDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF({ ...f, [k]: v });

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const body = {
      title: f.title, destination: f.destination, country: f.country, description: f.description,
      duration_days: Number(f.duration_days), price_per_person: Number(f.price_per_person),
      child_price: optNum(f.child_price), currency: f.currency.trim() || null, departure_dates: f.departure_dates,
      includes: lines(f.includes), excludes: lines(f.excludes),
      tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean),
      hotel_name: f.hotel_name || null, hotel_stars: optNum(f.hotel_stars), seats_available: optNum(f.seats_available),
      image_url: f.image_url || null, is_active: f.is_active, is_featured: f.is_featured,
    };
    try {
      if (pkg) await put(`/api/packages/${pkg.id}`, body);
      else await post("/api/packages", body);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const remove = async () => {
    if (!pkg || !confirm(`Delete "${pkg.title}"? Packages with bookings are hidden instead of deleted.`)) return;
    try {
      await del(`/api/packages/${pkg.id}`);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <Modal title={pkg ? `Edit ${pkg.title}` : "New package"} onClose={onClose} wide>
      <form onSubmit={save}>
        <div className="form-grid">
          <Field label="Title"><input value={f.title} onChange={(e) => set("title", e.target.value)} required /></Field>
          <Field label="Destination (city / region)"><input value={f.destination} onChange={(e) => set("destination", e.target.value)} required /></Field>
          <Field label="Country"><input value={f.country} onChange={(e) => set("country", e.target.value)} required /></Field>
          <Field label="Duration (days)"><input type="number" min={1} value={f.duration_days} onChange={(e) => set("duration_days", e.target.value)} required /></Field>
          <Field label="Price per adult"><input type="number" min={0} step="0.01" value={f.price_per_person} onChange={(e) => set("price_per_person", e.target.value)} required /></Field>
          <Field label="Price per child" hint="Empty = same as adult"><input type="number" min={0} step="0.01" value={f.child_price} onChange={(e) => set("child_price", e.target.value)} /></Field>
          <Field label="Currency" hint="Empty = company currency"><input maxLength={3} value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></Field>
          <Field label="Seats available" hint="Empty = unlimited"><input type="number" min={0} value={f.seats_available} onChange={(e) => set("seats_available", e.target.value)} /></Field>
          <Field label="Hotel"><input value={f.hotel_name} onChange={(e) => set("hotel_name", e.target.value)} /></Field>
          <Field label="Hotel stars"><input type="number" min={1} max={7} value={f.hotel_stars} onChange={(e) => set("hotel_stars", e.target.value)} /></Field>
        </div>
        <Field label="Description / itinerary" hint="The AI reads this to answer customer questions.">
          <textarea rows={4} value={f.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <Field label="Departure dates" hint="Leave empty for flexible dates on request.">
          <div className="date-chips">
            {f.departure_dates.map((d) => (
              <span key={d} className="chip">{shortDate(d)}
                <button type="button" onClick={() => set("departure_dates", f.departure_dates.filter((x) => x !== d))}>×</button>
              </span>
            ))}
            <input type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} />
            <button type="button" className="btn btn-sm" disabled={!newDate} onClick={() => {
              if (!f.departure_dates.includes(newDate)) set("departure_dates", [...f.departure_dates, newDate].sort());
              setNewDate("");
            }}>Add date</button>
          </div>
        </Field>
        <div className="form-grid">
          <Field label="Included (one per line)"><textarea rows={4} value={f.includes} onChange={(e) => set("includes", e.target.value)} /></Field>
          <Field label="Not included (one per line)"><textarea rows={4} value={f.excludes} onChange={(e) => set("excludes", e.target.value)} /></Field>
        </div>
        <Field label="Tags" hint="Comma separated: honeymoon, family, beach, umrah… helps the AI match requests.">
          <input value={f.tags} onChange={(e) => set("tags", e.target.value)} />
        </Field>
        <Field label="Image URL (optional)"><input value={f.image_url} onChange={(e) => set("image_url", e.target.value)} /></Field>
        <div className="row-gap">
          <label className="check"><input type="checkbox" checked={f.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Visible to customers and the AI</label>
          <label className="check"><input type="checkbox" checked={f.is_featured} onChange={(e) => set("is_featured", e.target.checked)} /> Featured</label>
        </div>
        <ErrorBox error={error} />
        <div className="modal-actions">
          {pkg && <button type="button" className="btn btn-danger" onClick={remove}>Delete</button>}
          <span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary">Save package</button>
        </div>
      </form>
    </Modal>
  );
}
