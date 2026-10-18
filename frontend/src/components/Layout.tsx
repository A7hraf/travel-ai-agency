import { CSSProperties, ComponentType, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";
import { LangSwitch, trServer, useI18n } from "../lang";
import { dashboardVars, GHANJAH, isDark } from "../theme";
import type { ConversationSummary, Ticket as TicketT } from "../types";
import { customerLabel, ROLE_LABELS, usePolling } from "../util";
import { GhanjahMark, usePlatformName } from "./Brand";
import {
  ArrowSquareOut, Buildings, ChartLineUp, ChatsCircle, GraduationCap, IconProps, List, PaintBrush, SignOut,
  SquaresFour, SuitcaseRolling, Ticket, Translate, UserCircle, UsersThree, WhatsappLogo,
} from "./Icon";
import { moneyText } from "./Money";
import { Sheet } from "./staff/Sheet";
import { StaffContext, StaffToast } from "./staff/StaffContext";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<IconProps>;
  permission?: string;
  badge?: "needs" | "open";
}

const COMPANY_NAV: NavItem[] = [
  { to: "/app/dashboard", label: "Dashboard", icon: SquaresFour, permission: "reports.view" },
  { to: "/app/conversations", label: "Conversations", icon: ChatsCircle, permission: "conversations.view", badge: "needs" },
  { to: "/app/tickets", label: "Tickets", icon: Ticket, permission: "tickets.view", badge: "open" },
  { to: "/app/packages", label: "Packages", icon: SuitcaseRolling, permission: "packages.view" },
  { to: "/app/users", label: "Team & accounts", icon: UsersThree, permission: "users.manage" },
  { to: "/app/branding", label: "Customer page design", icon: PaintBrush, permission: "settings.manage" },
  { to: "/app/training", label: "AI training", icon: GraduationCap, permission: "settings.manage" },
  { to: "/app/settings", label: "AI & WhatsApp", icon: WhatsappLogo, permission: "settings.manage" },
  { to: "/app/account", label: "My account", icon: UserCircle },
];

const SYSTEM_NAV: NavItem[] = [
  { to: "/system", label: "Companies", icon: Buildings },
  { to: "/system/account", label: "My account", icon: UserCircle },
];

/** The phone tab bar: the three screens of the design (Menu holds the rest). */
const TAB_PATHS = ["/app/conversations", "/app/tickets", "/app/dashboard"];
const TAB_ICONS: Record<string, ComponentType<IconProps>> = { "/app/dashboard": ChartLineUp };

const OPEN_STATUSES = ["pending_payment", "in_progress"];
const POLL_MS = 20000;
const TOAST_MS = 4200;

export default function Layout() {
  const { user, logout, can } = useAuth();
  const { t, lang, setLang } = useI18n();
  const platformName = usePlatformName();
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [location.pathname]);
  useEffect(() => {
    const company = user?.company?.name;
    document.title = company ? `${company} · Ghanjah` : "Ghanjah · AI Travel from Oman";
  }, [user?.company?.name]);

  // --- Badge counts and "new" toasts -----------------------------------------------------
  const isSystem = user?.role === "system_admin";
  const canConvs = !isSystem && can("conversations.view");
  const canTickets = !isSystem && can("tickets.view");
  const [needsHuman, setNeedsHuman] = useState(0);
  const [openTickets, setOpenTickets] = useState(0);
  const [agentName, setAgentName] = useState("");
  const [toasts, setToasts] = useState<StaffToast[]>([]);
  const seenChats = useRef<Set<number> | null>(null);
  const lastTicketId = useRef<number | null>(null);
  const toastSeq = useRef(0);

  const toast = useCallback((item: StaffToast) => {
    const id = ++toastSeq.current;
    setToasts((list) => [...list.slice(-2), { ...item, id }]);
    window.setTimeout(() => setToasts((list) => list.filter((x) => x.id !== id)), TOAST_MS);
  }, []);

  const pollRef = useRef<() => void>(() => {});
  pollRef.current = () => {
    if (canConvs) {
      get<ConversationSummary[]>("/api/conversations?status=human&limit=200").then((rows) => {
        const waiting = rows.filter((c) => !c.assigned_to);
        setNeedsHuman(waiting.length);
        const before = seenChats.current;
        if (before) {
          for (const c of waiting.filter((x) => !before.has(x.id)).slice(0, 2)) {
            toast({
              tone: "amber",
              icon: <ChatsCircle weight="duotone" />,
              title: t("{name} needs a human", { name: customerLabel(c.customer) }),
              text: trServer(c.last_message_preview) || undefined,
              onOpen: () => navigate(`/app/conversations/${c.id}`),
            });
          }
        }
        seenChats.current = new Set(waiting.map((c) => c.id));
      }).catch(() => {});
    }
    if (canTickets) {
      Promise.all(OPEN_STATUSES.map((s) => get<TicketT[]>(`/api/tickets?status=${s}&limit=1000`)))
        .then(([a, b]) => {
          const open = [...a, ...b];
          setOpenTickets(open.length);
          const maxId = open.reduce((m, x) => Math.max(m, x.id), 0);
          const before = lastTicketId.current;
          if (before !== null) {
            for (const tk of open.filter((x) => x.id > before).slice(0, 2)) {
              toast({
                tone: "cyan",
                icon: <Ticket weight="duotone" />,
                title: t("New booking {reference}", { reference: tk.reference }),
                text: `${tk.package_title} · ${moneyText(tk.total_price, tk.currency, lang)}`,
                onOpen: () => navigate(`/app/tickets?open=${tk.id}`),
              });
            }
          }
          lastTicketId.current = Math.max(before ?? 0, maxId);
        })
        .catch(() => {});
    }
  };
  usePolling(() => pollRef.current(), POLL_MS, [canConvs, canTickets]);
  const refreshCounts = useCallback(() => pollRef.current(), []);

  useEffect(() => {
    if (!user?.company) return;
    get<{ ai_agent_name: string }>("/api/company").then((c) => setAgentName(c.ai_agent_name || "")).catch(() => {});
  }, [user?.company]);

  const staff = useMemo(
    () => ({ needsHuman, openTickets, agentName, toast, refreshCounts }),
    [needsHuman, openTickets, agentName, toast, refreshCounts],
  );

  if (!user) return null;
  const nav = isSystem ? SYSTEM_NAV : COMPANY_NAV.filter((n) => !n.permission || can(n.permission));
  const tabs = isSystem ? [] : TAB_PATHS.map((p) => nav.find((n) => n.to === p)).filter((n): n is NavItem => !!n);
  const menuItems = nav.filter((n) => !tabs.includes(n));
  const branding = user.company?.branding;
  const style = dashboardVars(branding?.dashboard_color, branding?.dashboard_sidebar) as CSSProperties;
  const brandName = user.company?.name ?? platformName;
  const darkSidebar = isDark(branding?.dashboard_sidebar ?? GHANJAH.ink);
  const logo = (cls: string) => branding?.logo
    ? <img className={`brand-logo ${cls}`} src={branding.logo} alt="" />
    : <GhanjahMark dark={darkSidebar} className={`brand-ghanjah ${cls}`} />;
  const sub = isSystem ? t("Platform console") : t("Agency workspace");
  const initial = (user.full_name.trim()[0] ?? "?").toUpperCase();
  const role = t(ROLE_LABELS[user.role]);
  const count = (n: NavItem) => (n.badge === "needs" ? needsHuman : n.badge === "open" ? openTickets : 0);
  const badgeLabel = (n: NavItem) =>
    n.badge === "needs" ? t("{n} need a human", { n: needsHuman }) : t("{n} open", { n: openTickets });

  return (
    <StaffContext.Provider value={staff}>
      <div className={`app-shell ${tabs.length ? "has-tabs" : ""}`} style={style}>
        <div className="gj-orbs" aria-hidden="true" />

        {/* Phones: compact header */}
        <header className="app-top">
          {logo("top-logo")}
          <div className="app-top-name">
            <div className="app-top-agency">{brandName}</div>
            <div className="app-top-sub">{sub}</div>
          </div>
          <button type="button" className="app-avatar" aria-label={t("Open menu")} aria-haspopup="dialog"
            aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>
            <span aria-hidden="true">{initial}</span>
          </button>
        </header>

        {/* Desktop: sidebar */}
        <aside className="app-side" aria-label={t("Main menu")}>
          <div className="side-brand">
            {logo("side-logo")}
            <div className="side-brand-text">
              <div className="side-agency">{brandName}</div>
              <div className="side-sub">{sub}</div>
            </div>
          </div>
          <nav className="side-nav">
            {nav.map((n) => {
              const c = count(n);
              return (
                <NavLink key={n.to} to={n.to} end={n.to === "/system"} className="side-link">
                  <n.icon size={19} weight="duotone" aria-hidden="true" />
                  <span className="side-link-label">{t(n.label)}</span>
                  {c > 0 && (
                    <span className={`side-count ${n.badge === "needs" ? "amber" : "cyan"}`} aria-label={badgeLabel(n)}>{c}</span>
                  )}
                </NavLink>
              );
            })}
            {user.company && (
              <a className="side-link" href={`/c/${user.company.slug}`} target="_blank" rel="noreferrer">
                <ArrowSquareOut size={19} weight="duotone" aria-hidden="true" />
                <span className="side-link-label">{t("Customer page")}</span>
              </a>
            )}
          </nav>
          <div className="side-foot">
            <div className="side-user">
              <span className="side-avatar" aria-hidden="true">{initial}</span>
              <div className="side-user-text">
                <div className="side-user-name">{user.full_name}</div>
                <div className="side-user-role">{role}</div>
              </div>
            </div>
            <div className="side-actions">
              <LangSwitch className="side-act" />
              <button type="button" className="side-act" onClick={logout}>
                <SignOut size={16} className="flip" aria-hidden="true" />{t("Log out")}
              </button>
            </div>
          </div>
        </aside>

        <main className="content" id="main">
          <Outlet />
        </main>

        {/* Phones: bottom tab bar */}
        {tabs.length > 0 && (
          <nav className="app-tabs" aria-label={t("Main menu")}>
            {tabs.map((n) => {
              const c = count(n);
              const Icon = TAB_ICONS[n.to] ?? n.icon;
              return (
                <NavLink key={n.to} to={n.to} className="app-tab">
                  <span className="app-tab-icon">
                    <Icon size={24} weight="duotone" aria-hidden="true" />
                    {c > 0 && <span className={`app-tab-count ${n.badge === "needs" ? "amber" : "cyan"}`} aria-label={badgeLabel(n)}>{c}</span>}
                  </span>
                  {t(n.label)}
                </NavLink>
              );
            })}
            <button type="button" className={`app-tab ${menuOpen ? "active" : ""}`} aria-haspopup="dialog" aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}>
              <span className="app-tab-icon"><List size={24} weight="duotone" aria-hidden="true" /></span>
              {t("Menu")}
            </button>
          </nav>
        )}

        {menuOpen && (
          <Sheet label={t("Menu")} onClose={() => setMenuOpen(false)} className="menu-sheet">
            <div className="menu-user">
              <span className="side-avatar big" aria-hidden="true">{initial}</span>
              <div className="side-user-text">
                <div className="menu-user-name">{user.full_name}</div>
                <div className="side-user-role">{role} · {brandName}</div>
              </div>
            </div>
            <nav className="menu-list" aria-label={t("Menu")}>
              {menuItems.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === "/system"} className="menu-link" onClick={() => setMenuOpen(false)}>
                  <n.icon size={22} weight="duotone" aria-hidden="true" />
                  <span>{t(n.label)}</span>
                </NavLink>
              ))}
              {user.company && (
                <a className="menu-link" href={`/c/${user.company.slug}`} target="_blank" rel="noreferrer">
                  <ArrowSquareOut size={22} weight="duotone" aria-hidden="true" />
                  <span>{t("Customer page")} ↗</span>
                </a>
              )}
            </nav>
            <div className="menu-foot">
              <button type="button" className="btn menu-foot-btn" lang={lang === "ar" ? "en" : "ar"}
                onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
                <Translate size={18} aria-hidden="true" />{lang === "ar" ? "English" : "العربية"}
              </button>
              <button type="button" className="btn btn-danger menu-foot-btn" onClick={logout}>
                <SignOut size={18} className="flip" aria-hidden="true" />{t("Log out")}
              </button>
            </div>
          </Sheet>
        )}

        {toasts.length > 0 && (
          <div className="toast-stack app-toasts" role="status" aria-live="polite">
            {toasts.map((x) => (
              <button key={x.id} type="button" className="toast"
                onClick={() => { setToasts((l) => l.filter((y) => y.id !== x.id)); x.onOpen?.(); }}>
                <span className={`toast-icon ${x.tone}`} aria-hidden="true">{x.icon}</span>
                <span className="toast-text">
                  <strong>{x.title}</strong>
                  {x.text && <span dir="auto">{x.text}</span>}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </StaffContext.Provider>
  );
}
