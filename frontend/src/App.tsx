import { ComponentType, lazy as reactLazy, ReactNode, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import { homePath, useAuth } from "./auth";
import { ErrorBox, Loading as LoadingState } from "./components/ui";
/** The staff pages' code, fetched in the background once someone is signed in, so moving between pages
 *  never waits for a slow (sleeping) server to send a page's script. */
const PRELOAD: (() => Promise<unknown>)[] = [];
const Layout = lazy(() => import("./components/Layout"));
const Account = lazy(() => import("./pages/Account"));
const Branding = lazy(() => import("./pages/Branding"));
const Conversations = lazy(() => import("./pages/Conversations"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Login = lazy(() => import("./pages/Login"), false);
const Packages = lazy(() => import("./pages/Packages"));
const Settings = lazy(() => import("./pages/Settings"));
const Storefront = lazy(() => import("./pages/Storefront"), false);
const Tickets = lazy(() => import("./pages/Tickets"));
const Training = lazy(() => import("./pages/Training"));
const Users = lazy(() => import("./pages/Users"));
const Companies = lazy(() => import("./pages/system/Companies"));
const CompanyDetail = lazy(() => import("./pages/system/CompanyDetail"));
const PlatformSettings = lazy(() => import("./pages/system/PlatformSettings"));
// Business tools
const SystemHealth = lazy(() => import("./pages/system/SystemHealth"));
const Customers = lazy(() => import("./pages/Customers"));
const Activity = lazy(() => import("./pages/Activity"));
// Subscription plans
const Plans = lazy(() => import("./pages/system/Plans"));
const MyPlan = lazy(() => import("./pages/MyPlan"));
const Invoice = lazy(() => import("./pages/Invoice"));
// Business accounts (clients and vendors)
const Partners = lazy(() => import("./pages/Partners"));
const PartnerPortal = lazy(() => import("./pages/PartnerPortal"));
const Requests = lazy(() => import("./pages/Requests"));

function preloadPages() {
  for (const load of PRELOAD) load().catch(() => { /* loaded again (with the reload fallback) when the page is opened */ });
}

/** After a new release the old script files are gone: a tab opened before it reloads once to get the
 *  new version instead of showing a broken page. */
function lazy<T extends ComponentType<any>>(load: () => Promise<{ default: T }>, preload = true) { // eslint-disable-line @typescript-eslint/no-explicit-any
  if (preload) PRELOAD.push(load);
  return reactLazy(() => load().then((m) => {
    try { sessionStorage.removeItem("gj_reloaded"); } catch { /* storage blocked */ }
    return m;
  }).catch((err) => {
    let reloaded = false;
    try { reloaded = sessionStorage.getItem("gj_reloaded") === "1"; sessionStorage.setItem("gj_reloaded", "1"); } catch { /* storage blocked */ }
    if (!reloaded) {
      window.location.reload();
      return new Promise<{ default: T }>(() => {});
    }
    throw err;
  }));
}

/** Full-screen wait for the session check (a sleeping server can take up to a minute). */
function SessionWait() {
  const { loading, loadError, retry } = useAuth();
  return (
    <div className="loading-screen">
      <div style={{ width: "min(460px, 100%)" }}>
        {loading || !loadError ? <LoadingState height={0} /> : <ErrorBox error={loadError} onRetry={retry} />}
      </div>
    </div>
  );
}

function RequireUser({ system, permission, partner, children }: {
  system?: boolean; permission?: string;
  /** The business portal (logins of clients and vendors), which never see the staff app. */
  partner?: boolean;
  children: ReactNode;
}) {
  const { user, loading, can, sessionEnded, loadError } = useAuth();
  const location = useLocation();
  if (loading || (!user && loadError)) return <SessionWait />;
  // After signing in again the person comes back to the page they were on.
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search, expired: sessionEnded }} />;
  const isSystem = user.role === "system_admin";
  const isPartner = user.role === "partner";
  if (!!partner !== isPartner) return <Navigate to={homePath(user)} replace />;
  if (system !== undefined && system !== isSystem) return <Navigate to={homePath(user)} replace />;
  if (permission && !can(permission)) return <Navigate to={homePath(user)} replace />;
  return <>{children}</>;
}

function Home() {
  const { user, loading, loadError } = useAuth();
  if (loading || (!user && loadError)) return <SessionWait />;
  return <Navigate to={user ? homePath(user) : "/login"} replace />;
}

/** Each area loads its own code, so a traveller opening /c/<slug> does not download the staff app. */
function Loading() {
  return <div className="loading-screen"><div style={{ width: "min(460px, 100%)" }}><LoadingState height={0} /></div></div>;
}

export default function App() {
  const location = useLocation();
  const { user } = useAuth();
  const signedIn = !!user;
  useEffect(() => {
    if (!signedIn) return;
    const id = window.setTimeout(preloadPages, 1200);
    return () => window.clearTimeout(id);
  }, [signedIn]);
  return (
    <ErrorBoundary resetKey={location.pathname}>
    <Suspense fallback={<Loading />}>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/c/:slug" element={<Storefront />} />
      <Route path="/system/invoices/:id" element={<RequireUser system><Invoice owner /></RequireUser>} />
      <Route path="/app/plan/invoices/:id" element={<RequireUser system={false}><Invoice /></RequireUser>} />

      <Route path="/partner" element={<RequireUser partner><PartnerPortal /></RequireUser>} />

      <Route path="/system" element={<RequireUser system><Layout /></RequireUser>}>
        <Route index element={<Companies />} />
        <Route path="companies/:id" element={<CompanyDetail />} />
        <Route path="account" element={<Account />} />
        <Route path="settings" element={<PlatformSettings />} />
        <Route path="health" element={<SystemHealth />} />
        <Route path="plans" element={<Plans />} />
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
        <Route path="customers" element={<RequireUser permission="conversations.view"><Customers /></RequireUser>} />
        <Route path="customers/:id" element={<RequireUser permission="conversations.view"><Customers /></RequireUser>} />
        <Route path="partners" element={<RequireUser permission="partners.manage"><Partners /></RequireUser>} />
        <Route path="requests" element={<RequireUser permission="requests.manage"><Requests /></RequireUser>} />
        <Route path="requests/:id" element={<RequireUser permission="requests.manage"><Requests /></RequireUser>} />
        <Route path="activity" element={<Activity />} />
        <Route path="plan" element={<MyPlan />} />
        <Route path="account" element={<Account />} />
      </Route>

      <Route path="*" element={<Home />} />
    </Routes>
    </Suspense>
    </ErrorBoundary>
  );
}
