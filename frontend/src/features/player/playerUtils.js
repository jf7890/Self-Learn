export const PLAYBACK_SPEEDS = [1, 1.25, 1.5, 2];

export function formatPlaybackTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = String(total % 60).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${remainingSeconds}`
    : `${minutes}:${remainingSeconds}`;
}

export function findNextLesson(lessons, currentLessonId) {
  if (!Array.isArray(lessons)) return null;
  const index = lessons.findIndex((lesson) => lesson.id === currentLessonId);
  return index >= 0 && index < lessons.length - 1 ? lessons[index + 1] : null;
}

export function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}
