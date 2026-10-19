import { Link, useSearchParams } from "react-router-dom";
import { PageTitle } from "../components/admin/AdminUI";
import TrainingWorkspace, { type TrainingTab } from "../components/ai/TrainingWorkspace";
import { ArrowRight } from "../components/Icon";
import { useI18n } from "../lang";

const TABS: TrainingTab[] = ["answers", "knowledge", "try"];

export default function Training() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab") as TrainingTab | null;
  const tab: TrainingTab = raw && TABS.includes(raw) ? raw : "answers";

  return (
    <div className="narrow ad-narrow">
      <PageTitle kicker={t("Agency workspace")} title={t("AI training")}
        subtitle={t("Teach your AI consultant how your company answers. When a customer asks something similar, in Arabic or English, the AI answers your way.")} />
      <TrainingWorkspace base="/api/training" tab={tab}
        onTab={(next) => setParams(next === "answers" ? {} : { tab: next }, { replace: true })}
        settingsLink={<Link to="/app/settings" className="btn btn-ghost">{t("AI & WhatsApp settings")} <ArrowRight className="flip" /></Link>} />
    </div>
  );
}
