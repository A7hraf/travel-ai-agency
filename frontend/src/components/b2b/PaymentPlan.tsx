import { FormEvent, useState } from "react";
import { post, put } from "../../api";
import { useI18n } from "../../lang";
import type { Amount, TripPayment } from "../../types";
import { shortDate } from "../../util";
import { Check, Plus, Trash } from "../Icon";
import { moneyText } from "../Money";
import { ErrorBox } from "../ui";

type Side = "staff" | "client" | "vendor";
interface Row { label: string; percent: string; due_date: string }

/**
 * The payments of a business trip, for each party: the client its share of the price, the vendor its share of
 * the cost, the travel company both (and it writes down what was paid). The vendor or the travel company set
 * the plan (shares with dates) while the trip isn't paid.
 */
export default function PaymentPlan<T>({ side, plan, currency, planUrl, paidUrl, canEdit, onChange }: {
  side: Side; plan: TripPayment[]; currency: string; planUrl?: string; paidUrl?: (stepId: number) => string;
  canEdit: boolean; onChange: (x: T) => void;
}) {
  const { t, lang } = useI18n();
  const [editing, setEditing] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const money = (v: Amount | undefined) => (v == null ? "—" : moneyText(Number(v), currency, lang));
  const run = async (fn: () => Promise<T>) => {
    setBusy(true); setError(null);
    try { onChange(await fn()); return true; } catch (e) { setError((e as Error).message); return false; } finally { setBusy(false); }
  };
  const total = (editing ?? []).reduce((a, r) => a + (Number(r.percent) || 0), 0);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!editing || !planUrl) return;
    const body = { steps: editing.map((r) => ({ label: r.label, percent: Number(r.percent), due_date: r.due_date || null })) };
    if (await run(() => put<T>(planUrl, body))) setEditing(null);
  };
  const anyPaid = plan.some((p) => p.paid || p.vendor_paid);

  return (
    <section className="gx-card">
      <h2 className="gx-card-title">{t("Payment plan")}</h2>
      {plan.length === 0 && !editing && <p className="muted small">{side === "client" ? t("The payment dates are shared here once your trip is approved.") : t("No payment plan yet.")}</p>}
      {plan.length > 0 && !editing && (
        <ul className="gx-pay-plan">
          {plan.map((p) => (
            <li key={p.id} className={p.paid ? "paid" : p.overdue ? "late" : ""}>
              <div>
                <strong dir="auto">{p.label}</strong> <span className="muted small">· {Number(p.percent)}%{p.due_date && ` · ${t("due {date}", { date: shortDate(p.due_date) })}`}</span>
                {p.overdue && <span className="pill st-cancelled">{t("Late")}</span>}
              </div>
              <div className="gx-pay-amounts">
                {side === "staff" ? (<>
                  <PaidToggle label={t("Client pays {v}", { v: money(p.amount) })} paid={p.paid} disabled={busy || !paidUrl}
                    onToggle={(paid) => paidUrl && run(() => post<T>(paidUrl(p.id), { side: "client", paid }))} />
                  <PaidToggle label={t("We pay the vendor {v}", { v: money(p.vendor_amount) })} paid={!!p.vendor_paid} disabled={busy || !paidUrl}
                    onToggle={(paid) => paidUrl && run(() => post<T>(paidUrl(p.id), { side: "vendor", paid }))} />
                </>) : (
                  <span>{money(p.amount)} · {p.paid ? <span className="gx-wf-paid"><Check /> {t("paid")}</span> : <span className="muted">{t("not paid yet")}</span>}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <form className="gx-qx-form" onSubmit={save}>
          {editing.map((r, i) => (
            <div key={i} className="gx-pay-row">
              <input aria-label={t("Payment")} value={r.label} required minLength={2} maxLength={80} dir="auto" placeholder={t("e.g. Deposit")}
                onChange={(e) => setEditing(editing.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
              <label className="gx-wf-val"><input aria-label={t("Share")} type="number" min={1} max={100} step="0.01" required value={r.percent}
                onChange={(e) => setEditing(editing.map((x, j) => (j === i ? { ...x, percent: e.target.value } : x)))} /><span>%</span></label>
              <input aria-label={t("Due date")} type="date" value={r.due_date} dir="ltr"
                onChange={(e) => setEditing(editing.map((x, j) => (j === i ? { ...x, due_date: e.target.value } : x)))} />
              <button type="button" className="icon-btn" aria-label={t("Remove")} disabled={editing.length === 1} onClick={() => setEditing(editing.filter((_, j) => j !== i))}><Trash /></button>
            </div>
          ))}
          {editing.length < 8 && <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing([...editing, { label: "", percent: "", due_date: "" }])}><Plus />{t("Add a payment")}</button>}
          <p className={`small ${total === 100 ? "muted" : "gx-bad"}`}>{t("Total: {n}% (must be 100%)", { n: total })}</p>
          <div className="gx-wf-save">
            <button className="btn btn-sm btn-primary" disabled={busy || total !== 100}>{t("Save the plan")}</button>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setEditing(null)}>{t("Cancel")}</button>
          </div>
        </form>
      )}
      {canEdit && planUrl && !editing && !anyPaid && (
        <button type="button" className="btn btn-soft btn-sm" onClick={() => setEditing(plan.length
          ? plan.map((p) => ({ label: p.label, percent: String(Number(p.percent)), due_date: p.due_date ?? "" }))
          : [{ label: t("Deposit"), percent: "50", due_date: "" }, { label: t("Balance"), percent: "50", due_date: "" }])}>
          {plan.length ? t("Change the plan") : t("Set the payment plan")}
        </button>
      )}
      <ErrorBox error={error} />
    </section>
  );
}

function PaidToggle({ label, paid, disabled, onToggle }: { label: string; paid: boolean; disabled: boolean; onToggle: (paid: boolean) => void }) {
  return (
    <label className={`gx-feat-check ${paid ? "gx-wf-paid" : ""}`}>
      <input type="checkbox" checked={paid} disabled={disabled} onChange={(e) => onToggle(e.target.checked)} /> {label}
    </label>
  );
}
