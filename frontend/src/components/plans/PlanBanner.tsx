import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { get } from "../../api";
import { useAuth } from "../../auth";
import { useI18n } from "../../lang";
// Also loads the plan texts in Arabic for every agency page (server messages about limits).
import "../../plans";
import type { PlanNotice } from "../../plans";
import "../../styles/plans.css";
import { shortDate } from "../../util";
import { Hourglass, WarningCircle } from "../Icon";

/** Top banner of the agency app: trial ending soon, payment due, or expired (AI and page paused). */
export default function PlanBanner() {
  const { user } = useAuth();
  const { t } = useI18n();
  const location = useLocation();
  const [notice, setNotice] = useState<PlanNotice | null>(null);
  const onPlanPage = location.pathname.startsWith("/app/plan");
  useEffect(() => {
    if (!user?.company) return;
    get<PlanNotice>("/api/company/plan/notice").then(setNotice).catch(() => {});
    // Fetched again when the person moves to another page (cheap: one small query).
  }, [user?.company, location.pathname]);

  if (!notice?.banner) return null;
  const date = shortDate(notice.ends_on);
  const days = notice.days_left ?? 0;
  const text = {
    trial_ending: days <= 0 ? t("Your free trial ends today.") : t("Your free trial ends in {n} days ({date}).", { n: days, date }),
    past_due: t("Your subscription payment is due. Everything keeps working until {date}, then the AI and your customer page pause.", { date: shortDate(notice.grace_until) }),
    expired: t("Your subscription has expired: the AI and your customer page are paused. Your data is kept."),
    cancelled: t("Your plan was cancelled and ends on {date}.", { date }),
  }[notice.banner];
  const bad = notice.banner === "expired" || notice.banner === "past_due";
  return (
    <div className={`plan-banner ${bad ? "bad" : ""}`} role={bad ? "alert" : "status"}>
      {bad ? <WarningCircle weight="fill" aria-hidden="true" /> : <Hourglass weight="fill" aria-hidden="true" />}
      <span>{text} {notice.banner === "trial_ending" ? t("Contact the platform to choose a plan.") : t("Contact the platform to renew.")}</span>
      {user?.role === "company_admin" && !onPlanPage && <Link className="btn btn-sm" to="/app/plan">{t("My plan")}</Link>}
    </div>
  );
}
