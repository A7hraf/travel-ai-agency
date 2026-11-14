import { ChangeEvent, useEffect, useState } from "react";
import { api, download, fetchBlob, post, readFileBase64 } from "../../api";
import { useAuth } from "../../auth";
import { trServer, useI18n } from "../../lang";
import type { RequestFile, Ticket } from "../../types";
import { dateTime } from "../../util";
import { CheckCircle, DownloadSimple, FilePdf, PaperPlaneRight, Paperclip, Receipt, Trash } from "../Icon";
import { ErrorBox } from "../ui";

const KIND_LABELS: Record<RequestFile["kind"], string> = {
  payment_proof: "Payment proof", client_file: "From the client", document: "Travel document",
};
const DOCS_STEP = "documents";
const ACCEPT = "image/jpeg,image/png,image/webp,application/pdf";

/** A photo the staff can look at right here (payment receipts), fetched with the login. */
function Preview({ ticketId, file }: { ticketId: number; file: RequestFile }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let gone = false;
    let made: string | null = null;
    fetchBlob(`/api/tickets/${ticketId}/files/${file.id}`).then(({ blob }) => {
      if (gone) return;
      made = URL.createObjectURL(blob);
      setUrl(made);
    }).catch(() => {});
    return () => { gone = true; if (made) URL.revokeObjectURL(made); };
  }, [ticketId, file.id]);
  return url ? <img className="gx-rq-thumb" src={url} alt={file.name} /> : <span className="gx-rq-thumb skeleton" aria-hidden="true" />;
}

/** After the client approves: their payment proof and papers, the booking checklist, and the travel documents. */
export default function BookingPanel({ ticket, onChange }: { ticket: Ticket; onChange: (t: Ticket) => void }) {
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<RequestFile["kind"]>("document");
  const [note, setNote] = useState("");
  const manage = can("tickets.manage");
  const base = `/api/tickets/${ticket.id}`;
  const closed = ticket.status === "cancelled" || ticket.status === "rejected";
  const files = ticket.request_files ?? [];
  const steps = ticket.booking_steps ?? [];
  const paid = ticket.status === "paid";
  const unsent = files.filter((f) => f.kind === "document" && !f.sent_at);
  const stepsLeft = steps.filter((s) => s.key !== DOCS_STEP && !s.done);
  const canSend = manage && (paid ? stepsLeft.length === 0 : ticket.status === "confirmed" && unsent.length > 0);
  const show = files.length > 0 || ["pending_payment", "in_progress", "paid", "confirmed"].includes(ticket.status);
  if (!show) return null;

  const run = async (fn: () => Promise<Ticket>) => {
    setBusy(true);
    setError(null);
    try { onChange(await fn()); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const list = [...(e.target.files ?? [])];
    e.target.value = "";
    for (const file of list) {
      if (file.size > 6_000_000) { setError(t("The file is too large (maximum 6 MB)")); continue; }
      const data = await readFileBase64(file).catch(() => null);
      if (data === null) continue;
      await run(() => post<Ticket>(`${base}/files`, { kind, name: file.name, content_type: file.type, data_base64: data }));
    }
  };

  return (
    <section className="gx-rq-booking" aria-label={t("Payment and booking")}>
      {files.length > 0 && (
        <>
          <h3>{t("Files")}</h3>
          <ul className="gx-rq-files">
            {files.map((f) => (
              <li key={f.id} className={`gx-rq-file ${f.kind}`}>
                {f.content_type.startsWith("image/") ? <Preview ticketId={ticket.id} file={f} />
                  : <span className="gx-rq-thumb pdf" aria-hidden="true"><FilePdf weight="duotone" /></span>}
                <span className="gx-rq-file-main">
                  <strong dir="auto">{f.name}</strong>
                  <span className="muted small">
                    {f.kind === "payment_proof" && <Receipt weight="fill" />} {t(KIND_LABELS[f.kind])} · {f.uploaded_by === "client" ? t("the client") : f.uploaded_by} · {dateTime(f.created_at)}
                    {f.sent_at && <> · <strong className="gx-rq-chosen">{t("sent to the client")}</strong></>}
                  </span>
                </span>
                <button type="button" className="icon-btn" aria-label={t("Download {name}", { name: f.name })}
                  onClick={() => download(`${base}/files/${f.id}`, f.name).catch((e) => setError((e as Error).message))}><DownloadSimple /></button>
                {manage && !f.sent_at && (
                  <button type="button" className="icon-btn" aria-label={t("Remove")} disabled={busy}
                    onClick={() => run(() => api<Ticket>("DELETE", `${base}/files/${f.id}`))}><Trash /></button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {ticket.status === "in_progress" && files.some((f) => f.kind === "payment_proof") && (
        <p className="gx-rq-hint" role="note"><Receipt weight="fill" /> {t("The client sent a payment proof: check it, write the transfer number in Payment reference, then mark as paid.")}</p>
      )}

      {steps.length > 0 && ["paid", "confirmed"].includes(ticket.status) && (
        <>
          <h3>{t("Booking checklist")}</h3>
          <ul className="gx-rq-steps">
            {steps.map((s) => (
              <li key={s.key} className={s.done ? "done" : ""}>
                <label>
                  <input type="checkbox" checked={s.done} disabled={!manage || !paid || busy || s.key === DOCS_STEP}
                    onChange={(e) => run(() => post<Ticket>(`${base}/checklist`, { step: s.key, done: e.target.checked }))} />
                  <span dir="auto">{lang === "ar" ? s.label_ar || s.label_en : s.label_en}</span>
                </label>
                <span className="muted small">
                  {s.done && s.by ? `${s.by} · ${s.at ? dateTime(s.at) : ""}` : s.key === DOCS_STEP ? t("Done when you send the documents") : ""}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {manage && !closed && (
        <div className="gx-rq-upload">
          <select value={kind} onChange={(e) => setKind(e.target.value as RequestFile["kind"])} aria-label={t("Kind of file")}>
            <option value="document">{t("Travel document")}</option>
            <option value="payment_proof">{t("Payment proof")}</option>
            <option value="client_file">{t("From the client")}</option>
          </select>
          <label className="btn btn-sm btn-soft">
            <Paperclip />{t("Add files (photo or PDF)")}
            <input type="file" accept={ACCEPT} multiple hidden disabled={busy} onChange={upload} />
          </label>
        </div>
      )}

      {manage && (paid || (ticket.status === "confirmed" && unsent.length > 0)) && (
        <div className="gx-rq-final">
          <h4>{paid ? t("Send the documents and confirm") : t("Send the new documents")}</h4>
          <p className="muted small">
            {unsent.length
              ? t("Documents to send: {n}. They go to the client on WhatsApp and on their private trips page.", { n: unsent.length })
              : t("No documents added: the client gets the confirmation message only.")}
          </p>
          {paid && stepsLeft.length > 0 && <p className="muted small">{t("Tick the booking steps first ({n} left).", { n: stepsLeft.length })}</p>}
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} dir="auto"
            placeholder={t("Note for the client (optional)")} aria-label={t("Note for the client")} />
          <button type="button" className="btn btn-primary" disabled={!canSend || busy}
            onClick={() => run(() => post<Ticket>(`${base}/send-documents`, { note: note || null })).then(() => setNote(""))}>
            {paid ? <CheckCircle weight="fill" /> : <PaperPlaneRight className="flip" />}{paid ? t("Send and confirm") : t("Send")}
          </button>
        </div>
      )}
      {ticket.notice && <div className="tk-cancelled" role="status">{trServer(ticket.notice)}</div>}
      <ErrorBox error={error} />
    </section>
  );
}
