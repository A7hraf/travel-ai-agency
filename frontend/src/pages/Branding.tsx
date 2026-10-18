import { useAuth } from "../auth";
import BrandingEditor from "../components/BrandingEditor";
import { PageTitle } from "../components/admin/AdminUI";
import { useI18n } from "../lang";

export default function Branding() {
  const { user, refresh } = useAuth();
  const { t } = useI18n();
  if (!user?.company) return null;
  return (
    <div>
      <PageTitle kicker={t("Agency workspace")} title={t("Customer page design")}
        subtitle={t("Your colours, logo, texts and the layout of the page your customers see.")} />
      <BrandingEditor loadPath="/api/company/branding" uploadPath="/api/media" slug={user.company.slug} name={user.company.name}
        onSaved={() => { refresh().catch(() => {}); }} />
    </div>
  );
}
