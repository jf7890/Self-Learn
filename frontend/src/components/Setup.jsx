import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useBranding } from "../BrandingContext.jsx";
import { BrandMark } from "../icons.jsx";

export default function Setup() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [checked, setChecked] = useState(false);
  const navigate = useNavigate();
  const { site_name, logo_url } = useBranding();

  useEffect(() => {
    api.authConfig().then((cfg) => {
      if (!cfg.needs_setup) {
        navigate("/login");
        return;
      }
      setChecked(true);
    }).catch(() => setChecked(true));
  }, [navigate]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords don't match");
      return;
    }
    setLoading(true);
    try {
      const data = await api.setup(username, password);
      localStorage.setItem("ct_token", "cookie-session");
      localStorage.setItem("ct_user", JSON.stringify(data.user));
      navigate("/");
    } catch (err) {
      setError(err.message || "Setup failed");
    } finally {
      setLoading(false);
    }
  }

  if (!checked) return <div className="state-screen"><span className="spinner" /></div>;

  return (
    <div className="ct-auth-screen">
      <form className="ct-auth-card card" onSubmit={handleSubmit}>
        {logo_url ? (
          <img src={`/api${logo_url}`} alt="" className="ct-auth-logo" />
        ) : (
          <span className="ct-auth-mark"><BrandMark size={26} /></span>
        )}
        <h1 className="display ct-auth-title">Welcome to {site_name}</h1>
        <p className="ct-auth-sub">
          Create the first admin account to get started. You can add members and turn on Jellyfin
          sign-in afterwards, from the dashboard.
        </p>

        {error && <p className="alert alert-danger">{error}</p>}

        <div className="field">
          <label>Admin username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} required />
        </div>
        <div className="field">
          <label>Confirm password</label>
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} minLength={8} required />
        </div>

        <button type="submit" className="btn btn-primary ct-auth-submit" disabled={loading}>
          {loading ? <span className="spinner" /> : "Create admin account"}
        </button>
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
          max-width: 400px;
          padding: 36px 30px 30px;
          display: flex;
          flex-direction: column;
          gap: var(--space-4);
          box-shadow: var(--shadow-lg);
        }
        .ct-auth-mark { color: var(--accent); margin-bottom: var(--space-1); }
        .ct-auth-logo { height: 40px; width: auto; max-width: 180px; object-fit: contain; margin-bottom: var(--space-1); }
        .ct-auth-title { font-size: var(--text-xl); }
        .ct-auth-sub { color: var(--text-muted); font-size: var(--text-sm); line-height: 1.55; margin: -6px 0 4px; }
        .ct-auth-submit { margin-top: var(--space-1); padding: 11px; font-size: var(--text-md); }
      `}</style>
    </div>
  );
}
