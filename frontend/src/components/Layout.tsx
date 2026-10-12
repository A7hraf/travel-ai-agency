import { CSSProperties } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
import { LangSwitch, useI18n } from "../lang";
import { dashboardVars } from "../theme";
import { ROLE_LABELS } from "../util";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  permission?: string;
}

const COMPANY_NAV: NavItem[] = [
  { to: "/app/dashboard", label: "Dashboard", icon: "◧", permission: "reports.view" },
  { to: "/app/conversations", label: "Conversations", icon: "💬", permission: "conversations.view" },
  { to: "/app/tickets", label: "Tickets", icon: "🎫", permission: "tickets.view" },
  { to: "/app/packages", label: "Packages", icon: "🧳", permission: "packages.view" },
  { to: "/app/users", label: "Team & accounts", icon: "👥", permission: "users.manage" },
  { to: "/app/branding", label: "Customer page design", icon: "🎨", permission: "settings.manage" },
  { to: "/app/training", label: "AI training", icon: "🎓", permission: "settings.manage" },
  { to: "/app/settings", label: "AI & WhatsApp", icon: "⚙", permission: "settings.manage" },
  { to: "/app/account", label: "My account", icon: "🔑" },
];

const SYSTEM_NAV: NavItem[] = [
  { to: "/system", label: "Companies", icon: "🏢" },
  { to: "/system/account", label: "My account", icon: "🔑" },
];

export default function Layout() {
  const { user, logout, can } = useAuth();
  const { t } = useI18n();
  if (!user) return null;
  const nav = user.role === "system_admin" ? SYSTEM_NAV : COMPANY_NAV.filter((n) => !n.permission || can(n.permission));
  const branding = user.company?.branding;
  const style = dashboardVars(branding?.dashboard_color, branding?.dashboard_sidebar) as CSSProperties;

  return (
    <div className="shell" style={style}>
      <aside className="sidebar">
        <div className="brand">
          {branding?.logo ? <img className="brand-logo" src={branding.logo} alt="" /> : <span className="brand-mark">✈</span>}
          <div>
            <div className="brand-name">{user.company?.name ?? t("Travel AI Platform")}</div>
            <div className="brand-sub">{user.role === "system_admin" ? t("Platform console") : t("Agency workspace")}</div>
          </div>
        </div>
        <nav>
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/system"} className="nav-link">
              <span className="nav-icon">{n.icon}</span>
              {t(n.label)}
            </NavLink>
          ))}
          {user.company && (
            <a className="nav-link" href={`/c/${user.company.slug}`} target="_blank" rel="noreferrer">
              <span className="nav-icon">↗</span>
              {t("Customer page")}
            </a>
          )}
        </nav>
        <div className="sidebar-lang"><LangSwitch /></div>
        <div className="sidebar-foot">
          <div className="who">
            <div className="who-name">{user.full_name}</div>
            <div className="who-role">{t(ROLE_LABELS[user.role])}</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={logout}>{t("Log out")}</button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
