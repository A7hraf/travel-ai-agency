import { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { homePath, useAuth } from "./auth";
import Layout from "./components/Layout";
import Account from "./pages/Account";
import Conversations from "./pages/Conversations";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Packages from "./pages/Packages";
import Settings from "./pages/Settings";
import Storefront from "./pages/Storefront";
import Tickets from "./pages/Tickets";
import Users from "./pages/Users";
import Companies from "./pages/system/Companies";
import CompanyDetail from "./pages/system/CompanyDetail";

function RequireUser({ system, permission, children }: { system?: boolean; permission?: string; children: ReactNode }) {
  const { user, loading, can } = useAuth();
  if (loading) return <div className="loading-screen">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  const isSystem = user.role === "system_admin";
  if (system !== undefined && system !== isSystem) return <Navigate to={homePath(user)} replace />;
  if (permission && !can(permission)) return <Navigate to={homePath(user)} replace />;
  return <>{children}</>;
}

function Home() {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-screen">Loading…</div>;
  return <Navigate to={user ? homePath(user) : "/login"} replace />;
}

export default function App() {
  return (
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
        <Route path="account" element={<Account />} />
      </Route>

      <Route path="*" element={<Home />} />
    </Routes>
  );
}
