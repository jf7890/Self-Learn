import { useEffect, useState, useMemo, useCallback } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { api } from "../api";
import VideoPlayer from "./VideoPlayer.jsx";
import DocViewer from "./DocViewer.jsx";
import LessonSidebar from "./LessonSidebar.jsx";
import Certificate from "./Certificate.jsx";
import LessonNotes from "./LessonNotes.jsx";
import { IconChevronLeft, IconTrophy, IconInbox, IconChevronDown, IconLibrary } from "../icons.jsx";

export default function CourseView() {
  const { courseId } = useParams();
  const [searchParams] = useSearchParams();
  const [course, setCourse] = useState(null);
  const [activeLesson, setActiveLesson] = useState(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showCertificate, setShowCertificate] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.getCourse(courseId).then((c) => {
      setCourse(c);
      const allLessons = c.sections.flatMap((s) => s.lessons);
      const deepLinkId = searchParams.get("lesson");
      const deepLinked = deepLinkId && allLessons.find((l) => String(l.id) === deepLinkId);
      const firstIncomplete = allLessons.find((l) => !l.completed);
      setActiveLesson(deepLinked || firstIncomplete || c.sections[0]?.lessons[0] || null);
    }).catch((e) => setError(e.message)).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  const flatLessons = useMemo(
    () => course?.sections.flatMap((s) => s.lessons.map((l) => ({ ...l, sectionId: s.id }))) || [],
    [course]
  );

  const allComplete = flatLessons.length > 0 && flatLessons.every((l) => l.completed);

  const activeSectionAttachments = useMemo(() => {
    if (!course || !activeLesson) return [];
    const section = course.sections.find((s) => s.lessons.some((l) => l.id === activeLesson.id));
    return section?.attachments || [];
  }, [course, activeLesson]);

  const handleProgress = useCallback((lessonId, positionSeconds, completed) => {
    api.updateProgress(lessonId, positionSeconds, completed).catch(() => {});
    setCourse((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        sections: prev.sections.map((s) => ({
          ...s,
          lessons: s.lessons.map((l) =>
            l.id === lessonId ? { ...l, position_seconds: positionSeconds, completed: completed ? 1 : l.completed } : l
          ),
        })),
      };
    });
  }, []);

  if (error) return <p className="alert alert-danger" style={{ margin: 20 }}>{error}</p>;
  if (loading) return <div className="state-screen"><span className="spinner" /></div>;
  if (!course) return <p className="alert alert-danger" style={{ margin: 20 }}>Course not found.</p>;
  if (!activeLesson) {
    return (
      <div className="empty-state">
        <IconLibrary width={36} height={36} />
        <p className="empty-state-title">No lessons in this course yet</p>
        <p className="empty-state-sub">
          Nothing playable was found for "{course.title}" the last time the library was scanned.
          If you've just added files, ask an admin to rescan under Admin → Library.
        </p>
        <Link to="/" className="btn btn-secondary" style={{ marginTop: 12 }}>Back to courses</Link>
      </div>
    );
  }

  return (
    <div className="ct-course-view">
      <LessonSidebar
        sections={course.sections}
        activeLessonId={activeLesson.id}
        onSelect={(lesson) => {
          setActiveLesson(lesson);
          setSheetOpen(false);
        }}
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
      />

      <div className="ct-player-column">
        <div className="ct-player-topbar">
          <Link to="/" className="ct-back"><IconChevronLeft width={15} height={15} /> Courses</Link>
          <h2 className="ct-lesson-heading">{activeLesson.title}</h2>
          <button className="btn btn-secondary btn-sm ct-lessons-toggle" onClick={() => setSheetOpen(true)}>
            Lessons <IconChevronDown width={13} height={13} />
          </button>
        </div>

        {allComplete && (
          <div className="alert alert-success ct-complete-banner">
            <IconTrophy width={16} height={16} /> Course complete — nice work.
            <button className="btn btn-secondary btn-sm ct-cert-btn" onClick={() => setShowCertificate(true)}>
              View certificate
            </button>
          </div>
        )}

        {(activeLesson.media_type === "video" || activeLesson.media_type === "audio") ? (
          <VideoPlayer
            key={activeLesson.id}
            lesson={activeLesson}
            lessons={flatLessons}
            onNext={(l) => setActiveLesson(l)}
            onProgress={handleProgress}
          />
        ) : (
          <DocViewer
            key={activeLesson.id}
            lesson={activeLesson}
            onMarkComplete={(lessonId) => handleProgress(lessonId, 0, true)}
          />
        )}

        {activeSectionAttachments.length > 0 && (
          <div className="card ct-attachments">
            <h4><IconInbox width={14} height={14} /> Resources</h4>
            <ul>
              {activeSectionAttachments.map((a) => (
                <li key={a.id}>
                  <a href={api.attachmentUrl(a.id)} download>
                    {a.file_name} <span>({(a.size_bytes / 1024 / 1024).toFixed(1)} MB)</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        <LessonNotes lessonId={activeLesson.id} />
      </div>

      {showCertificate && (
        <Certificate
          courseTitle={course.title}
          username={JSON.parse(localStorage.getItem("ct_user") || "null")?.username || "Learner"}
          onClose={() => setShowCertificate(false)}
        />
      )}

      <style>{`
        .ct-course-view {
          display: flex;
          height: 100dvh;
        }
        .ct-player-column {
          flex: 1;
          min-width: 0;
          display: flex;
          flex-direction: column;
          padding: var(--space-4) var(--space-5);
          gap: var(--space-3);
          overflow-y: auto;
          max-width: 1500px;
          margin: 0 auto;
        }
        .ct-player-topbar {
          display: flex;
          align-items: center;
          gap: var(--space-4);
        }
        .ct-back {
          display: flex;
          align-items: center;
          gap: 2px;
          font-size: var(--text-sm);
          color: var(--text-muted);
          text-decoration: none;
          flex-shrink: 0;
          transition: color var(--dur-fast) var(--ease);
        }
        .ct-back:hover { color: var(--text); }
        .ct-lesson-heading {
          font-size: var(--text-md);
          font-weight: 600;
          flex: 1;
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .ct-lessons-toggle { display: none; flex-shrink: 0; }
        .ct-attachments { padding: var(--space-3) var(--space-4); }
        .ct-attachments h4 {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: var(--text-sm);
          margin: 0 0 var(--space-2);
          color: var(--text-muted);
          font-weight: 600;
        }
        .ct-attachments ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
        .ct-attachments a {
          font-size: var(--text-sm);
          text-decoration: none;
          color: var(--accent);
        }
        .ct-attachments a:hover { text-decoration: underline; }
        .ct-attachments a span { color: var(--text-muted); }
        .ct-complete-banner { font-weight: 500; align-items: center; }
        .ct-cert-btn { margin-left: auto; }

        @media (max-width: 900px) {
          .ct-course-view { flex-direction: column; height: auto; min-height: 100dvh; }
          .ct-lessons-toggle { display: inline-flex; }
          .ct-player-column { padding: var(--space-3); }
        }
      `}</style>
    </div>
  );
}
