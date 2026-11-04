import { FormEvent, useState } from "react";
import { download } from "../api";
import { useI18n } from "../lang";
import { TICKET_STATUS_LABELS, todayIso } from "../util";
import { DownloadSimple } from "./Icon";
import { ErrorBox, Field, Modal } from "./ui";

type What = "tickets" | "payments";

/** "Export CSV" button with a small form: bookings or payments, date range and (bookings) status.
 *  The server checks the permissions (reports.view and tickets.view). */
export default function ExportCsv({ className = "btn btn-ghost", initial = "tickets" }: { className?: string; initial?: What }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [what, setWhat] = useState<What>(initial);
  const first = new Date();
  first.setDate(1);
  const [from, setFrom] = useState(`${first.getFullYear()}-${String(first.getMonth() + 1).padStart(2, "0")}-01`);
  const [to, setTo] = useState(todayIso());
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams();
      if (from) q.set("date_from", from);
      if (to) q.set("date_to", to);
      if (what === "tickets" && status) q.set("status", status);
      await download(`/api/exports/${what}.csv?${q}`, `${what}.csv`);
      setOpen(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" className={className} onClick={() => { setError(null); setOpen(true); }}>
        <DownloadSimple aria-hidden="true" />{t("Export CSV")}
      </button>
      {open && (
        <Modal title={t("Export CSV")} onClose={() => setOpen(false)}>
          <form onSubmit={submit}>
            <p className="ad-card-note" style={{ marginTop: 0 }}>
              {t("A file for Excel or Google Sheets. Dates are your local days; both days are included.")}
            </p>
            <div className="chips" role="group" aria-label={t("What to export")} style={{ marginBottom: 14 }}>
              <button type="button" className={`chip-btn ${what === "tickets" ? "active" : ""}`} aria-pressed={what === "tickets"}
                onClick={() => setWhat("tickets")}>{t("Bookings")}</button>
              <button type="button" className={`chip-btn ${what === "payments" ? "active" : ""}`} aria-pressed={what === "payments"}
                onClick={() => setWhat("payments")}>{t("Payments")}</button>
            </div>
            <div className="ad-grid-2">
              <Field label={what === "payments" ? t("Paid from") : t("Created from")}>
                <input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
              </Field>
              <Field label={t("Until")}>
                <input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
              </Field>
            </div>
            {what === "tickets" && (
              <Field label={t("Status")}>
                <select value={status} onChange={(e) => setStatus(e.target.value)}>
                  <option value="">{t("All statuses")}</option>
                  <option value="open">{t("Open (waiting or in progress)")}</option>
                  {Object.entries(TICKET_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
                </select>
              </Field>
            )}
            {what === "payments" && <p className="bt-muted">{t("Paid and confirmed bookings, dated by the day they were marked as paid.")}</p>}
            <ErrorBox error={error} />
            <div className="ad-form-actions">
              <button className="btn btn-primary" disabled={busy}><DownloadSimple aria-hidden="true" />{busy ? t("Preparing…") : t("Download")}</button>
              <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>{t("Cancel")}</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
