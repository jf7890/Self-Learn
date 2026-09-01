import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { IconTrophy, IconCheckCircle, IconLibrary, IconChevronLeft } from "../icons.jsx";

function formatWatchTime(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.round((totalSeconds % 3600) / 60);
  if (hours === 0) return `${minutes}m`;
  return `${hours}h ${minutes}m`;
}

export default function Profile() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const user = JSON.parse(localStorage.getItem("ct_user") || "null");

  useEffect(() => {
    api.getMyStats().then(setStats).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="alert alert-danger" style={{ margin: 20 }}>{error}</p>;
  if (!stats) return <div className="state-screen"><span className="spinner" /></div>;

  const memberSince = stats.member_since
    ? new Date(stats.member_since.replace(" ", "T") + "Z").toLocaleDateString(undefined, { year: "numeric", month: "long" })
    : null;

  return (
    <div className="ct-profile">
      <Link to="/" className="ct-profile-back"><IconChevronLeft width={16} height={16} /> Back to your courses</Link>
      <h2 className="ct-profile-heading">{user?.username}</h2>
      {memberSince && <p className="ct-profile-sub">Member since {memberSince}</p>}

      <div className="ct-stat-grid">
        <div className="card ct-stat-card">
          <IconTrophy width={20} height={20} />
          <span className="ct-stat-value">{stats.streak_days}</span>
          <span className="ct-stat-label">day streak</span>
        </div>
        <div className="card ct-stat-card">
          <IconCheckCircle width={20} height={20} />
          <span className="ct-stat-value">{stats.lessons_completed}</span>
          <span className="ct-stat-label">lessons completed</span>
        </div>
        <div className="card ct-stat-card">
          <IconLibrary width={20} height={20} />
          <span className="ct-stat-value">{stats.courses_completed}</span>
          <span className="ct-stat-label">courses completed</span>
        </div>
        <div className="card ct-stat-card">
          <span className="ct-stat-value">{formatWatchTime(stats.watch_seconds)}</span>
          <span className="ct-stat-label">total watch time</span>
        </div>
      </div>

      <style>{`
        .ct-profile { max-width: 640px; margin: 0 auto; padding: var(--space-6) var(--space-5); }
        .ct-profile-back { display:inline-flex;align-items:center;gap:3px;color:var(--text-muted);text-decoration:none;font-size:var(--text-sm);margin-bottom:var(--space-5); }
        .ct-profile-back:hover { color:var(--accent); }
        .ct-profile-heading { font-size: var(--text-xl); }
        .ct-profile-sub { color: var(--text-muted); font-size: var(--text-sm); margin: 4px 0 var(--space-6); }
        .ct-stat-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: var(--space-3);
        }
        .ct-stat-card {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: 6px;
          padding: var(--space-4);
        }
        .ct-stat-card svg { color: var(--accent); margin-bottom: 2px; }
        .ct-stat-value { font-family: var(--font-display); font-size: 28px; font-weight: 700; }
        .ct-stat-label { font-size: var(--text-sm); color: var(--text-muted); }
      `}</style>
    </div>
  );
}
