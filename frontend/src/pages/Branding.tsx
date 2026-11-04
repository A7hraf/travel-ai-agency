import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";
import BrandingEditor from "../components/BrandingEditor";
import { PageTitle } from "../components/admin/AdminUI";
import { useI18n } from "../lang";
import type { PlanNotice } from "../plans";

export default function Branding() {
  const { user, refresh } = useAuth();
  const { t } = useI18n();
  // The plan decides whether the page editor is included and whether "Powered by" can be hidden.
  const [notice, setNotice] = useState<PlanNotice | null>(null);
  useEffect(() => { get<PlanNotice>("/api/company/plan/notice").then(setNotice).catch(() => {}); }, []);
  if (!user?.company) return null;
  const locked = notice !== null && !notice.page_editor;
  return (
    <div>
      <PageTitle kicker={t("Agency workspace")} title={t("Customer page design")}
        subtitle={t("Your colours, logo, texts and the layout of the page your customers see.")} />
      {locked && (
        <div className="warn-box" role="status">
          {t("Your plan does not include the page editor: you can look at the design, but changes can't be saved. Contact the platform to upgrade.")}
          {user.role === "company_admin" && <> <Link to="/app/plan">{t("My plan")}</Link></>}
        </div>
      )}
      <BrandingEditor loadPath="/api/company/branding" uploadPath="/api/media" slug={user.company.slug} name={user.company.name}
        canHidePoweredBy={!!notice?.remove_powered_by}
        onSaved={() => { refresh().catch(() => {}); }} />
    </div>
  );
}
