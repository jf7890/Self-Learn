import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api";
import { useBranding } from "../BrandingContext.jsx";
import { BrandMark } from "../icons.jsx";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [jellyfinEnabled, setJellyfinEnabled] = useState(false);
  const [jellyfinMode, setJellyfinMode] = useState(false);
  const [checkingConfig, setCheckingConfig] = useState(true);
  const navigate = useNavigate();
  const { site_name, logo_url } = useBranding();

  useEffect(() => {
    api.authConfig().then((cfg) => {
      if (cfg.needs_setup) {
        navigate("/setup");
        return;
      }
      setJellyfinEnabled(cfg.jellyfin_enabled);
      setCheckingConfig(false);
    }).catch(() => setCheckingConfig(false));
  }, [navigate]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = jellyfinMode
        ? await api.jellyfinLogin(username, password)
        : await api.login(username, password);
      localStorage.setItem("ct_token", "cookie-session");
      localStorage.setItem("ct_user", JSON.stringify(data.user));
      navigate("/");
    } catch (err) {
      setError(err.message || "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  if (checkingConfig) {
    return <div className="state-screen"><span className="spinner" /></div>;
  }

  return (
    <div className="ct-auth-screen">
      <form className="ct-auth-card card" onSubmit={handleSubmit}>
        {logo_url ? (
          <img src={`/api${logo_url}`} alt="" className="ct-auth-logo" />
        ) : (
          <span className="ct-auth-mark"><BrandMark size={26} /></span>
        )}
        <h1 className="display ct-auth-title">{site_name}</h1>
        <p className="ct-auth-sub">
          {jellyfinMode ? "Sign in with your Jellyfin account" : "Sign in to your account"}
        </p>

        {error && <p className="alert alert-danger">{error}</p>}

        <div className="field">
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>

        <button type="submit" className="btn btn-primary ct-auth-submit" disabled={loading}>
          {loading ? <span className="spinner" /> : "Sign in"}
        </button>

        {!jellyfinMode && (
          <Link to="/forgot-password" className="ct-forgot-link">Forgot password?</Link>
        )}

        {jellyfinEnabled && (
          <>
            <div className="divider-label">or</div>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => { setJellyfinMode((m) => !m); setError(null); }}
            >
              {jellyfinMode ? `Use ${site_name} account instead` : "Sign in with Jellyfin"}
            </button>
          </>
        )}
      </form>

      <style>{`
        .ct-auth-screen {
          min-height: 100dvh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: var(--space-6);
          background:
            radial-gradient(circle at 18% -8%, var(--accent-soft), transparent 42%),
            var(--bg);
        }
        .ct-auth-card {
          width: 100%;
          max-width: 368px;
          padding: 36px 30px 30px;
          display: flex;
          flex-direction: column;
          gap: var(--space-4);
          box-shadow: var(--shadow-lg);
        }
        .ct-auth-mark { color: var(--accent); margin-bottom: var(--space-1); }
        .ct-auth-logo { height: 40px; width: auto; max-width: 180px; object-fit: contain; margin-bottom: var(--space-1); }
        .ct-auth-title { font-size: var(--text-2xl); }
        .ct-auth-sub { color: var(--text-muted); font-size: var(--text-sm); margin: -8px 0 4px; }
        .ct-auth-submit { margin-top: var(--space-1); padding: 11px; font-size: var(--text-md); }
        .ct-forgot-link { text-align: center; font-size: var(--text-sm); color: var(--text-muted); text-decoration: none; margin-top: -6px; }
        .ct-forgot-link:hover { color: var(--text); }
      `}</style>
    </div>
  );
}
