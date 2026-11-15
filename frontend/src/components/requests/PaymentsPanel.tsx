import { FormEvent, useEffect, useState } from "react";
import { fetchBlob, get, post } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
import type { Ticket, TicketPayment } from "../../types";
import { dateTime } from "../../util";
import { CheckCircle, Plus, Receipt, XCircle } from "../Icon";
import { moneyText } from "../Money";
import { ErrorBox } from "../ui";

const METHODS: Record<TicketPayment["method"], string> = {
  bank_transfer: "Bank transfer", cash: "Cash", card: "Card", link: "Payment link", other: "Other",
};

/** A receipt photo, fetched with the login (never public). */
function ReceiptImage({ ticketId, fileId }: { ticketId: number; fileId: number }) {
  const [url, setUrl] = useState<string | null>(null);
  const [pdf, setPdf] = useState(false);
  useEffect(() => {
    let made: string | null = null;
    let gone = false;
    fetchBlob(`/api/tickets/${ticketId}/files/${fileId}`).then(({ blob }) => {
      if (gone) return;
      if (blob.type === "application/pdf") { setPdf(true); return; }
      made = URL.createObjectURL(blob); setUrl(made);
    }).catch(() => {});
    return () => { gone = true; if (made) URL.revokeObjectURL(made); };
  }, [ticketId, fileId]);
  const { t } = useI18n();
  if (pdf) return <span className="rw-receipt pdf">PDF · {t("download it from Files")}</span>;
  return url ? <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={t("Payment receipt")} className="rw-receipt" /></a>
    : <span className="rw-receipt skeleton" aria-hidden="true" />;
}

function Review({ ticket, p, onChange }: { ticket: Ticket; p: TicketPayment; onChange: (t: Ticket) => void }) {
  const { t } = useI18n();
  const [amount, setAmount] = useState(ticket.money.balance ? String(ticket.money.balance) : "");
  const [reference, setReference] = useState("");
  const [method, setMethod] = useState<TicketPayment["method"]>("bank_transfer");
  const [refuse, setRefuse] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (path: string, body: unknown) => {
    setBusy(true); setError(null);
    try { onChange(await post<Ticket>(`/api/tickets/${ticket.id}/payments/${p.id}/${path}`, body)); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="rw-review">
      {p.file_id && <ReceiptImage ticketId={ticket.id} fileId={p.file_id} />}
      <div className="rw-review-main">
        <strong><Receipt weight="fill" /> {t("Receipt from the client")}</strong>
        <span className="muted small">{dateTime(p.created_at)} · {t("Check it in your bank, then write the amount received.")}</span>
        {!refuse ? (
          <form className="rw-review-form" onSubmit={(e: FormEvent) => { e.preventDefault(); run("approve", { amount, reference: reference || null, method }); }}>
            <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" dir="ltr" required placeholder={t("Amount received")} aria-label={t("Amount received")} />
            <input value={reference} onChange={(e) => setReference(e.target.value)} dir="ltr" maxLength={200} placeholder={t("Transfer number")} aria-label={t("Transfer number")} />
            <select value={method} onChange={(e) => setMethod(e.target.value as TicketPayment["method"])} aria-label={t("Method")}>
              {Object.entries(METHODS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
            </select>
            <div className="rw-row-end">
              <button type="button" className="btn btn-sm btn-ghost btn-danger-text" onClick={() => setRefuse(true)}><XCircle />{t("Refuse")}</button>
              <button className="btn btn-sm btn-primary" disabled={busy}><CheckCircle weight="fill" />{t("Approve")}</button>
            </div>
          </form>
        ) : (
          <form className="rw-review-form" onSubmit={(e: FormEvent) => { e.preventDefault(); run("reject", { note }); }}>
            <input value={note} onChange={(e) => setNote(e.target.value)} required minLength={3} maxLength={500} dir="auto"
              placeholder={t("Why (the client reads this)")} aria-label={t("Why (the client reads this)")} />
            <div className="rw-row-end">
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => setRefuse(false)}>{t("Back")}</button>
              <button className="btn btn-sm btn-danger" disabled={busy}>{t("Refuse and tell the client")}</button>
            </div>
          </form>
        )}
        <ErrorBox error={error} />
      </div>
    </div>
  );
}

/** Payments of a request: receipts to check, payments received (deposit, balance), and recording a payment. */
export default function PaymentsPanel({ ticket, onChange }: { ticket: Ticket; onChange: (t: Ticket) => void }) {
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const manage = can("tickets.manage");
  const m = ticket.money;
  const [adding, setAdding] = useState(false);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<TicketPayment["method"]>("bank_transfer");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<{ en: string; ar: string } | null>(null);
  useEffect(() => { get<{ en: string; ar: string }>("/api/payment-info").then(setInfo).catch(() => {}); }, []);
  const payable = ["pending_payment", "in_progress", "paid", "confirmed"].includes(ticket.status);
  const pending = ticket.payment_list.filter((p) => p.status === "pending");
  const done = ticket.payment_list.filter((p) => p.status !== "pending");
  const money = (v: number | null) => (v == null ? "—" : moneyText(v, ticket.currency, lang));

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      onChange(await post<Ticket>(`/api/tickets/${ticket.id}/payments`, { amount, method, reference: reference || null }));
      setAdding(false); setAmount(""); setReference("");
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };

  if (!payable) {
    return <p className="muted">{t("Payments start once the client approves the final quotation. They then get your payment details in the chat.")}</p>;
  }
  return (
    <div className="rw-pay">
      <div className="rw-pay-sum">
        <div><span className="muted small">{t("Total")}</span><strong>{money(m.total)}</strong></div>
        <div><span className="muted small">{t("Paid")}</span><strong>{money(m.paid)}</strong></div>
        <div className={m.balance ? "rw-due" : ""}><span className="muted small">{t("Balance")}</span><strong>{money(m.balance ?? 0)}</strong></div>
      </div>
      {m.total > 0 && <div className="rw-pay-bar" aria-hidden="true"><span style={{ width: `${Math.min(100, (m.paid / m.total) * 100)}%` }} /></div>}

      {pending.map((p) => <Review key={p.id} ticket={ticket} p={p} onChange={onChange} />)}

      <h4>{t("Payments")}</h4>
      {done.length === 0 ? <p className="muted small">{t("No payment yet.")}</p> : (
        <ul className="rw-pay-list">
          {done.map((p) => (
            <li key={p.id} className={p.status}>
              <span className="rw-pay-amount">{p.status === "rejected" ? t("Refused") : money(p.amount)}</span>
              <span className="muted small">
                {t(METHODS[p.method])}{p.reference ? <> · <bdi dir="ltr">{p.reference}</bdi></> : null} · {p.reviewed_by ?? p.created_by} · {dateTime(p.reviewed_at ?? p.created_at)}
                {p.note && <> · <span dir="auto">{p.note}</span></>}
              </span>
            </li>
          ))}
        </ul>
      )}
      {manage && !adding && (m.balance ?? 0) > 0 && (
        <button type="button" className="btn btn-soft" onClick={() => { setAmount(String(m.balance ?? "")); setAdding(true); }}><Plus />{t("Record a payment")}</button>
      )}
      {adding && (
        <form className="rw-card rw-review-form" onSubmit={add}>
          <h4>{t("Record a payment")}</h4>
          <p className="muted small">{t("A deposit or the balance, received by transfer, in cash at the office, by card…")}</p>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" dir="ltr" required placeholder={t("Amount")} aria-label={t("Amount")} />
          <select value={method} onChange={(e) => setMethod(e.target.value as TicketPayment["method"])} aria-label={t("Method")}>
            {Object.entries(METHODS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
          </select>
          <input value={reference} onChange={(e) => setReference(e.target.value)} dir="ltr" maxLength={200} placeholder={t("Transfer or receipt number")} aria-label={t("Transfer or receipt number")} />
          <ErrorBox error={error} />
          <div className="rw-row-end">
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setAdding(false)}>{t("Cancel")}</button>
            <button className="btn btn-sm btn-primary" disabled={busy}>{t("Save the payment")}</button>
          </div>
        </form>
      )}
      {info && (info.en || info.ar) && (
        <details className="rw-pay-info">
          <summary>{t("Payment details the client received")}</summary>
          <p dir="auto">{lang === "ar" ? info.ar || info.en : info.en || info.ar}</p>
        </details>
      )}
    </div>
  );
}
