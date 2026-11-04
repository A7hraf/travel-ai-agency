import { FormEvent, useEffect, useState } from "react";
import { del, get, patch, post } from "../../api";
import { useI18n } from "../../lang";
import {
  CYCLE_LABELS, METHOD_LABELS, Payment, Plan, planName, STATE_LABELS, STATUS_OPTIONS, Subscription,
} from "../../plans";
import { shortDate, todayIso } from "../../util";
import { ConfirmSheet } from "../admin/AdminUI";
import { CalendarPlus, Crown, Hourglass, Prohibit, Receipt } from "../Icon";
import { Money } from "../Money";
import { ErrorBox, Field, Modal } from "../ui";
import { endText, PaymentTable, PlanIncludes, StateBadge, UsageMeters } from "./PlanUI";

/** The platform owner's view of one company's plan: status, usage, actions, payments. */
export default function SubscriptionPanel({ companyId, onChanged }: { companyId: number; onChanged?: () => void }) {
  const { t, lang } = useI18n();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [sheet, setSheet] = useState<"cancel" | "trial" | "payment" | null>(null);
  const [trialDays, setTrialDays] = useState("14");
  const [deleting, setDeleting] = useState<Payment | null>(null);

  const base = `/api/system/companies/${companyId}`;
  const loadPayments = () => get<{ payments: Payment[] }>(`${base}/payments`).then((r) => setPayments(r.payments)).catch(() => {});
  useEffect(() => {
    get<Subscription>(`${base}/subscription`).then(setSub).catch((e) => setError(e.message));
    get<Plan[]>("/api/system/plans").then(setPlans).catch(() => {});
    loadPayments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const act = async (what: string, run: () => Promise<Subscription>, done?: string) => {
    if (busy) return;
    setBusy(what);
    setError(null);
    setNotice(null);
    try {
      setSub(await run());
      setNotice(done ?? t("Saved."));
      onChanged?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
      setSheet(null);
    }
  };

  if (!sub) return error ? <div className="error-box">{error}</div> : <div className="skeleton" style={{ height: 260, borderRadius: 24 }} />;
  const p = sub.plan;
  const custom = sub.custom_price !== null;

  return (
    <div className="pl-sub-panel">
      <section className="ad-card pl-current">
        <div className="pl-current-head">
          <span className="pl-card-icon" aria-hidden="true"><Crown weight="duotone" /></span>
          <div className="pl-current-name">
            <div className="ad-kicker">{t("Current plan")}</div>
            <h2 dir="auto">{planName(p, lang)}</h2>
          </div>
          <StateBadge state={sub.state} />
        </div>
        <dl className="pl-facts">
          <div><dt>{t("Price")}</dt><dd><Money value={sub.cycle_price} currency="OMR" /> <span className="pl-per">{sub.billing_cycle === "yearly" ? t("/ year") : t("/ month")}</span>{custom && <span className="pl-tag">{t("Custom price")}</span>}</dd></div>
          <div><dt>{t("Billing")}</dt><dd>{t(CYCLE_LABELS[sub.billing_cycle])}</dd></div>
          <div><dt>{t("Period")}</dt><dd>{sub.status === "trial" ? `${t("Trial")}: ${shortDate(sub.trial_end)}` : `${shortDate(sub.current_period_start)} – ${shortDate(sub.current_period_end)}`}</dd></div>
          <div><dt>{t("Renewal")}</dt><dd>{endText(sub.state, sub.ends_on, t)}{sub.days_left !== null && sub.days_left >= 0 && <span className="pl-sub"> · {t("{n} days left", { n: sub.days_left })}</span>}</dd></div>
          {(sub.state === "grace" || sub.state === "past_due") && sub.grace_until && (
            <div><dt>{t("Pauses after")}</dt><dd className="warn-text">{shortDate(sub.grace_until)}</dd></div>
          )}
          <div><dt>{t("Paid so far")}</dt><dd><Money value={sub.payments_total} currency="OMR" /></dd></div>
        </dl>
        {sub.state === "expired" && <div className="warn-box">{t("Expired: the AI and the customer page are paused. Staff can still log in and see a renewal banner. Nothing is deleted.")}</div>}
        <div className="pl-quick">
          <button type="button" className="btn btn-primary" disabled={!!busy} onClick={() => setSheet("payment")}><Receipt />{t("Record payment")}</button>
          <button type="button" className="btn btn-soft" disabled={!!busy} onClick={() => act("m1", () => post(`${base}/subscription/extend`, { months: 1 }), t("Extended by 1 month."))}>
            <CalendarPlus />{busy === "m1" ? t("Please wait…") : t("+1 month")}</button>
          <button type="button" className="btn btn-soft" disabled={!!busy} onClick={() => act("y1", () => post(`${base}/subscription/extend`, { months: 12 }), t("Extended by 1 year."))}>
            <CalendarPlus />{busy === "y1" ? t("Please wait…") : t("+1 year")}</button>
          <button type="button" className="btn btn-ghost" disabled={!!busy} onClick={() => { setTrialDays(String(p.trial_days || 14)); setSheet("trial"); }}>
            <Hourglass />{t("Start trial")}</button>
          {sub.status !== "cancelled" && (
            <button type="button" className="btn btn-ghost danger-text" disabled={!!busy} onClick={() => setSheet("cancel")}><Prohibit />{t("Mark cancelled")}</button>
          )}
        </div>
        <ErrorBox error={error} />
        {notice && <div className="ok-box ad-notice" role="status">{notice}</div>}
      </section>

      <section className="ad-card">
        <h2 className="ad-card-title">{t("Usage")}</h2>
        <UsageMeters usage={sub.usage} />
      </section>

      <SubscriptionForm key={`${sub.plan.id}-${sub.status}-${sub.current_period_end}-${sub.trial_end}-${sub.max_users}`}
        sub={sub} plans={plans} busy={busy === "form"}
        onSave={(body) => act("form", () => patch(`${base}/subscription`, body))} />

      <section className="ad-card">
        <h2 className="ad-card-title">{t("What the plan includes")}</h2>
        <PlanIncludes plan={p} />
      </section>

      <section className="ad-card">
        <h2 className="ad-card-title">{t("Payment history")}<span className="spacer" />
          <button type="button" className="btn btn-sm btn-soft" onClick={() => setSheet("payment")}><Receipt />{t("Record payment")}</button>
        </h2>
        <PaymentTable payments={payments} invoiceBase="/system/invoices" onDelete={setDeleting} busy={!!busy} />
      </section>

      {sheet === "cancel" && (
        <ConfirmSheet title={t("Mark the subscription as cancelled?")} tone="danger" busy={busy === "cancel"}
          text={t("Everything keeps working until the end of the paid period ({date}). Then the AI and the customer page pause. Nothing is deleted.", { date: shortDate(sub.ends_on) })}
          confirmLabel={t("Mark cancelled")} onConfirm={() => act("cancel", () => post(`${base}/subscription/cancel`))}
          onCancel={() => setSheet(null)} />
      )}
      {sheet === "trial" && (
        <ConfirmSheet title={t("Start a trial")} busy={busy === "trial"}
          text={t("The company uses the {plan} plan for free until the trial ends.", { plan: planName(p, lang) })}
          confirmLabel={t("Start trial")} confirmDisabled={!(Number(trialDays) >= 1)}
          onConfirm={() => act("trial", () => post(`${base}/subscription/trial`, { days: Number(trialDays) }))}
          onCancel={() => setSheet(null)}>
          <label className="field">
            <span className="field-label">{t("Trial days")}</span>
            <input type="number" min={1} max={365} value={trialDays} onChange={(e) => setTrialDays(e.target.value)} />
          </label>
        </ConfirmSheet>
      )}
      {sheet === "payment" && (
        <PaymentForm sub={sub} onClose={() => setSheet(null)} onSaved={async () => {
          setSheet(null);
          setNotice(t("Payment recorded."));
          await loadPayments();
          get<Subscription>(`${base}/subscription`).then(setSub).catch(() => {});
          onChanged?.();
        }} base={base} />
      )}
      {deleting && (
        <ConfirmSheet title={t("Delete payment {n}?", { n: deleting.invoice_number })} tone="danger"
          text={t("Only for a payment recorded by mistake. The subscription period does not change.")}
          confirmLabel={t("Delete payment")} onCancel={() => setDeleting(null)}
          onConfirm={async () => {
            try {
              await del(`/api/system/payments/${deleting.id}`);
              setDeleting(null);
              await loadPayments();
              get<Subscription>(`${base}/subscription`).then(setSub).catch(() => {});
            } catch (err) {
              setError((err as Error).message);
              setDeleting(null);
            }
          }} />
      )}
    </div>
  );
}

function SubscriptionForm({ sub, plans, busy, onSave }: {
  sub: Subscription; plans: Plan[]; busy: boolean; onSave: (body: Record<string, unknown>) => void;
}) {
  const { t, lang } = useI18n();
  const [f, setF] = useState({
    plan_id: String(sub.plan.id), billing_cycle: sub.billing_cycle, status: sub.status,
    current_period_start: sub.current_period_start ?? "", current_period_end: sub.current_period_end ?? "",
    trial_end: sub.trial_end ?? "", custom_price: sub.custom_price === null ? "" : String(sub.custom_price),
    account_limit: sub.max_users_custom ? String(sub.max_users) : "", notes: sub.notes,
  });
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  const choices = plans.filter((x) => !x.is_archived || x.id === sub.plan.id);
  const chosen = plans.find((x) => String(x.id) === f.plan_id) ?? sub.plan;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSave({
      plan_id: Number(f.plan_id), billing_cycle: f.billing_cycle, status: f.status,
      current_period_start: f.current_period_start || null, current_period_end: f.current_period_end || null,
      trial_end: f.trial_end || null, custom_price: f.custom_price.trim() === "" ? null : Number(f.custom_price),
      account_limit: f.account_limit.trim() === "" ? null : Number(f.account_limit), notes: f.notes,
    });
  };

  return (
    <form className="ad-card" onSubmit={submit}>
      <h2 className="ad-card-title">{t("Change plan and period")}</h2>
      <div className="ad-grid-2">
        <Field label={t("Plan")}>
          <select value={f.plan_id} onChange={(e) => set("plan_id", e.target.value)}>
            {choices.map((x) => (
              <option key={x.id} value={x.id}>{planName(x, lang)}{x.is_archived ? ` (${t("Archived")})` : ""}</option>
            ))}
          </select>
        </Field>
        <Field label={t("Billing")}>
          <select value={f.billing_cycle} onChange={(e) => set("billing_cycle", e.target.value)}>
            <option value="monthly">{t("Monthly")}</option>
            <option value="yearly">{t("Yearly")}</option>
          </select>
        </Field>
        <Field label={t("Status")}>
          <select value={f.status} onChange={(e) => set("status", e.target.value)}>
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{t(STATE_LABELS[s])}</option>)}
          </select>
        </Field>
        <Field label={t("Trial ends")} hint={f.status === "trial" ? undefined : t("Only used while the status is Trial.")}>
          <input type="date" value={f.trial_end} onChange={(e) => set("trial_end", e.target.value)} required={f.status === "trial"} />
        </Field>
        <Field label={t("Period starts")}><input type="date" value={f.current_period_start} onChange={(e) => set("current_period_start", e.target.value)} /></Field>
        <Field label={t("Period ends")} hint={t("Last paid day.")}><input type="date" value={f.current_period_end} onChange={(e) => set("current_period_end", e.target.value)} /></Field>
        <Field label={t("Custom price (OMR)")} hint={t("Empty: the plan's price ({price}).", {
          price: String(f.billing_cycle === "yearly" ? chosen.price_yearly : chosen.price_monthly) })}>
          <input type="number" min={0} step="0.001" value={f.custom_price} onChange={(e) => set("custom_price", e.target.value)} dir="ltr" />
        </Field>
        <Field label={t("Account limit")} hint={t("Empty: follows the plan ({n} accounts). Currently {used} active.", {
          n: chosen.max_users, used: sub.usage.users })}>
          <input type="number" min={1} max={10000} value={f.account_limit} placeholder={String(chosen.max_users)} onChange={(e) => set("account_limit", e.target.value)} />
        </Field>
      </div>
      <Field label={t("Internal notes")} hint={t("Only you see these.")}>
        <textarea rows={2} value={f.notes} onChange={(e) => set("notes", e.target.value)} maxLength={4000} dir="auto" />
      </Field>
      <div className="ad-form-actions"><button className="btn btn-primary" disabled={busy}>{busy ? t("Saving…") : t("Save")}</button></div>
    </form>
  );
}

function PaymentForm({ sub, base, onClose, onSaved }: { sub: Subscription; base: string; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({
    amount: String(sub.next_period.amount || ""), paid_on: todayIso(), method: "bank_transfer", reference: "",
    period_start: sub.next_period.start, period_end: sub.next_period.end, notes: "", extend: true,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string | boolean) => setF({ ...f, [k]: v });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await post(`${base}/payments`, {
        ...f, amount: Number(f.amount), period_start: f.period_start || null, period_end: f.period_end || null,
      });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <Modal title={t("Record payment")} onClose={onClose} wide>
      <form onSubmit={submit}>
        <div className="ad-grid-2">
          <Field label={t("Amount (OMR)")}><input type="number" min={0.001} step="0.001" value={f.amount} onChange={(e) => set("amount", e.target.value)} required dir="ltr" /></Field>
          <Field label={t("Paid on")}><input type="date" value={f.paid_on} onChange={(e) => set("paid_on", e.target.value)} required /></Field>
          <Field label={t("Method")}>
            <select value={f.method} onChange={(e) => set("method", e.target.value)}>
              {Object.entries(METHOD_LABELS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
            </select>
          </Field>
          <Field label={t("Reference")} hint={t("Transfer number, receipt or card slip.")}><input value={f.reference} maxLength={200} onChange={(e) => set("reference", e.target.value)} dir="auto" /></Field>
          <Field label={t("Covers from")}><input type="date" value={f.period_start} onChange={(e) => set("period_start", e.target.value)} /></Field>
          <Field label={t("Covers until")}><input type="date" value={f.period_end} onChange={(e) => set("period_end", e.target.value)} /></Field>
        </div>
        <Field label={t("Notes")}><textarea rows={2} value={f.notes} maxLength={2000} onChange={(e) => set("notes", e.target.value)} dir="auto" /></Field>
        <label className="check pl-check">
          <input type="checkbox" checked={f.extend} onChange={(e) => set("extend", e.target.checked)} />
          {t("Extend the subscription until the end of this period")}
        </label>
        <ErrorBox error={error} />
        <div className="modal-actions"><span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t("Cancel")}</button>
          <button className="btn btn-primary" disabled={busy} aria-busy={busy}>{busy ? t("Saving…") : t("Record payment")}</button>
        </div>
      </form>
    </Modal>
  );
}
