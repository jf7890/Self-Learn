import { useState, useMemo } from "react";
import { IconPlay, IconMusic, IconHelpCircle, IconFileText, IconCheck, IconPaperclip, IconChevronDown, IconChevronRight, IconSearch, BrandMark } from "../icons.jsx";

function TypeIcon({ mediaType, ...props }) {
  switch (mediaType) {
    case "video": return <IconPlay fill="currentColor" {...props} />;
    case "audio": return <IconMusic {...props} />;
    case "quiz": return <IconHelpCircle {...props} />;
    default: return <IconFileText {...props} />;
  }
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "--:--";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

export default function LessonSidebar({ sections, activeLessonId, onSelect, open, onClose }) {
  const [collapsed, setCollapsed] = useState({});
  const [query, setQuery] = useState("");

  const toggle = (id) => setCollapsed((c) => ({ ...c, [id]: !c[id] }));

  const filteredSections = useMemo(() => {
    if (!query.trim()) return sections;
    const q = query.toLowerCase();
    return sections
      .map((s) => ({ ...s, lessons: s.lessons.filter((l) => l.title.toLowerCase().includes(q)) }))
      .filter((s) => s.lessons.length > 0 || s.title.toLowerCase().includes(q));
  }, [sections, query]);

  const isSearching = query.trim().length > 0;

  return (
    <>
      {open && <div className="ct-sheet-backdrop" onClick={onClose} />}
      <aside className={`ct-sidebar ${open ? "open" : ""}`}>
        <div className="ct-sidebar-handle" onClick={onClose} />
        <div className="ct-sidebar-search">
          <IconSearch width={14} height={14} />
          <input placeholder="Search lessons…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="ct-sidebar-list">
          {filteredSections.length === 0 && (
            <p className="ct-sidebar-empty">No lessons match "{query}"</p>
          )}
          {filteredSections.map((section) => {
            const total = section.lessons.length;
            const done = section.lessons.filter((l) => l.completed).length;
            const isCollapsed = isSearching ? false : collapsed[section.id];
            return (
              <div key={section.id} className="ct-section">
                <button className="ct-section-header" onClick={() => toggle(section.id)}>
                  <span className="ct-section-flag"><BrandMark size={10} /></span>
                  <span className="ct-section-title">{section.title}</span>
                  <span className="ct-section-count">{done}/{total}</span>
                  {isCollapsed ? <IconChevronRight width={13} height={13} /> : <IconChevronDown width={13} height={13} />}
                </button>
                {total > 0 && (
                  <div className="ct-section-progress">
                    <div className="ct-section-progress-fill" style={{ width: `${(done / total) * 100}%` }} />
                  </div>
                )}

                {!isCollapsed && (
                  <ul className="ct-lesson-list">
                    {section.lessons.map((lesson) => {
                      const watchFraction = lesson.duration_seconds && lesson.position_seconds
                        ? Math.min(1, lesson.position_seconds / lesson.duration_seconds)
                        : 0;
                      const inProgress = !lesson.completed && watchFraction > 0.02;
                      return (
                        <li key={lesson.id}>
                          <button
                            className={`ct-lesson ${lesson.id === activeLessonId ? "active" : ""} ${lesson.completed ? "done" : ""}`}
                            onClick={() => onSelect(lesson, section)}
                          >
                            <span className="ct-lesson-icon">
                              {lesson.completed ? <IconCheck width={13} height={13} /> : <TypeIcon mediaType={lesson.media_type} width={13} height={13} />}
                            </span>
                            <span className="ct-lesson-title">{lesson.title}</span>
                            <span className="ct-lesson-size">{formatDuration(lesson.duration_seconds)}</span>
                            {inProgress && (
                              <span className="ct-lesson-progress">
                                <span style={{ width: `${watchFraction * 100}%` }} />
                              </span>
                            )}
                          </button>
                        </li>
                      );
                    })}

                    {section.attachments?.length > 0 && (
                      <li className="ct-attachments-inline">
                        <IconPaperclip width={12} height={12} />
                        {section.attachments.length} attachment{section.attachments.length > 1 ? "s" : ""}
                      </li>
                    )}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      <style>{`
        .ct-sidebar {
          width: 328px;
          flex-shrink: 0;
          background: var(--surface);
          border-right: 1px solid var(--border);
          overflow-y: auto;
          max-height: calc(100dvh - 56px);
        }
        .ct-sidebar-handle { display: none; }
        .ct-sidebar-search {
          display: flex;
          align-items: center;
          gap: var(--space-2);
          padding: var(--space-3) var(--space-4);
          border-bottom: 1px solid var(--border);
          color: var(--text-faint);
        }
        .ct-sidebar-search input {
          flex: 1;
          background: transparent;
          border: none;
          color: var(--text);
          font-size: var(--text-sm);
          font-family: var(--font-body);
        }
        .ct-sidebar-search input::placeholder { color: var(--text-faint); }
        .ct-sidebar-search input:focus { outline: none; }
        .ct-sidebar-empty { padding: var(--space-4); font-size: var(--text-sm); color: var(--text-muted); }

        .ct-section-header {
          width: 100%;
          display: flex;
          align-items: center;
          gap: var(--space-2);
          background: transparent;
          border: none;
          border-bottom: 1px solid var(--border);
          color: var(--text);
          padding: var(--space-3) var(--space-4) var(--space-2);
          text-align: left;
          font-weight: 600;
          font-size: var(--text-sm);
        }
        .ct-section-flag { color: var(--accent); flex-shrink: 0; display: inline-flex; }
        .ct-section-title { flex: 1; }
        .ct-section-count {
          font-size: var(--text-xs);
          font-weight: 500;
          color: var(--text-muted);
          font-variant-numeric: tabular-nums;
        }
        .ct-section-header svg { color: var(--text-faint); flex-shrink: 0; }
        .ct-section-progress {
          height: 2px;
          background: var(--border);
          margin: 0 var(--space-4) var(--space-1);
        }
        .ct-section-progress-fill { height: 100%; background: var(--complete); }

        .ct-lesson-list { list-style: none; margin: 0; padding: var(--space-1) 0 var(--space-2); }
        .ct-lesson {
          width: 100%;
          display: flex;
          align-items: center;
          gap: var(--space-2);
          background: transparent;
          border: none;
          color: var(--text-muted);
          padding: 9px var(--space-4) 9px 30px;
          text-align: left;
          font-size: var(--text-sm);
          border-left: 2px solid transparent;
          position: relative;
          transition: background var(--dur-fast) var(--ease);
        }
        .ct-lesson-icon {
          width: 15px;
          display: inline-flex;
          justify-content: center;
          color: var(--text-faint);
          flex-shrink: 0;
        }
        .ct-lesson-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .ct-lesson-size { font-size: var(--text-xs); color: var(--text-faint); flex-shrink: 0; }
        .ct-lesson.done .ct-lesson-icon { color: var(--complete); }
        .ct-lesson.active {
          color: var(--text);
          background: var(--surface-raised);
          border-left-color: var(--accent);
        }
        .ct-lesson:hover:not(.active) { background: rgba(255,255,255,0.02); }
        .ct-lesson-progress {
          position: absolute;
          left: 30px;
          right: var(--space-4);
          bottom: 2px;
          height: 2px;
          background: var(--border);
          border-radius: 1px;
          overflow: hidden;
        }
        .ct-lesson-progress span { display: block; height: 100%; background: var(--accent); }

        .ct-attachments-inline {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 7px var(--space-4) 7px 30px;
          font-size: var(--text-xs);
          color: var(--accent);
        }

        .ct-sheet-backdrop { display: none; }

        @media (max-width: 900px) {
          .ct-sidebar {
            position: fixed;
            left: 0; right: 0; bottom: 0;
            width: 100%;
            max-height: 72dvh;
            border-right: none;
            border-top: 1px solid var(--border);
            border-radius: var(--radius-lg) var(--radius-lg) 0 0;
            transform: translateY(100%);
            transition: transform var(--dur) var(--ease);
            z-index: 40;
            box-shadow: var(--shadow-lg);
          }
          .ct-sidebar.open { transform: translateY(0); }
          .ct-sidebar-handle {
            display: block;
            width: 36px; height: 4px;
            background: var(--border-strong);
            border-radius: 2px;
            margin: 10px auto;
          }
          .ct-sheet-backdrop {
            display: block;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.5);
            z-index: 39;
          }
        }
      `}</style>
    </>
  );
}
