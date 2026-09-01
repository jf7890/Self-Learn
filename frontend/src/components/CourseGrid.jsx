import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { IconLibrary, IconPlay, BrandMark } from "../icons.jsx";

// deterministic gradient per course, from a small warm/cool palette that
// stays in-family with the marigold accent rather than random hues
const PALETTE = [
  ["#e8a33d", "#8a6524"],
  ["#3dc4a8", "#1f6b5c"],
  ["#4d90e8", "#22406e"],
  ["#c15fe0", "#5c2a6e"],
  ["#e0625f", "#6e2a2a"],
  ["#5fe0a0", "#2a6e4d"],
];

const NEW_WINDOW_DAYS = 7;

function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
  return hash;
}

function thumbGradient(title) {
  const [a, b] = PALETTE[hashString(title) % PALETTE.length];
  return `linear-gradient(135deg, ${a}55, ${b}aa), linear-gradient(#141924, #141924)`;
}

function monogram(title) {
  const words = title.trim().split(/\s+/).filter(Boolean);
  const letters = words.slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  return letters || "?";
}

function parseTags(tags) {
  return (tags || "").split(",").map((t) => t.trim()).filter(Boolean);
}

function isRecent(addedAt) {
  if (!addedAt) return false;
  const added = new Date(addedAt.replace(" ", "T") + "Z").getTime();
  return (Date.now() - added) / (1000 * 60 * 60 * 24) <= NEW_WINDOW_DAYS;
}

export default function CourseGrid() {
  const [courses, setCourses] = useState(null);
  const [featured, setFeatured] = useState([]);
  const [continueWatching, setContinueWatching] = useState([]);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all"); // all | in_progress | completed | not_started
  const [tagFilter, setTagFilter] = useState(null);

  const loadLibrary = () => {
    setError(null);
    api.getCourses().then(setCourses).catch((e) => setError(e.message));
    api.getFeatured().then(setFeatured).catch(() => {});
    api.getContinueWatching().then(setContinueWatching).catch(() => {});
  };

  useEffect(() => {
    loadLibrary();
    const refresh = () => loadLibrary();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);

  const allTags = useMemo(() => {
    if (!courses) return [];
    const set = new Set();
    courses.forEach((c) => parseTags(c.tags).forEach((t) => set.add(t)));
    return [...set].sort();
  }, [courses]);

  if (error) return <p className="alert alert-danger" style={{ margin: 20 }}>{error}</p>;
  if (!courses) return <div className="state-screen"><span className="spinner" /></div>;

  if (courses.length === 0) {
    return (
      <div className="empty-state">
        <IconLibrary width={40} height={40} />
        <p className="empty-state-title">No courses yet</p>
        <p className="empty-state-sub">Drop course folders into the courses/ directory, then rescan the library from Admin.</p>
        <button className="btn btn-primary" onClick={loadLibrary}>Refresh courses</button>
      </div>
    );
  }

  const matchesFilter = (c) => {
    if (filter === "completed") return c.percent_complete === 100;
    if (filter === "in_progress") return c.percent_complete > 0 && c.percent_complete < 100;
    if (filter === "not_started") return c.percent_complete === 0;
    return true;
  };

  const filtered = courses.filter(
    (c) =>
      matchesFilter(c) &&
      c.title.toLowerCase().includes(query.toLowerCase()) &&
      (!tagFilter || parseTags(c.tags).includes(tagFilter))
  );

  return (
    <div>
      {featured.length > 0 && (
        <div className="ct-featured-section">
          <h2 className="ct-featured-heading">Featured</h2>
          <div className="ct-featured-row">
            {featured.map((c) => (
              <Link key={c.id} to={`/course/${c.id}`} className="ct-featured-card" style={{ background: thumbGradient(c.title) }}>
                <div className="ct-featured-info">
                  <p className="ct-featured-title">{c.title}</p>
                  <p className="ct-featured-meta">{c.lesson_count} lessons{c.percent_complete > 0 ? ` · ${c.percent_complete}% complete` : ""}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {continueWatching.length > 0 && (
        <div className="ct-continue-section">
          <h2 className="ct-continue-heading">Continue watching</h2>
          <div className="ct-continue-row">
            {continueWatching.map((cw) => {
              const pct = cw.duration_seconds
                ? Math.min(100, Math.round((cw.position_seconds / cw.duration_seconds) * 100))
                : null;
              return (
                <Link
                  key={cw.lesson_id}
                  to={`/course/${cw.course_id}?lesson=${cw.lesson_id}`}
                  className="ct-continue-card"
                  style={{ background: thumbGradient(cw.course_title) }}
                >
                  <IconPlay width={13} height={13} className="ct-continue-play" fill="currentColor" />
                  <div className="ct-continue-info">
                    <p className="ct-continue-lesson">{cw.lesson_title}</p>
                    <p className="ct-continue-course">{cw.course_title}</p>
                  </div>
                  {pct !== null && (
                    <div className="ct-continue-bar"><div style={{ width: `${pct}%` }} /></div>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      )}

      <h2 className="ct-grid-heading">Your courses</h2>
      <div className="ct-toolbar">
        <input
          className="ct-search-input"
          placeholder="Search courses…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="ct-filter-chips">
          {[["all", "All"], ["in_progress", "In progress"], ["completed", "Completed"], ["not_started", "Not started"]].map(([id, label]) => (
            <button key={id} className={filter === id ? "active" : ""} onClick={() => setFilter(id)}>{label}</button>
          ))}
        </div>
      </div>

      {allTags.length > 0 && (
        <div className="ct-tag-row">
          <button className={!tagFilter ? "active" : ""} onClick={() => setTagFilter(null)}>All tags</button>
          {allTags.map((t) => (
            <button key={t} className={tagFilter === t ? "active" : ""} onClick={() => setTagFilter(t)}>{t}</button>
          ))}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="empty-state">
          <IconLibrary width={32} height={32} />
          <p className="empty-state-title">No matches</p>
          <p className="empty-state-sub">Try a different search or filter.</p>
        </div>
      ) : (
        <div className="ct-grid">
          {filtered.map((c) => (
            <Link key={c.id} to={`/course/${c.id}`} className="ct-card">
              <div className="ct-card-thumb" style={{ background: thumbGradient(c.title) }}>
                <span className="ct-card-corner"><BrandMark size={11} /></span>
                <span className="ct-card-monogram">{monogram(c.title)}</span>
                {isRecent(c.added_at) && <span className="badge badge-complete ct-card-new">New</span>}
                {c.percent_complete > 0 && (
                  <span className="badge badge-accent ct-card-badge">{c.percent_complete}%</span>
                )}
              </div>
              <div className="ct-card-body">
                <h3>{c.title}</h3>
                {parseTags(c.tags).length > 0 && (
                  <div className="ct-card-tags">
                    {parseTags(c.tags).map((t) => <span key={t} className="badge badge-neutral">{t}</span>)}
                  </div>
                )}
                <div className="ct-card-progress-row">
                  <div className="ct-card-bar">
                    <div className="ct-card-bar-fill" style={{ width: `${c.percent_complete}%` }} />
                  </div>
                  <span>{c.percent_complete}%</span>
                </div>
                <p className="ct-card-meta">{c.completed_count} / {c.lesson_count} lessons</p>
              </div>
            </Link>
          ))}
        </div>
      )}

      <style>{`
        .ct-featured-section { padding: var(--space-5) var(--space-5) 0; }
        .ct-featured-heading { font-size: var(--text-md); font-weight: 600; margin: 0 0 var(--space-3); }
        .ct-featured-row {
          display: flex;
          gap: var(--space-3);
          overflow-x: auto;
          padding-bottom: var(--space-2);
          scrollbar-width: thin;
        }
        .ct-featured-card {
          position: relative;
          flex: 0 0 300px;
          height: 168px;
          border-radius: var(--radius);
          text-decoration: none;
          color: #fff;
          display: flex;
          align-items: flex-end;
          padding: var(--space-4);
          overflow: hidden;
          box-shadow: var(--shadow-md);
          transition: transform var(--dur) var(--ease);
        }
        .ct-featured-card:hover { transform: translateY(-3px); }
        .ct-featured-card::before {
          content: "";
          position: absolute;
          inset: 0;
          background: linear-gradient(to top, rgba(0,0,0,0.8), transparent 55%);
        }
        .ct-featured-info { position: relative; z-index: 1; min-width: 0; }
        .ct-featured-title {
          font-family: var(--font-display);
          font-size: var(--text-lg);
          font-weight: 700;
          margin: 0;
          line-height: 1.25;
        }
        .ct-featured-meta { font-size: var(--text-xs); margin: 4px 0 0; opacity: 0.8; }

        .ct-continue-section { padding: var(--space-5) var(--space-5) 0; }
        .ct-continue-heading {
          font-size: var(--text-md);
          font-weight: 600;
          margin: 0 0 var(--space-3);
        }
        .ct-grid-heading {
          font-size: var(--text-md);
          font-weight: 600;
          margin: 0;
          padding: var(--space-6) var(--space-5) 0;
        }
        .ct-toolbar {
          display: flex;
          align-items: center;
          gap: var(--space-3);
          flex-wrap: wrap;
          padding: var(--space-3) var(--space-5) var(--space-2);
        }
        .ct-search-input {
          font-family: var(--font-body);
          font-size: var(--text-sm);
          color: var(--text);
          background: var(--surface-raised);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          padding: 8px 12px;
          width: 240px;
          max-width: 100%;
        }
        .ct-search-input:focus { outline: none; border-color: var(--accent-dim); }
        .ct-filter-chips { display: flex; gap: 6px; flex-wrap: wrap; }
        .ct-filter-chips button {
          background: var(--surface-raised);
          border: 1px solid var(--border);
          color: var(--text-muted);
          border-radius: 20px;
          padding: 6px 13px;
          font-size: var(--text-xs);
          font-weight: 500;
          transition: color var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease);
        }
        .ct-filter-chips button:hover { color: var(--text); }
        .ct-filter-chips button.active { color: var(--accent); border-color: var(--accent-dim); background: var(--accent-soft); }
        .ct-tag-row { display: flex; gap: 6px; flex-wrap: wrap; padding: 0 var(--space-5) var(--space-4); }
        .ct-tag-row button {
          background: transparent;
          border: 1px solid var(--border);
          color: var(--text-faint);
          border-radius: 20px;
          padding: 4px 11px;
          font-size: var(--text-xs);
        }
        .ct-tag-row button:hover { color: var(--text-muted); }
        .ct-tag-row button.active { color: var(--accent); border-color: var(--accent-dim); }
        @media (max-width: 640px) {
          .ct-toolbar { flex-direction: column; align-items: stretch; }
          .ct-search-input { width: 100%; }
        }
        .ct-continue-row {
          display: flex;
          gap: var(--space-3);
          overflow-x: auto;
          padding-bottom: var(--space-2);
          scrollbar-width: thin;
        }
        .ct-continue-card {
          position: relative;
          flex: 0 0 216px;
          height: 108px;
          border-radius: var(--radius);
          text-decoration: none;
          color: #fff;
          display: flex;
          align-items: flex-end;
          padding: var(--space-3);
          overflow: hidden;
          box-shadow: var(--shadow-sm);
          transition: transform var(--dur) var(--ease);
        }
        .ct-continue-card:hover { transform: translateY(-2px); }
        .ct-continue-card::before {
          content: "";
          position: absolute;
          inset: 0;
          background: linear-gradient(to top, rgba(0,0,0,0.78), transparent 62%);
        }
        .ct-continue-play {
          position: absolute;
          top: 10px;
          right: 12px;
          opacity: 0.85;
        }
        .ct-continue-info { position: relative; z-index: 1; min-width: 0; }
        .ct-continue-lesson {
          font-size: var(--text-sm);
          font-weight: 600;
          margin: 0;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .ct-continue-course {
          font-size: var(--text-xs);
          margin: 2px 0 0;
          opacity: 0.75;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .ct-continue-bar {
          position: absolute;
          left: 0; right: 0; bottom: 0;
          height: 3px;
          background: rgba(255,255,255,0.2);
        }
        .ct-continue-bar div { height: 100%; background: var(--accent); }

        .ct-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(216px, 1fr));
          gap: var(--space-4);
          padding: 0 var(--space-5) var(--space-6);
        }
        .ct-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          overflow: hidden;
          text-decoration: none;
          color: var(--text);
          transition: border-color var(--dur) var(--ease), transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
        }
        .ct-card:hover { border-color: var(--border-strong); transform: translateY(-2px); box-shadow: var(--shadow-md); }
        .ct-card-thumb {
          position: relative;
          aspect-ratio: 16/9;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
        }
        .ct-card-thumb::before {
          content: "";
          position: absolute;
          inset: 0;
          background: radial-gradient(circle at 30% 20%, rgba(255,255,255,0.08), transparent 60%);
        }
        .ct-card-corner {
          position: absolute;
          top: 10px;
          left: 10px;
          color: rgba(255,255,255,0.55);
        }
        .ct-card-monogram {
          font-family: var(--font-display);
          font-size: 26px;
          font-weight: 700;
          color: rgba(255,255,255,0.85);
          letter-spacing: 0.02em;
        }
        .ct-card-new {
          position: absolute;
          top: 8px;
          left: 34px;
        }
        .ct-card-badge {
          position: absolute;
          top: 8px;
          right: 8px;
          background: rgba(11,14,20,0.78);
          backdrop-filter: blur(2px);
        }
        .ct-card-body { padding: var(--space-3) var(--space-4) var(--space-4); }
        .ct-card-body h3 {
          font-size: var(--text-base);
          font-weight: 600;
          margin-bottom: var(--space-2);
          line-height: 1.35;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .ct-card-tags { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: var(--space-3); }
        .ct-card-tags .badge { font-size: 10px; padding: 2px 7px; }
        .ct-card-progress-row { display: flex; align-items: center; gap: var(--space-2); }
        .ct-card-bar {
          flex: 1;
          height: 4px;
          background: var(--surface-raised);
          border-radius: 2px;
          overflow: hidden;
        }
        .ct-card-bar-fill { height: 100%; background: var(--accent); }
        .ct-card-progress-row span { font-size: var(--text-xs); color: var(--text-muted); font-variant-numeric: tabular-nums; }
        .ct-card-meta { font-size: var(--text-xs); color: var(--text-muted); margin: var(--space-2) 0 0; }
      `}</style>
    </div>
  );
}
