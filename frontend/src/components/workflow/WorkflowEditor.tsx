import { useI18n } from "../../lang";
import type { StepType, WorkflowStep } from "../../types";
import { ArrowDown, ArrowUp, Check, Plus, Trash } from "../Icon";

export const STEP_TYPES: { type: StepType; en: string; ar: string; hint: string }[] = [
  { type: "intake", en: "Request details", ar: "تفاصيل الطلب", hint: "The AI gathers the answers to the service's questions." },
  { type: "review", en: "Team review", ar: "مراجعة الفريق", hint: "The team checks the request and asks for anything missing." },
  { type: "quote", en: "Quotation", ar: "عرض السعر", hint: "Choices and the final quotation, until the client approves." },
  { type: "documents", en: "Client documents", ar: "مستندات العميل", hint: "The papers the service needs (passport copy…)." },
  { type: "payment", en: "Payment", ar: "الدفع", hint: "One installment: a percent, a fixed amount or the rest." },
  { type: "schedule", en: "Appointment", ar: "الموعد", hint: "The client's possible times, the time you book, the client's confirmation." },
  { type: "booking", en: "Booking", ar: "الحجز", hint: "The booking checklist of the service." },
  { type: "delivery", en: "Travel documents", ar: "وثائق السفر", hint: "Tickets, vouchers and visas sent to the client." },
  { type: "trip", en: "Trip", ar: "الرحلة", hint: "Ends by itself the day after the return date." },
  { type: "feedback", en: "Feedback", ar: "التقييم", hint: "Ends when the client rates the trip." },
  { type: "task", en: "Task", ar: "مهمة", hint: "Any other step done by the team." },
];
const ONCE: StepType[] = ["intake", "review", "quote", "documents", "booking", "delivery", "trip", "feedback"];
export const STEP_LABEL = Object.fromEntries(STEP_TYPES.map((s) => [s.type, s]));

/** A new step key that no other step has. */
function freshKey(steps: WorkflowStep[], type: StepType): string {
  const keys = new Set(steps.map((s) => s.key));
  if (!keys.has(type)) return type;
  let n = 2;
  while (keys.has(`${type}_${n}`)) n += 1;
  return `${type}_${n}`;
}

/** The problems the server would refuse, checked while editing. */
export function workflowProblems(steps: WorkflowStep[]): string[] {
  const out: string[] = [];
  if (!steps.length) out.push("A workflow needs at least one step");
  if (steps.some((s) => s.type === "intake") && steps[0]?.type !== "intake") out.push("Request details must be the first step");
  for (const type of ONCE) if (steps.filter((s) => s.type === type).length > 1) out.push("Some steps can only be there once");
  const pays = steps.filter((s) => s.type === "payment");
  const pct = pays.filter((s) => s.pay_mode === "percent").reduce((a, s) => a + Number(s.pay_value || 0), 0);
  if (pct > 100) out.push("The payments add up to more than 100%");
  if (pays.length && pays[pays.length - 1].pay_mode !== "rest") out.push("The last payment must be the rest of the amount");
  if (pays.filter((s) => s.pay_mode === "rest").length > 1) out.push("Only the last payment can be the rest of the amount");
  for (const s of pays) {
    if (s.pay_mode === "percent" && !(Number(s.pay_value) > 0 && Number(s.pay_value) <= 100)) out.push("A payment in percent needs a value between 1 and 100");
    if (s.pay_mode === "fixed" && !(Number(s.pay_value) > 0)) out.push("A fixed payment needs its amount");
  }
  return [...new Set(out)];
}

/** What the server takes for a step (state and times stay on the server). */
export function stepBody(s: WorkflowStep) {
  return { key: s.key, type: s.type, label_en: s.label_en, label_ar: s.label_ar,
    pay_mode: s.type === "payment" ? s.pay_mode ?? "rest" : null, pay_value: s.type === "payment" && s.pay_mode !== "rest" ? s.pay_value ?? null : null };
}

/**
 * The ordered steps of a workflow. The first `locked` steps (done or started on a request) can't be changed.
 */
export default function WorkflowEditor({ steps, onChange, locked = 0, currency, disabled }: {
  steps: WorkflowStep[]; onChange: (steps: WorkflowStep[]) => void; locked?: number; currency: string; disabled?: boolean;
}) {
  const { t, lang } = useI18n();
  const set = (i: number, patch: Partial<WorkflowStep>) => onChange(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const move = (i: number, d: number) => {
    const next = [...steps];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange(next);
  };
  const add = (type: StepType) => {
    const info = STEP_LABEL[type];
    const step: WorkflowStep = { key: freshKey(steps, type), type, label_en: type === "task" ? "" : info.en, label_ar: type === "task" ? "" : info.ar,
      pay_mode: type === "payment" ? "rest" : null, pay_value: null };
    onChange([...steps, step]);
  };
  const canAdd = STEP_TYPES.filter((x) => !ONCE.includes(x.type) || !steps.some((s) => s.type === x.type));
  const problems = workflowProblems(steps);

  return (
    <div className="gx-wf">
      <ol className="gx-wf-list">
        {steps.map((s, i) => {
          const fixed = disabled || i < locked;
          const info = STEP_LABEL[s.type];
          return (
            <li key={s.key} className={`gx-wf-step ${fixed ? "locked" : ""} ${s.state ?? ""}`}>
              <span className="gx-wf-n">{s.state === "done" || s.state === "skipped" ? <Check weight="bold" /> : i + 1}</span>
              <div className="gx-wf-body">
                <div className="gx-wf-row">
                  <span className="gx-wf-type">{lang === "ar" ? info?.ar : info?.en}</span>
                  {!fixed && (
                    <span className="gx-wf-tools">
                      <button type="button" className="btn btn-ghost btn-icon btn-sm" disabled={i <= locked} aria-label={t("Move up")} onClick={() => move(i, -1)}><ArrowUp /></button>
                      <button type="button" className="btn btn-ghost btn-icon btn-sm" disabled={i === steps.length - 1} aria-label={t("Move down")} onClick={() => move(i, 1)}><ArrowDown /></button>
                      <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label={t("Remove")} onClick={() => onChange(steps.filter((_, j) => j !== i))}><Trash /></button>
                    </span>
                  )}
                </div>
                {fixed ? (
                  <span className="gx-wf-name"><bdi>{lang === "ar" ? s.label_ar : s.label_en}</bdi>
                    {s.type === "payment" && s.pay_mode !== "rest" && <span className="muted"> · {s.pay_mode === "percent" ? `${s.pay_value}%` : `${s.pay_value} ${currency}`}</span>}
                  </span>
                ) : (
                  <>
                    <div className="gx-wf-names">
                      <input aria-label={t("Name in English")} placeholder={t("Name in English")} dir="ltr" maxLength={80} value={s.label_en}
                        onChange={(e) => set(i, { label_en: e.target.value })} />
                      <input aria-label={t("Name in Arabic")} placeholder={t("Name in Arabic")} dir="rtl" maxLength={80} value={s.label_ar}
                        onChange={(e) => set(i, { label_ar: e.target.value })} />
                    </div>
                    {s.type === "payment" && (
                      <div className="gx-wf-pay">
                        <select aria-label={t("Amount")} value={s.pay_mode ?? "rest"} onChange={(e) => set(i, { pay_mode: e.target.value as WorkflowStep["pay_mode"], pay_value: null })}>
                          <option value="rest">{t("The rest of the amount")}</option>
                          <option value="percent">{t("A percent of the total")}</option>
                          <option value="fixed">{t("A fixed amount")}</option>
                        </select>
                        {s.pay_mode && s.pay_mode !== "rest" && (
                          <label className="gx-wf-val"><input type="number" min={s.pay_mode === "percent" ? 1 : 0.001} max={s.pay_mode === "percent" ? 100 : undefined}
                            step="any" inputMode="decimal" value={s.pay_value ?? ""} onChange={(e) => set(i, { pay_value: e.target.value })} />
                            <span>{s.pay_mode === "percent" ? "%" : currency}</span></label>
                        )}
                      </div>
                    )}
                    <small className="muted">{t(info?.hint ?? "")}</small>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {!disabled && (
        <div className="gx-wf-add">
          <span className="muted small">{t("Add a step")}</span>
          {canAdd.map((x) => (
            <button key={x.type} type="button" className="btn btn-soft btn-sm" onClick={() => add(x.type)}><Plus />{lang === "ar" ? x.ar : x.en}</button>
          ))}
        </div>
      )}
      {problems.length > 0 && <ul className="gx-wf-problems" role="alert">{problems.map((p) => <li key={p}>{t(p)}</li>)}</ul>}
    </div>
  );
}
