import { Navigate } from "react-router-dom";
import { homePath, useAuth } from "../auth";
import ActivityLog from "../components/ActivityLog";
import { PageTitle } from "../components/admin/AdminUI";
import { useI18n } from "../lang";

/** Company admins: who did what (logins, accounts, packages, bookings, design, AI and channels). */
export default function Activity() {
  const { user } = useAuth();
  const { t } = useI18n();
  if (!user) return null;
  if (user.role !== "company_admin") return <Navigate to={homePath(user)} replace />;
  return (
    <div className="narrow ad-narrow">
      <PageTitle kicker={t("Agency workspace")} title={t("Activity")}
        subtitle={t("Important changes made by your team: logins, accounts, packages, bookings, the customer page, AI training and channels.")} />
      <ActivityLog path="/api/activity" />
    </div>
  );
}
