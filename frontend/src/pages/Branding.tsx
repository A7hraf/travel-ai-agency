import { useAuth } from "../auth";
import BrandingEditor from "../components/BrandingEditor";
import { PageHeader } from "../components/ui";
import { useI18n } from "../lang";

export default function Branding() {
  const { user, refresh } = useAuth();
  const { t } = useI18n();
  if (!user?.company) return null;
  return (
    <div>
      <PageHeader title={t("Customer page design")}
        subtitle={t("Your colours, logo, texts and the layout of the page your customers see.")} />
      <BrandingEditor loadPath="/api/company/branding" uploadPath="/api/media" slug={user.company.slug}
        onSaved={() => { refresh().catch(() => {}); }} />
    </div>
  );
}
