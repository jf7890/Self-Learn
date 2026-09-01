import { Routes, Route, Navigate, Link, useNavigate, useLocation } from "react-router-dom";
import Login from "./components/Login.jsx";
import Setup from "./components/Setup.jsx";
import ForgotPassword from "./components/ForgotPassword.jsx";
import SetPassword from "./components/SetPassword.jsx";
import CourseGrid from "./components/CourseGrid.jsx";
import CourseView from "./components/CourseView.jsx";
import AdminDashboard from "./components/AdminDashboard.jsx";
import Profile from "./components/Profile.jsx";
import { getToken } from "./api";
import { useBranding } from "./BrandingContext.jsx";
import { BrandMark, IconShield, IconLogOut, IconUsers } from "./icons.jsx";

function RequireAuth({ children }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
}

function RequireAdmin({ children }) {
  const user = JSON.parse(localStorage.getItem("ct_user") || "null");
  if (!getToken()) return <Navigate to="/login" replace />;
  if (!user?.is_admin) return <Navigate to="/" replace />;
  return children;
}

function TopNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = JSON.parse(localStorage.getItem("ct_user") || "null");
  const { logo_url } = useBranding();

  const logout = () => {
    localStorage.removeItem("ct_token");
    localStorage.removeItem("ct_user");
    navigate("/login");
  };

  return (
    <header className="ct-topnav">
      <Link to="/" className="ct-brand">
        {logo_url ? (
          <img src={`/api${logo_url}`} alt="" className="ct-brand-logo" />
        ) : (
          <img src="/brand-logo-192.png" alt="Home" className="ct-brand-logo ct-default-brand-logo" />
        )}
      </Link>
      <div className="ct-spacer" />
      <Link to="/profile" className={`btn btn-secondary btn-sm ${location.pathname === "/profile" ? "ct-nav-active" : ""}`}>
        <IconUsers width={14} height={14} /> My progress
      </Link>
      {user?.is_admin && (
        <Link to="/admin" className={`btn btn-secondary btn-sm ${location.pathname === "/admin" ? "ct-nav-active" : ""}`}>
          <IconShield width={14} height={14} /> Admin
        </Link>
      )}
      <span className="ct-nav-user">{user?.username}</span>
      <button className="btn btn-ghost btn-sm" onClick={logout}>
        <IconLogOut width={14} height={14} /> Sign out
      </button>

      <style>{`
        .ct-topnav {
          display: flex;
          align-items: center;
          gap: var(--space-3);
          padding: 0 var(--space-5);
          border-bottom: 1px solid var(--border);
          height: 56px;
          flex-shrink: 0;
          background: var(--bg);
        }
        .ct-brand {
          display: flex;
          align-items: center;
          gap: var(--space-2);
          font-family: var(--font-display);
          font-weight: 600;
          font-size: var(--text-md);
          text-decoration: none;
          color: var(--text);
        }
        .ct-brand-mark { color: var(--accent); display: inline-flex; }
        .ct-brand-logo { height: 32px; width: auto; max-width: 140px; object-fit: contain; }
        .ct-default-brand-logo { width: 32px; border-radius: 7px; object-fit: cover; }
        .ct-spacer { flex: 1; }
        .ct-nav-user { font-size: var(--text-sm); color: var(--text-muted); }
        .ct-nav-active { border-color: var(--accent-dim); color: var(--accent); }
        @media (max-width: 640px) {
          .ct-nav-user { display: none; }
        }
      `}</style>
    </header>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/setup" element={<Setup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/set-password/:token" element={<SetPassword />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <div className="ct-app-shell">
              <TopNav />
              <div className="ct-app-body"><CourseGrid /></div>
            </div>
          </RequireAuth>
        }
      />
      <Route
        path="/course/:courseId"
        element={
          <RequireAuth>
            <CourseView />
          </RequireAuth>
        }
      />
      <Route
        path="/profile"
        element={
          <RequireAuth>
            <div className="ct-app-shell">
              <TopNav />
              <div className="ct-app-body"><Profile /></div>
            </div>
          </RequireAuth>
        }
      />
      <Route
        path="/admin"
        element={
          <RequireAdmin>
            <div className="ct-app-shell">
              <TopNav />
              <div className="ct-app-body"><AdminDashboard /></div>
            </div>
          </RequireAdmin>
        }
      />
    </Routes>
  );
}
