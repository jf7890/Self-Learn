import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "../api";
import { useBranding } from "../BrandingContext.jsx";
import { BrandMark } from "../icons.jsx";

// Handles both invite ("welcome, set your password") and password reset
// ("choose a new password") — same mechanism server-side, just different
// copy depending on the token's kind.
export default function SetPassword() {
  const { token } = useParams();
  const navigate = useNavigate();
  const { site_name, logo_url } = useBranding();

  const [checking, setChecking] = useState(true);
  const [tokenInfo, setTokenInfo] = useState(null);
  const [tokenError, setTokenError] = useState(null);

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.checkAuthToken(token)
      .then(setTokenInfo)
      .catch((e) => setTokenError(e.message))
      .finally(() => setChecking(false));
  }, [token]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords don't match");
      return;
    }
    setLoading(true);
    try {
      const data = await api.setPasswordViaToken(token, password);
      localStorage.setItem("ct_token", "cookie-session");
      localStorage.setItem("ct_user", JSON.stringify(data.user));
      navigate("/");
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const heading = tokenInfo?.kind === "invite" ? `Welcome to ${site_name}` : "Choose a new password";

  return (
    <div className="ct-auth-screen">
      <div className="ct-auth-card card">
        {logo_url ? (
          <img src={`/api${logo_url}`} alt="" className="ct-auth-logo" />
        ) : (
          <span className="ct-auth-mark"><BrandMark size={26} /></span>
        )}

        {checking ? (
          <div className="state-screen" style={{ minHeight: 80 }}><span className="spinner" /></div>
        ) : tokenError ? (
          <>
            <h1 className="display ct-auth-title">Link expired</h1>
            <p className="alert alert-danger">{tokenError}</p>
            <Link to="/forgot-password" className="btn btn-secondary ct-auth-submit" style={{ textAlign: "center" }}>
              Request a new link
            </Link>
          </>
        ) : (
          <>
            <h1 className="display ct-auth-title">{heading}</h1>
            <p className="ct-auth-sub">
              {tokenInfo?.kind === "invite"
                ? `Set a password for ${tokenInfo.username} to get started.`
                : `Choose a new password for ${tokenInfo?.username}.`}
            </p>

            {error && <p className="alert alert-danger">{error}</p>}

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <div className="field">
                <label>New password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} autoFocus required />
              </div>
              <div className="field">
                <label>Confirm password</label>
                <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} minLength={8} required />
              </div>
              <button type="submit" className="btn btn-primary ct-auth-submit" disabled={loading}>
                {loading ? <span className="spinner" /> : "Set password and sign in"}
              </button>
            </form>
          </>
        )}
      </div>

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
        .ct-auth-title { font-size: var(--text-xl); }
        .ct-auth-sub { color: var(--text-muted); font-size: var(--text-sm); margin: -8px 0 4px; line-height: 1.5; }
        .ct-auth-submit { padding: 11px; font-size: var(--text-md); text-decoration: none; }
      `}</style>
    </div>
  );
}
