import { lazy, ReactNode, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { homePath, useAuth } from "./auth";
import { useI18n } from "./lang";
const Layout = lazy(() => import("./components/Layout"));
const Account = lazy(() => import("./pages/Account"));
const Branding = lazy(() => import("./pages/Branding"));
const Conversations = lazy(() => import("./pages/Conversations"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Login = lazy(() => import("./pages/Login"));
const Packages = lazy(() => import("./pages/Packages"));
const Settings = lazy(() => import("./pages/Settings"));
const Storefront = lazy(() => import("./pages/Storefront"));
const Tickets = lazy(() => import("./pages/Tickets"));
const Training = lazy(() => import("./pages/Training"));
const Users = lazy(() => import("./pages/Users"));
const Companies = lazy(() => import("./pages/system/Companies"));
const CompanyDetail = lazy(() => import("./pages/system/CompanyDetail"));

function RequireUser({ system, permission, children }: { system?: boolean; permission?: string; children: ReactNode }) {
  const { user, loading, can, sessionEnded } = useAuth();
  const { t } = useI18n();
  const location = useLocation();
  if (loading) return <div className="loading-screen">{t("Loading…")}</div>;
  // After signing in again the person comes back to the page they were on.
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search, expired: sessionEnded }} />;
  const isSystem = user.role === "system_admin";
  if (system !== undefined && system !== isSystem) return <Navigate to={homePath(user)} replace />;
  if (permission && !can(permission)) return <Navigate to={homePath(user)} replace />;
  return <>{children}</>;
}

function Home() {
  const { user, loading } = useAuth();
  const { t } = useI18n();
  if (loading) return <div className="loading-screen">{t("Loading…")}</div>;
  return <Navigate to={user ? homePath(user) : "/login"} replace />;
}

/** Each area loads its own code, so a traveller opening /c/<slug> does not download the staff app. */
function Loading() {
  const { t } = useI18n();
  return <div className="loading-screen">{t("Loading…")}</div>;
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/c/:slug" element={<Storefront />} />

      <Route path="/system" element={<RequireUser system><Layout /></RequireUser>}>
        <Route index element={<Companies />} />
        <Route path="companies/:id" element={<CompanyDetail />} />
        <Route path="account" element={<Account />} />
      </Route>

      <Route path="/app" element={<RequireUser system={false}><Layout /></RequireUser>}>
        <Route index element={<Home />} />
        <Route path="dashboard" element={<RequireUser permission="reports.view"><Dashboard /></RequireUser>} />
        <Route path="conversations" element={<RequireUser permission="conversations.view"><Conversations /></RequireUser>} />
        <Route path="conversations/:id" element={<RequireUser permission="conversations.view"><Conversations /></RequireUser>} />
        <Route path="tickets" element={<RequireUser permission="tickets.view"><Tickets /></RequireUser>} />
        <Route path="packages" element={<RequireUser permission="packages.view"><Packages /></RequireUser>} />
        <Route path="users" element={<RequireUser permission="users.manage"><Users /></RequireUser>} />
        <Route path="settings" element={<RequireUser permission="settings.manage"><Settings /></RequireUser>} />
        <Route path="branding" element={<RequireUser permission="settings.manage"><Branding /></RequireUser>} />
        <Route path="training" element={<RequireUser permission="settings.manage"><Training /></RequireUser>} />
        <Route path="account" element={<Account />} />
      </Route>

      <Route path="*" element={<Home />} />
    </Routes>
    </Suspense>
  );
}
