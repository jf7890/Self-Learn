import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "../api";
import { IconPlay, IconPause, IconFullscreen, IconVolume, IconVolumeMuted, IconReplay10, IconForward10 } from "../icons.jsx";

const SPEEDS = [1, 1.25, 1.5, 2];

function formatTime(sec) {
  if (!isFinite(sec) || sec < 0) return "0:00";
  const total = Math.floor(sec);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = (total % 60).toString().padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/**
 * lesson: current lesson object (id, title, position_seconds, ...)
 * lessons: flat ordered list of lessons in the section, for chapter markers + auto-advance
 * onNext: called when playback ends and there's a next lesson
 */
export default function VideoPlayer({ lesson, lessons, onNext, onProgress }) {
  const videoRef = useRef(null);
  const progressBarRef = useRef(null);
  const saveIntervalRef = useRef(null);

  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [volume, setVolume] = useState(() => Number(localStorage.getItem("ct_volume") ?? 1));
  const [muted, setMuted] = useState(() => localStorage.getItem("ct_muted") === "1");
  const [showSpeedMenu, setShowSpeedMenu] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [nextPrompt, setNextPrompt] = useState(false);
  const [buffering, setBuffering] = useState(false);
  const [preloadMode, setPreloadMode] = useState("metadata");
  const [bufferedEnd, setBufferedEnd] = useState(0);
  const [mediaError, setMediaError] = useState("");
  const controlsTimeout = useRef(null);
  const durationReportedRef = useRef(false);
  const autoCompletedRef = useRef(false);

  const hasSubtitles = lesson.subtitles && lesson.subtitles.length > 0;
  const [showCcMenu, setShowCcMenu] = useState(false);
  // The player remounts fresh on every lesson change (keyed by lesson.id
  // in the parent), so component state alone can't carry a "captions on"
  // preference across lessons — read it from localStorage instead, so
  // turning captions on once keeps them on for the rest of the course.
  const [activeTrackId, setActiveTrackId] = useState(() => {
    if (!hasSubtitles) return null;
    if (localStorage.getItem("ct_subtitles_on") !== "1") return null;
    const preferredLang = localStorage.getItem("ct_subtitles_lang");
    const match = lesson.subtitles.find((s) => s.language === preferredLang);
    return (match || lesson.subtitles[0]).id;
  });

  const selectTrack = (trackId) => {
    setActiveTrackId(trackId);
    setShowCcMenu(false);
    if (trackId === null) {
      localStorage.setItem("ct_subtitles_on", "0");
    } else {
      localStorage.setItem("ct_subtitles_on", "1");
      const track = lesson.subtitles.find((s) => s.id === trackId);
      if (track) localStorage.setItem("ct_subtitles_lang", track.language);
    }
  };

  // Sync the chosen track to the browser's actual TextTrack API — all
  // <track> elements are always rendered, this just flips which one (if
  // any) is actively showing.
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !v.textTracks) return;
    for (let i = 0; i < v.textTracks.length; i++) {
      const track = v.textTracks[i];
      const trackId = track.id ? Number(track.id) : null;
      track.mode = activeTrackId !== null && trackId === activeTrackId ? "showing" : "hidden";
    }
  }, [activeTrackId]);

  const nextLesson = (() => {
    if (!lessons) return null;
    const idx = lessons.findIndex((l) => l.id === lesson.id);
    return idx >= 0 && idx < lessons.length - 1 ? lessons[idx + 1] : null;
  })();

  // Resume from stored position when lesson changes
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    setNextPrompt(false); setBuffering(false); setPreloadMode("metadata"); setBufferedEnd(0); setMediaError("");
    durationReportedRef.current = false;
    autoCompletedRef.current = false;
    const resumeAt = lesson.position_seconds || 0;
    const onLoaded = () => {
      if (resumeAt > 2 && resumeAt < v.duration - 5) {
        v.currentTime = resumeAt;
      }
    };
    v.addEventListener("loadedmetadata", onLoaded, { once: true });
    return () => v.removeEventListener("loadedmetadata", onLoaded);
  }, [lesson.id]);

  // Periodic progress save (every 5s while playing)
  useEffect(() => {
    saveIntervalRef.current = setInterval(() => {
      const v = videoRef.current;
      if (v && !v.paused && v.currentTime > 0) {
        onProgress?.(lesson.id, v.currentTime, false);
      }
    }, 5000);
    return () => clearInterval(saveIntervalRef.current);
  }, [lesson.id, onProgress]);

  const handleTimeUpdate = () => {
    const v = videoRef.current;
    if (!v) return;
    setCurrent(v.currentTime);
    if (v.duration && v.currentTime > v.duration - 8 && !nextPrompt && nextLesson) {
      setNextPrompt(true);
    }
    // Safety net: mark complete at 95% watched, in case the tab closes or
    // the person navigates away just before the literal "ended" event —
    // otherwise a lesson watched almost entirely could stay unchecked forever.
    if (v.duration && !autoCompletedRef.current && v.currentTime / v.duration >= 0.95) {
      autoCompletedRef.current = true;
      onProgress?.(lesson.id, v.currentTime, true);
    }
  };

  const handleDurationChange = (e) => {
    const d = e.target.duration;
    setDuration(d);
    if (d && isFinite(d) && !durationReportedRef.current && !lesson.duration_seconds) {
      durationReportedRef.current = true;
      api.reportDuration(lesson.id, d).catch(() => {});
    }
  };

  const updateBuffered = () => {
    const v = videoRef.current;
    if (!v || !v.buffered?.length) return setBufferedEnd(0);
    for (let i = 0; i < v.buffered.length; i++) {
      if (v.currentTime >= v.buffered.start(i) && v.currentTime <= v.buffered.end(i)) {
        setBufferedEnd(v.buffered.end(i)); return;
      }
    }
    setBufferedEnd(v.buffered.end(v.buffered.length - 1));
  };

  const handleEnded = () => {
    onProgress?.(lesson.id, videoRef.current?.duration || 0, true);
    if (nextLesson) onNext?.(nextLesson);
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) v.play(); else v.pause();
  };

  const skip = useCallback((seconds) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, Math.min(v.duration || Infinity, v.currentTime + seconds));
    setShowControls(true);
  }, []);

  const changeVolume = (value) => {
    const next = Number(value);
    setVolume(next); localStorage.setItem("ct_volume", String(next));
    if (videoRef.current) videoRef.current.volume = next;
    if (next > 0 && muted) { setMuted(false); localStorage.setItem("ct_muted", "0"); }
  };

  const toggleMute = () => {
    const next = !muted;
    setMuted(next); localStorage.setItem("ct_muted", next ? "1" : "0");
    if (videoRef.current) videoRef.current.muted = next;
  };

  const seekTo = (fraction) => {
    const v = videoRef.current;
    if (!v || !duration) return;
    v.currentTime = fraction * duration;
  };

  const handleBarClick = (e) => {
    const rect = progressBarRef.current.getBoundingClientRect();
    seekTo((e.clientX - rect.left) / rect.width);
  };

  const handleBarTouch = (e) => {
    const rect = progressBarRef.current.getBoundingClientRect();
    const touch = e.touches[0];
    seekTo((touch.clientX - rect.left) / rect.width);
  };

  const changeSpeed = (s) => {
    setSpeed(s);
    if (videoRef.current) videoRef.current.playbackRate = s;
    setShowSpeedMenu(false);
  };

  const toggleFullscreen = () => {
    const el = videoRef.current?.closest(".ct-player");
    if (!document.fullscreenElement) el?.requestFullscreen?.();
    else document.exitFullscreen?.();
  };

  const revealControls = useCallback(() => {
    setShowControls(true);
    clearTimeout(controlsTimeout.current);
    controlsTimeout.current = setTimeout(() => {
      if (playing) setShowControls(false);
    }, 2800);
  }, [playing]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.volume = Math.max(0, Math.min(1, volume));
    v.muted = muted;
  }, [lesson.id]);

  useEffect(() => {
    const onKeyDown = (e) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target?.tagName) || e.target?.isContentEditable) return;
      if (e.key === "ArrowLeft") { e.preventDefault(); skip(-10); }
      if (e.key === "ArrowRight") { e.preventDefault(); skip(10); }
      if (e.key.toLowerCase() === "m") { e.preventDefault(); toggleMute(); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [skip, muted]);

  // chapter markers: lessons within this section, positioned along this
  // lesson's own duration isn't meaningful across files, so instead we
  // show *section progress* ticks below the bar rather than on it —
  // see the mini progress rail under the scrubber.

  return (
    <div className="ct-player" onMouseMove={revealControls} onClick={revealControls}>
      <video
        ref={videoRef}
        src={api.mediaUrl(lesson.id)}
        preload={preloadMode}
        onPlay={() => { setPlaying(true); setBuffering(false); setPreloadMode("auto"); }}
        onPlaying={() => { setPlaying(true); setBuffering(false); setMediaError(""); }}
        onWaiting={() => setBuffering(true)}
        onStalled={() => setBuffering(true)}
        onCanPlay={() => setBuffering(false)}
        onProgress={updateBuffered}
        onError={() => { setBuffering(false); setMediaError("Video could not be loaded. Check your connection and try again."); }}
        onPause={() => setPlaying(false)}
        onTimeUpdate={handleTimeUpdate}
        onDurationChange={handleDurationChange}
        onEnded={handleEnded}
        onClick={(e) => { e.stopPropagation(); togglePlay(); }}
        playsInline
        controlsList="nodownload"
      >
        {hasSubtitles && lesson.subtitles.map((sub) => (
          <track
            key={sub.id}
            id={String(sub.id)}
            kind="subtitles"
            src={api.subtitleUrl(sub.id)}
            srcLang={sub.language}
            label={sub.label}
          />
        ))}
      </video>

      {(buffering || mediaError) && <div className="ct-buffer-state" role="status">
        {buffering && !mediaError && <><span className="spinner" /> Buffering…</>}
        {mediaError && <><span>{mediaError}</span><button className="btn btn-primary btn-sm" onClick={() => { const v=videoRef.current; setMediaError(""); v?.load(); v?.play().catch(()=>{}); }}>Retry</button></>}
      </div>}

      {nextPrompt && nextLesson && (
        <div className="ct-next-card">
          <span>Next: {nextLesson.title}</span>
          <div className="ct-next-actions">
            <button className="btn btn-ghost btn-sm" onClick={() => { setNextPrompt(false); }}>Dismiss</button>
            <button className="btn btn-primary btn-sm" onClick={() => onNext(nextLesson)}>Play now</button>
          </div>
        </div>
      )}

      <div className={`ct-controls ${showControls ? "visible" : ""}`}>
        <div
          className="ct-scrubber"
          ref={progressBarRef}
          onClick={handleBarClick}
          onTouchStart={handleBarTouch}
          onTouchMove={handleBarTouch}
        >
          <div className="ct-scrubber-buffer" style={{ width: `${(bufferedEnd / duration || 0) * 100}%` }} />
          <div className="ct-scrubber-fill" style={{ width: `${(current / duration || 0) * 100}%` }} />
          <div className="ct-scrubber-handle" style={{ left: `${(current / duration || 0) * 100}%` }} />
        </div>

        <div className="ct-controls-row">
          <button className="ct-icon-btn" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
            {playing ? <IconPause width={20} height={20} fill="currentColor" /> : <IconPlay width={20} height={20} fill="currentColor" />}
          </button>
          <button className="ct-icon-btn ct-skip-btn" onClick={() => skip(-10)} aria-label="Back 10 seconds" title="Back 10 seconds (←)"><IconReplay10 width={22} height={22} /></button>
          <button className="ct-icon-btn ct-skip-btn" onClick={() => skip(10)} aria-label="Forward 10 seconds" title="Forward 10 seconds (→)"><IconForward10 width={22} height={22} /></button>
          <div className="ct-volume">
            <button className="ct-icon-btn" onClick={toggleMute} aria-label={muted ? "Unmute" : "Mute"} title="Mute (M)">{muted || volume === 0 ? <IconVolumeMuted width={20} height={20} /> : <IconVolume width={20} height={20} />}</button>
            <input type="range" min="0" max="1" step="0.05" value={muted ? 0 : volume} onChange={(e) => changeVolume(e.target.value)} aria-label="Volume" />
          </div>

          <span className="ct-time">{formatTime(current)} / {formatTime(duration)}</span>
          {duration > 0 && bufferedEnd > current + 0.5 && <span className="ct-buffer-ahead" title="Video buffered ahead">+{Math.floor(bufferedEnd - current)}s buffered</span>}

          <div className="ct-spacer" />

          {hasSubtitles && (
            <div className="ct-speed-wrap">
              <button
                className={`ct-icon-btn ct-cc-btn ${activeTrackId !== null ? "active" : ""}`}
                onClick={() => setShowCcMenu((s) => !s)}
                aria-label="Subtitles"
              >
                CC
              </button>
              {showCcMenu && (
                <div className="ct-speed-menu">
                  <button className={activeTrackId === null ? "active" : ""} onClick={() => selectTrack(null)}>Off</button>
                  {lesson.subtitles.map((sub) => (
                    <button key={sub.id} className={activeTrackId === sub.id ? "active" : ""} onClick={() => selectTrack(sub.id)}>
                      {sub.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="ct-speed-wrap">
            <button className="ct-icon-btn ct-speed-btn" onClick={() => setShowSpeedMenu((s) => !s)}>
              {speed}x
            </button>
            {showSpeedMenu && (
              <div className="ct-speed-menu">
                {SPEEDS.map((s) => (
                  <button key={s} className={s === speed ? "active" : ""} onClick={() => changeSpeed(s)}>
                    {s}x
                  </button>
                ))}
              </div>
            )}
          </div>

          <button className="ct-icon-btn" onClick={toggleFullscreen} aria-label="Fullscreen">
            <IconFullscreen width={18} height={18} />
          </button>
        </div>
      </div>

      <style>{`
        .ct-player {
          position: relative;
          width: 100%;
          aspect-ratio: 16 / 9;
          background: #000;
          border-radius: var(--radius);
          overflow: hidden;
        }
        .ct-player video {
          width: 100%;
          height: 100%;
          display: block;
          object-fit: contain;
        }
        .ct-buffer-state{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:10px;background:rgba(0,0,0,.35);color:#fff;font-size:14px;pointer-events:none}.ct-buffer-state .btn{pointer-events:auto}.ct-buffer-state .spinner{width:22px;height:22px}
        .ct-next-card {
          position: absolute;
          right: 16px;
          bottom: 84px;
          background: rgba(20,25,36,0.95);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          padding: 12px 14px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-width: 260px;
          animation: ct-slide-in 0.25s ease;
          font-size: 13px;
        }
        @keyframes ct-slide-in {
          from { transform: translateY(12px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
        .ct-next-actions { display: flex; gap: 8px; justify-content: flex-end; }

        .ct-controls {
          position: absolute;
          left: 0; right: 0; bottom: 0;
          padding: 10px 14px 12px;
          background: linear-gradient(to top, rgba(0,0,0,0.75), transparent);
          opacity: 0;
          transition: opacity 0.2s ease;
          pointer-events: none;
        }
        .ct-controls.visible { opacity: 1; pointer-events: auto; }

        .ct-scrubber {
          position: relative;
          height: 22px;
          display: flex;
          align-items: center;
          cursor: pointer;
          touch-action: none;
        }
        .ct-scrubber::before {
          content: "";
          position: absolute;
          left: 0; right: 0;
          height: 4px;
          background: rgba(255,255,255,0.25);
          border-radius: 2px;
        }
        .ct-scrubber-buffer { position:absolute; height:4px; background:rgba(255,255,255,.45); border-radius:2px; }
        .ct-scrubber-fill {
          position: absolute;
          height: 4px;
          background: var(--accent);
          border-radius: 2px;
        }
        .ct-scrubber-handle {
          position: absolute;
          width: 14px; height: 14px;
          background: var(--accent);
          border-radius: 50%;
          transform: translateX(-50%);
          box-shadow: 0 0 0 3px rgba(232,163,61,0.25);
        }

        .ct-controls-row {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-top: 4px;
        }
        .ct-icon-btn {
          background: transparent;
          border: none;
          color: #fff;
          padding: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 6px;
        }
        .ct-icon-btn:active { background: rgba(255,255,255,0.12); }
        .ct-time { color: #cfd3dc; font-size: 13px; font-variant-numeric: tabular-nums; }
        .ct-buffer-ahead { color:rgba(255,255,255,.68); font-size:11px; white-space:nowrap; font-variant-numeric:tabular-nums; }
        .ct-spacer { flex: 1; }
        .ct-volume { display:flex; align-items:center; }
        .ct-volume input { width:76px; accent-color:var(--accent); cursor:pointer; }
        .ct-skip-btn { padding-left:5px; padding-right:5px; }

        .ct-speed-wrap { position: relative; }
        .ct-speed-btn {
          font-size: 13px;
          font-weight: 600;
          min-width: 42px;
        }
        .ct-cc-btn {
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0.02em;
          min-width: 34px;
        }
        .ct-cc-btn.active { color: var(--accent); }
        .ct-speed-menu {
          position: absolute;
          bottom: 40px;
          right: 0;
          background: rgba(20,25,36,0.97);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          min-width: 60px;
        }
        .ct-speed-menu button {
          background: transparent;
          border: none;
          color: var(--text);
          padding: 8px 12px;
          text-align: left;
          font-size: 13px;
        }
        .ct-speed-menu button.active { color: var(--accent); font-weight: 600; }
        .ct-speed-menu button:active { background: rgba(255,255,255,0.08); }

        @media (max-width: 640px) {
          .ct-player { border-radius: 0; aspect-ratio: 16/9; }
          .ct-controls { padding: 8px 10px 10px; }
          .ct-icon-btn { padding: 8px; }
          .ct-controls-row { gap: 3px; }
          .ct-volume input { width: 52px; }
          .ct-time { font-size: 11px; }
          .ct-buffer-ahead { display:none; }
        }
        @media (max-width: 430px) {
          .ct-volume input { display:none; }
        }
      `}</style>
    </div>
  );
}
