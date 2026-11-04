import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { get } from "../api";
import { GhanjahMark, usePlatformName } from "../components/Brand";
import { ArrowLeft, Printer } from "../components/Icon";
import { Money } from "../components/Money";
import { ErrorBox, Loading } from "../components/ui";
import { LangSwitch, useI18n } from "../lang";
import { CYCLE_LABELS, Invoice as InvoiceT, METHOD_LABELS, periodText } from "../plans";
import "../styles/plans.css";
import { shortDate } from "../util";

/** A printable invoice for one payment (the browser's print dialog saves it as PDF). */
export default function Invoice({ owner }: { owner?: boolean }) {
  const { id } = useParams();
  const { t } = useI18n();
  const platform = usePlatformName();
  const [inv, setInv] = useState<InvoiceT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    setError(null);
    const path = owner ? `/api/system/payments/${id}/invoice` : `/api/company/plan/payments/${id}/invoice`;
    get<InvoiceT>(path).then((x) => { setInv(x); document.title = `${x.payment.invoice_number} · ${x.company.name}`; })
      .catch((e) => setError(e.message));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [id, owner]);

  const back = owner ? (inv ? `/system/companies/${inv.payment.company_id}` : "/system") : "/app/plan";
  return (
    <div className="inv-page">
      <div className="inv-tools no-print">
        <Link className="btn btn-ghost" to={back}><ArrowLeft className="flip" />{t("Back")}</Link>
        <span className="spacer" />
        <LangSwitch className="btn btn-ghost" />
        <button type="button" className="btn btn-primary" onClick={() => window.print()} disabled={!inv}><Printer />{t("Print")}</button>
      </div>
      {!inv && <div style={{ maxWidth: 820, margin: "0 auto" }}>{error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={320} label={t("Loading the invoice…")} />}</div>}
      {inv && (
        <article className="inv-sheet">
          <header className="inv-head">
            <div className="inv-brand"><GhanjahMark className="inv-mark" /><strong>{platform}</strong></div>
            <div className="inv-title">
              <h1>{t("Invoice")}</h1>
              <bdi dir="ltr">{inv.payment.invoice_number}</bdi>
            </div>
          </header>
          <div className="inv-parties">
            <div>
              <div className="inv-label">{t("Billed to")}</div>
              <strong dir="auto">{inv.company.name}</strong>
              {inv.company.contact_email && <div dir="ltr">{inv.company.contact_email}</div>}
              {inv.company.contact_phone && <div dir="ltr">{inv.company.contact_phone}</div>}
              <div dir="ltr" className="inv-muted">/c/{inv.company.slug}</div>
            </div>
            <div>
              <div className="inv-label">{t("Payment date")}</div>
              <strong>{shortDate(inv.payment.paid_on)}</strong>
              <div className="inv-label">{t("Method")}</div>
              <div>{t(METHOD_LABELS[inv.payment.method] ?? inv.payment.method)}{inv.payment.reference && <> · <bdi dir="auto">{inv.payment.reference}</bdi></>}</div>
            </div>
          </div>
          <table className="inv-table">
            <thead><tr><th>{t("Description")}</th><th>{t("Period")}</th><th className="num">{t("Amount")}</th></tr></thead>
            <tbody>
              <tr>
                <td dir="auto">{t("{plan} plan, {cycle}", { plan: inv.payment.plan_name || "—", cycle: t(CYCLE_LABELS[inv.payment.billing_cycle] ?? inv.payment.billing_cycle) })}
                  {inv.payment.notes && <div className="inv-muted" dir="auto">{inv.payment.notes}</div>}</td>
                <td>{periodText(inv.payment.period_start, inv.payment.period_end)}</td>
                <td className="num"><Money value={inv.payment.amount} currency={inv.payment.currency} /></td>
              </tr>
            </tbody>
            <tfoot><tr><td colSpan={2}>{t("Total paid")}</td><td className="num"><Money value={inv.payment.amount} currency={inv.payment.currency} /></td></tr></tfoot>
          </table>
          <p className="inv-paid">{t("Paid. Thank you!")}</p>
          <footer className="inv-foot">{t("{platform} · AI travel platform from Oman", { platform })}</footer>
        </article>
      )}
    </div>
  );
}
