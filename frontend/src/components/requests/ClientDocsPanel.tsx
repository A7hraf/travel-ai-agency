import { ChangeEvent, useState } from "react";
import { api, patch, post, readFileBase64 } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { RequestFile, Ticket } from "../../types";
import { dateTime } from "../../util";
import { CheckCircle, Circle, Paperclip, Trash, WarningCircle } from "../Icon";
import { ErrorBox } from "../ui";
import FileThumb from "./FileThumb";

const ACCEPT = "image/jpeg,image/png,image/webp,application/pdf";

/** What the client must send for this service (passport copies…), what came in, and papers to sort. */
export default function ClientDocsPanel({ ticket, onChange }: { ticket: Ticket; onChange: (t: Ticket) => void }) {
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const manage = can("tickets.manage");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const docs = ticket.client_documents;
  const byId = new Map(ticket.request_files.map((f) => [f.id, f]));
  const fromClient = ticket.request_files.filter((f) => f.kind === "client_file");
  const closed = ticket.stage === "closed";

  const run = async (fn: () => Promise<Ticket>) => {
    setBusy(true); setError(null);
    try { onChange(await fn()); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const sort = (f: RequestFile, value: string) => run(() => patch<Ticket>(`/api/tickets/${ticket.id}/files/${f.id}`,
    value === "payment_proof" ? { kind: "payment_proof" } : { kind: "client_file", requirement: value || null }));
  // Staff add a paper the client gave them (by email, at the office) for one document.
  const upload = async (e: ChangeEvent<HTMLInputElement>, requirement: string | null) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 6_000_000) { setError(t("The file is too large (maximum 6 MB)")); return; }
    await run(async () => {
      const data = await readFileBase64(file);
      const tk = await post<Ticket>(`/api/tickets/${ticket.id}/files`, { kind: "client_file", name: file.name, content_type: file.type, data_base64: data });
      const added = tk.request_files.reduce((a, b) => (b.id > a.id ? b : a));
      return requirement ? patch<Ticket>(`/api/tickets/${ticket.id}/files/${added.id}`, { kind: "client_file", requirement }) : tk;
    });
  };
  const sorter = (f: RequestFile) => manage && (
    <select value={f.requirement ?? ""} disabled={busy} onChange={(e) => sort(f, e.target.value)} aria-label={t("What is this file?")}>
      <option value="">{t("Not sorted")}</option>
      {docs.items.map((d) => <option key={d.key} value={d.key}>{lang === "ar" ? d.label_ar || d.label_en : d.label_en}</option>)}
      {["pending_payment", "in_progress", "paid", "confirmed"].includes(ticket.status) && <option value="payment_proof">{t("Payment receipt")}</option>}
    </select>
  );
  const row = (f: RequestFile) => (
    <li key={f.id} className="rw-file">
      <FileThumb ticketId={ticket.id} file={f} onError={setError} />
      <span className="rw-file-main">
        <strong dir="auto">{f.name}</strong>
        <span className="muted small">{f.uploaded_by === "client" ? t("the client") : f.uploaded_by} · {dateTime(f.created_at)}</span>
      </span>
      {sorter(f)}
      {manage && !f.sent_at && <button type="button" className="icon-btn" aria-label={t("Remove")} disabled={busy}
        onClick={() => run(() => api<Ticket>("DELETE", `/api/tickets/${ticket.id}/files/${f.id}`))}><Trash /></button>}
    </li>
  );

  return (
    <div className="rw-docs">
      {docs.items.length === 0 ? (
        <p className="muted">{t("This service needs no documents from the client. Add some in Services if it should.")}</p>
      ) : (
        <ul className="rw-req-list">
          {docs.items.map((d) => (
            <li key={d.key} className={d.done ? "done" : d.required ? "missing" : ""}>
              <div className="rw-req-head">
                {d.done ? <CheckCircle weight="fill" className="ok" /> : d.required ? <WarningCircle weight="fill" className="warn" /> : <Circle />}
                <strong>{lang === "ar" ? d.label_ar || d.label_en : d.label_en}</strong>
                <span className="muted small">{d.have} / {d.need}{!d.required && ` · ${t("optional")}`}</span>
                <span className="spacer" />
                {manage && !closed && (
                  <label className="btn btn-sm btn-ghost"><Paperclip />{t("Add")}
                    <input type="file" accept={ACCEPT} hidden disabled={busy} onChange={(e) => upload(e, d.key)} /></label>
                )}
              </div>
              {d.files.length > 0 && <ul className="rw-file-list">{d.files.map((id) => byId.get(id)).filter(Boolean).map((f) => row(f!))}</ul>}
            </li>
          ))}
        </ul>
      )}
      {docs.unsorted.length > 0 && (
        <>
          <h4><WarningCircle weight="fill" className="warn" /> {t("From the client, to sort ({n})", { n: docs.unsorted.length })}</h4>
          <p className="muted small">{t("Say which document each file is, so the missing list is right.")}</p>
          <ul className="rw-file-list">{docs.unsorted.map((id) => byId.get(id)).filter(Boolean).map((f) => row(f!))}</ul>
        </>
      )}
      {fromClient.length === 0 && docs.items.length > 0 && (
        <p className="muted small">{t("Nothing received yet. The client sends photos or PDFs in the chat (writing what each one is), or on their trips page.")}</p>
      )}
      {manage && !closed && docs.items.length === 0 && (
        <label className="btn btn-sm btn-soft"><Paperclip />{t("Add a client paper")}
          <input type="file" accept={ACCEPT} hidden disabled={busy} onChange={(e) => upload(e, null)} /></label>
      )}
      <ErrorBox error={error} />
    </div>
  );
}
