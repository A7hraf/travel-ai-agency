import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
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
  { to: "/app/settings", label: "AI & WhatsApp", icon: "⚙", permission: "settings.manage" },
  { to: "/app/account", label: "My account", icon: "🔑" },
];

const SYSTEM_NAV: NavItem[] = [
  { to: "/system", label: "Companies", icon: "🏢" },
  { to: "/system/account", label: "My account", icon: "🔑" },
];

export default function Layout() {
  const { user, logout, can } = useAuth();
  if (!user) return null;
  const nav = user.role === "system_admin" ? SYSTEM_NAV : COMPANY_NAV.filter((n) => !n.permission || can(n.permission));

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">✈</span>
          <div>
            <div className="brand-name">{user.company?.name ?? "Travel AI Platform"}</div>
            <div className="brand-sub">{user.role === "system_admin" ? "Platform console" : "Agency workspace"}</div>
          </div>
        </div>
        <nav>
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/system"} className="nav-link">
              <span className="nav-icon">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
          {user.company && (
            <a className="nav-link" href={`/c/${user.company.slug}`} target="_blank" rel="noreferrer">
              <span className="nav-icon">↗</span>
              Customer page
            </a>
          )}
        </nav>
        <div className="sidebar-foot">
          <div className="who">
            <div className="who-name">{user.full_name}</div>
            <div className="who-role">{ROLE_LABELS[user.role]}</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={logout}>Log out</button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
