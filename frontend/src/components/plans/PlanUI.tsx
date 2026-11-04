import { Link } from "react-router-dom";
import { useI18n } from "../../lang";
import { METHOD_LABELS, Payment, periodText, Plan, STATE_LABELS, STATE_TONES, SubState, Usage } from "../../plans";
import "../../styles/plans.css";
import { shortDate } from "../../util";
import { Check, Receipt, Trash, X } from "../Icon";
import { Money } from "../Money";

export function StateBadge({ state }: { state: SubState }) {
  const { t } = useI18n();
  return <span className={`ad-status ${STATE_TONES[state] ?? "off"}`}>{t(STATE_LABELS[state] ?? state)}</span>;
}

/** "Renews on …", "Trial ends on …", "Ended on …" for the end date of a subscription. */
export function endText(state: SubState, endsOn: string | null, t: (s: string, v?: Record<string, string | number>) => string) {
  if (!endsOn) return t("No end date");
  const date = shortDate(endsOn);
  if (state === "trial") return t("Trial ends on {date}", { date });
  if (state === "cancelled") return t("Ends on {date}", { date });
  if (state === "expired" || state === "grace") return t("Ended on {date}", { date });
  return t("Renews on {date}", { date });
}

function Meter({ label, used, limit }: { label: string; used: number; limit: number | null }) {
  const { t } = useI18n();
  const pct = limit === null ? 0 : limit === 0 ? 100 : Math.min(100, (used / limit) * 100);
  const full = limit !== null && used >= limit;
  return (
    <div className="pl-meter">
      <div className="pl-meter-row">
        <span>{label}</span>
        <span className="tnum" dir="ltr">{limit === null ? `${used} / ∞` : `${used} / ${limit}`}</span>
      </div>
      <div className={`tm-meter ${full ? "full" : ""} ${limit === null ? "unlimited" : ""}`} role="meter"
        aria-label={label} aria-valuemin={0} aria-valuemax={limit ?? used} aria-valuenow={used}>
        <div style={{ width: `${limit === null ? 100 : pct}%` }} />
      </div>
      {limit === null && <div className="pl-meter-note">{t("Unlimited")}</div>}
      {full && limit !== null && <div className="pl-meter-note warn">{t("Limit reached")}</div>}
    </div>
  );
}

export function UsageMeters({ usage }: { usage: Usage }) {
  const { t } = useI18n();
  return (
    <div className="pl-meters">
      <Meter label={t("Staff accounts")} used={usage.users} limit={usage.max_users} />
      <Meter label={t("Active packages")} used={usage.packages} limit={usage.max_packages} />
      <Meter label={t("AI conversations this month")} used={usage.ai_conversations} limit={usage.max_ai_conversations} />
    </div>
  );
}

const limitText = (n: number | null, t: (s: string) => string) => (n === null ? t("Unlimited") : String(n));

/** What a plan includes, as a check list (website always included). */
export function PlanIncludes({ plan }: { plan: Plan }) {
  const { t } = useI18n();
  const rows: [string, boolean | string][] = [
    [t("Staff accounts"), String(plan.max_users)],
    [t("Packages"), limitText(plan.max_packages, t)],
    [t("AI conversations per month"), limitText(plan.max_ai_conversations, t)],
    [t("Website chat"), true],
    [t("WhatsApp"), plan.allow_whatsapp],
    [t("Instagram"), plan.allow_instagram],
    [t("Customer page editor"), plan.allow_page_editor],
    [t("Hide \"Powered by Ghanjah\""), plan.allow_remove_powered_by],
    [t("Priority support"), plan.priority_support],
  ];
  return (
    <ul className="pl-includes">
      {rows.map(([label, v]) => (
        <li key={label} className={v === false ? "no" : ""}>
          {typeof v === "string"
            ? <><span className="pl-inc-num tnum">{v}</span><span>{label}</span></>
            : <>{v ? <Check weight="bold" className="pl-yes" aria-label={t("Included")} /> : <X weight="bold" className="pl-no" aria-label={t("Not included")} />}<span>{label}</span></>}
        </li>
      ))}
    </ul>
  );
}

/** Payment history; `invoiceBase` is the invoice page path ("/system/invoices" or "/app/plan/invoices"). */
export function PaymentTable({ payments, invoiceBase, onDelete, busy }: {
  payments: Payment[];
  invoiceBase: string;
  onDelete?: (p: Payment) => void;
  busy?: boolean;
}) {
  const { t } = useI18n();
  if (!payments.length) return <p className="muted pl-empty">{t("No payments recorded yet.")}</p>;
  return (
    <div className="pl-table-wrap">
      <table className="pl-table">
        <thead>
          <tr>
            <th>{t("Date")}</th><th>{t("Invoice")}</th><th>{t("Amount")}</th><th>{t("Method")}</th>
            <th>{t("Period")}</th><th><span className="sr-only">{t("Actions")}</span></th>
          </tr>
        </thead>
        <tbody>
          {payments.map((p) => (
            <tr key={p.id}>
              <td data-label={t("Date")}>{shortDate(p.paid_on)}</td>
              <td data-label={t("Invoice")}><bdi dir="ltr" className="pl-mono">{p.invoice_number}</bdi></td>
              <td data-label={t("Amount")} className="tnum"><Money value={p.amount} currency={p.currency} /></td>
              <td data-label={t("Method")}>
                {t(METHOD_LABELS[p.method] ?? p.method)}
                {p.reference && <div className="pl-sub" dir="auto">{p.reference}</div>}
              </td>
              <td data-label={t("Period")}>{periodText(p.period_start, p.period_end)}</td>
              <td className="pl-actions">
                <Link className="btn btn-sm btn-soft" to={`${invoiceBase}/${p.id}`} target="_blank" rel="noopener">
                  <Receipt />{t("Invoice")}
                </Link>
                {onDelete && (
                  <button type="button" className="icon-btn" disabled={busy} onClick={() => onDelete(p)}
                    aria-label={`${t("Delete payment")} ${p.invoice_number}`}><Trash /></button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
