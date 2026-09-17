import { useCallback, useEffect, useState } from "react";
import { clamp } from "./playerUtils";

export function usePersistedAudio(videoRef, lessonId) {
  const [volume, setVolume] = useState(() => clamp(Number(localStorage.getItem("ct_volume") ?? 1), 0, 1));
  const [muted, setMuted] = useState(() => localStorage.getItem("ct_muted") === "1");

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.volume = clamp(volume, 0, 1);
    video.muted = muted;
  }, [videoRef, lessonId, volume, muted]);

  const changeVolume = useCallback((value) => {
    const next = clamp(Number(value), 0, 1);
    setVolume(next);
    localStorage.setItem("ct_volume", String(next));
    if (videoRef.current) videoRef.current.volume = next;
    if (next > 0) {
      setMuted(false);
      localStorage.setItem("ct_muted", "0");
    }
  }, [videoRef]);

  const toggleMute = useCallback(() => {
    setMuted((current) => {
      const next = !current;
      localStorage.setItem("ct_muted", next ? "1" : "0");
      if (videoRef.current) videoRef.current.muted = next;
      return next;
    });
  }, [videoRef]);

  return { volume, muted, changeVolume, toggleMute };
}
