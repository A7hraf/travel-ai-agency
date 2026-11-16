import { FormEvent, useState } from "react";
import { post, put } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { Ticket, TicketOption } from "../../types";
import ImageUpload from "../ImageUpload";
import { Sparkle, Trash } from "../Icon";
import { ErrorBox } from "../ui";

const MAX_PHOTOS = 6;

/** How one item looks on the quotation: its description and photos (editable until the request closes). */
export function PresentationForm({ ticket, option, onChange, onClose }: {
  ticket: Ticket; option: TicketOption; onChange: (t: Ticket) => void; onClose: () => void;
}) {
  const { t } = useI18n();
  const [details, setDetails] = useState(option.details ?? "");
  const [cover, setCover] = useState<string | null>(option.image_url);
  const [photos, setPhotos] = useState<string[]>(option.photos ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      onChange(await put<Ticket>(`/api/tickets/${ticket.id}/options/${option.id}/presentation`, { details: details || null, image_url: cover, photos }));
      onClose();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <form className="gx-qx-form" onSubmit={save}>
      <label className="rw-lbl"><span>{t("Description on the quotation")}</span>
        <textarea rows={3} dir="auto" maxLength={2000} value={details} onChange={(e) => setDetails(e.target.value)} /></label>
      <div className="gx-qx-photos">
        <div className="gx-qx-cover"><ImageUpload value={cover} onChange={setCover} label={t("Main photo")} maxSide={1600} /></div>
        {photos.map((url) => (
          <figure key={url} className="gx-qx-photo">
            <img src={url} alt="" />
            <button type="button" className="icon-btn" aria-label={t("Remove")} onClick={() => setPhotos(photos.filter((x) => x !== url))}><Trash /></button>
          </figure>
        ))}
        {photos.length < MAX_PHOTOS && (
          <div className="gx-qx-add"><ImageUpload key={photos.length} value={null} onChange={(url) => url && setPhotos([...photos, url])} label={t("Add a photo")} maxSide={1600} /></div>
        )}
      </div>
      <ErrorBox error={error} />
      <div className="gx-wf-save">
        <button className="btn btn-sm btn-primary" disabled={busy}>{t("Save")}</button>
        <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>{t("Cancel")}</button>
      </div>
    </form>
  );
}

/** The quotation of this request: the AI writes the descriptions; its reference and a note for the client. */
export function QuoteTools({ ticket, onChange }: { ticket: Ticket; onChange: (t: Ticket) => void }) {
  const { t, lang } = useI18n();
  const { user, can } = useAuth();
  const writer = !!user?.company?.addons?.includes("quote_writer");
  const meta = ticket.quote_meta ?? {};
  const [open, setOpen] = useState(false);
  const [reference, setReference] = useState(meta.reference ?? "");
  const [noteEn, setNoteEn] = useState(meta.note_en ?? "");
  const [noteAr, setNoteAr] = useState(meta.note_ar ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!can("tickets.manage") || ticket.stage === "closed") return null;
  const run = async (fn: () => Promise<Ticket>) => {
    setBusy(true); setError(null);
    try { onChange(await fn()); return true; } catch (e) { setError((e as Error).message); return false; } finally { setBusy(false); }
  };
  const missing = ticket.options.filter((o) => (o.sent_to_client || o.price != null) && !(o.details ?? "").trim()).length;
  return (
    <div className="gx-qx-tools">
      <div className="gx-wf-save">
        {writer && missing > 0 && (
          <button type="button" className="btn btn-sm btn-soft" disabled={busy}
            onClick={() => run(() => post<Ticket>(`/api/tickets/${ticket.id}/quotation/ai-details?lang=${lang}`, {}))}>
            <Sparkle weight="fill" />{busy ? t("The AI is writing…") : t("Write {n} descriptions with AI", { n: missing })}
          </button>
        )}
        <button type="button" className="btn btn-sm btn-ghost" aria-expanded={open} onClick={() => setOpen(!open)}>{t("Quotation reference and note")}</button>
      </div>
      {open && (
        <form className="gx-qx-form" onSubmit={async (e) => {
          e.preventDefault();
          if (await run(() => put<Ticket>(`/api/tickets/${ticket.id}/quotation`, { reference, note_en: noteEn, note_ar: noteAr }))) setOpen(false);
        }}>
          <label className="rw-lbl"><span>{t("Quotation reference")}</span>
            <input value={reference} onChange={(e) => setReference(e.target.value.toUpperCase())} maxLength={40} pattern="[A-Za-z0-9-]*" dir="ltr"
              placeholder={ticket.reference} /></label>
          {user?.role !== "company_admin" && <small className="muted">{t("Your company admin is told when the reference changes.")}</small>}
          <div className="gx-wf-names">
            <label className="rw-lbl"><span>{t("Note for the client (English)")}</span><textarea rows={2} dir="ltr" maxLength={1500} value={noteEn} onChange={(e) => setNoteEn(e.target.value)} /></label>
            <label className="rw-lbl"><span>{t("Note for the client (Arabic)")}</span><textarea rows={2} dir="rtl" maxLength={1500} value={noteAr} onChange={(e) => setNoteAr(e.target.value)} /></label>
          </div>
          <div className="gx-wf-save"><button className="btn btn-sm btn-primary" disabled={busy}>{t("Save")}</button></div>
        </form>
      )}
      <ErrorBox error={error} />
    </div>
  );
}
