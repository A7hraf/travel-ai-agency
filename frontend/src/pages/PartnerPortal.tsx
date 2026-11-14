import { CSSProperties, useEffect, useState } from "react";
import { get } from "../api";
import { useAuth } from "../auth";
import {
  Briefcase, ChartBar, ChatCircleDots, ClockCounterClockwise, Crown, PaperPlaneTilt, SignOut, Tag, Translate, WhatsappLogo,
} from "../components/Icon";
import type { IconProps } from "../components/Icon";
import { ErrorBox, Loading } from "../components/ui";
import { useI18n } from "../lang";
import { dashboardVars } from "../theme";
import { useTheme } from "../themeMode";
import type { PartnerHome } from "../types";

const ICONS: Record<string, React.ComponentType<IconProps>> = {
  "client.requests": PaperPlaneTilt, "client.whatsapp": WhatsappLogo, "client.ai_chat": ChatCircleDots,
  "client.history": ClockCounterClockwise, "client.exclusive_packages": Crown, "client.reports": ChartBar,
  "vendor.requests": Briefcase, "vendor.quotes": Tag, "vendor.history": ClockCounterClockwise,
};

/** The portal of a business client or vendor login: its own space, apart from the travel company's staff app. */
export default function PartnerPortal() {
  const { user, logout } = useAuth();
  const { t, lang, setLang } = useI18n();
  const { theme } = useTheme();
  const [home, setHome] = useState<PartnerHome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => get<PartnerHome>("/api/partner/home").then((h) => { setHome(h); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => { load(); }, []);

  const b = user?.company?.branding;
  const style = dashboardVars(b?.dashboard_color, b?.dashboard_sidebar, theme) as CSSProperties;
  const kindLabel = home?.kind === "vendor" ? t("Vendor") : t("Business client");

  return (
    <div className="gx-portal" style={style} dir={lang === "ar" ? "rtl" : "ltr"}>
      <header className="gx-portal-top">
        <div className="gx-portal-brand">
          {home?.logo ? <img src={home.logo} alt="" /> : null}
          <span dir="auto">{home?.company_name ?? user?.company?.name}</span>
        </div>
        <span className="spacer" />
        <button type="button" className="btn btn-sm btn-ghost" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
          <Translate />{lang === "ar" ? "English" : "العربية"}
        </button>
        <button type="button" className="btn btn-sm btn-ghost" onClick={logout}><SignOut />{t("Log out")}</button>
      </header>

      <main className="gx-portal-main">
        {!home ? (error ? <ErrorBox error={error} onRetry={load} /> : <Loading height={260} />) : (<>
          <div className="gx-portal-hello">
            <div className="gx-kicker">{kindLabel}</div>
            <h1 dir="auto">{home.partner_name}</h1>
            <p className="muted">{t("Welcome, {name}. This is your private space with {company}.", { name: user?.full_name ?? "", company: home.company_name })}</p>
          </div>

          <h2 className="gx-portal-h2">{t("Your services")}</h2>
          {home.features.length === 0 ? (
            <p className="muted">{t("No services are switched on for your account yet. Contact {company}.", { company: home.company_name })}</p>
          ) : (
            <div className="gx-portal-grid">
              {home.features.map((f) => {
                const Icon = ICONS[f] ?? Briefcase;
                return (
                  <div key={f} className="gx-card gx-portal-card">
                    <Icon className="gx-portal-icon" />
                    <div className="gx-portal-card-title">{t(home.catalog[f] ?? f)}</div>
                    <span className="gx-status plain">{t("Opening soon")}</span>
                  </div>
                );
              })}
            </div>
          )}

          {home.kind === "client" && home.features.includes("client.whatsapp") && (
            <section className="gx-card gx-portal-wa">
              <h2 className="gx-card-title"><WhatsappLogo />{t("Request by WhatsApp")}</h2>
              {home.whatsapp_numbers.length > 0 ? (
                <p>{t("Messages from these numbers are recognised as {name}:", { name: home.partner_name })}{" "}
                  {home.whatsapp_numbers.map((n) => <bdi key={n} dir="ltr" className="gx-portal-num">+{n}</bdi>)}</p>
              ) : <p className="muted">{t("No WhatsApp number is linked to your account yet.")}</p>}
              {home.company_whatsapp && <p>{t("Write to {company} on WhatsApp:", { company: home.company_name })} <bdi dir="ltr" className="gx-portal-num">{home.company_whatsapp}</bdi></p>}
            </section>
          )}
        </>)}
      </main>
    </div>
  );
}
