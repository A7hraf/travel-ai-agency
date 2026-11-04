import { useEffect, useState } from "react";
import { get } from "../api";
import { useAuth } from "../auth";
import { PageTitle } from "../components/admin/AdminUI";
import { Crown, Headset } from "../components/Icon";
import { Money } from "../components/Money";
import { endText, PaymentTable, PlanIncludes, StateBadge, UsageMeters } from "../components/plans/PlanUI";
import { ErrorBox, Loading } from "../components/ui";
import { useI18n } from "../lang";
import { CompanyPlan, CYCLE_LABELS, planDescription, planFeatures, planName } from "../plans";
import { shortDate } from "../util";

/** The company admin's plan: features, limits with usage, renewal, payments (read-only). */
export default function MyPlan() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const [data, setData] = useState<CompanyPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => { setError(null); get<CompanyPlan>("/api/company/plan").then(setData).catch((e) => setError(e.message)); };
  useEffect(load, []);

  const title = (
    <PageTitle kicker={t("Agency workspace")} title={t("My plan")}
      subtitle={t("Your plan, what it includes and what you use, your renewal date and payments.")} />
  );
  if (user?.role !== "company_admin") return <div className="pl-page">{title}<div className="error-box">{t("Only a company admin can see the plan and payments")}</div></div>;
  if (!data) return <div className="pl-page">{title}{error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={320} />}</div>;
  const p = data.plan;
  const features = planFeatures(p, lang);

  return (
    <div className="pl-page">
      {title}

      <section className="ad-card pl-current">
        <div className="pl-current-head">
          <span className="pl-card-icon" aria-hidden="true"><Crown weight="duotone" /></span>
          <div className="pl-current-name">
            <div className="ad-kicker">{t("Current plan")}</div>
            <h2 dir="auto">{planName(p, lang)}</h2>
          </div>
          <StateBadge state={data.state} />
        </div>
        {planDescription(p, lang) && <p className="pl-desc" dir="auto">{planDescription(p, lang)}</p>}
        <dl className="pl-facts">
          <div><dt>{t("Price")}</dt><dd><Money value={data.cycle_price} currency="OMR" /> <span className="pl-per">{data.billing_cycle === "yearly" ? t("/ year") : t("/ month")}</span></dd></div>
          <div><dt>{t("Billing")}</dt><dd>{t(CYCLE_LABELS[data.billing_cycle])}</dd></div>
          <div><dt>{t("Renewal")}</dt><dd>{endText(data.state, data.ends_on, t)}{data.days_left !== null && data.days_left >= 0 && <span className="pl-sub"> · {t("{n} days left", { n: data.days_left })}</span>}</dd></div>
          {data.state === "grace" && data.grace_until && <div><dt>{t("Pauses after")}</dt><dd className="warn-text">{shortDate(data.grace_until)}</dd></div>}
          {p.priority_support && <div><dt>{t("Support")}</dt><dd><span className="pl-tag">{t("Priority support")}</span></dd></div>}
        </dl>
        {features.length > 0 && <ul className="pl-features">{features.map((f) => <li key={f} dir="auto">{f}</li>)}</ul>}
        <div className="pl-contact"><Headset weight="duotone" aria-hidden="true" />
          <span>{t("To upgrade, renew or change your plan, contact the platform. Your data is always kept.")}</span></div>
      </section>

      <section className="ad-card">
        <h2 className="ad-card-title">{t("Limits and usage")}</h2>
        <UsageMeters usage={data.usage} />
      </section>

      <section className="ad-card">
        <h2 className="ad-card-title">{t("What your plan includes")}</h2>
        <PlanIncludes plan={p} />
      </section>

      <section className="ad-card">
        <h2 className="ad-card-title">{t("Payment history")}{data.payments_total > 0 && <span className="pl-sub">{t("Total")}: <Money value={data.payments_total} currency="OMR" /></span>}</h2>
        <PaymentTable payments={data.payments} invoiceBase="/app/plan/invoices" />
      </section>
    </div>
  );
}
