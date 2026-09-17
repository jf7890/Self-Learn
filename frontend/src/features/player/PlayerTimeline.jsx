export default function PlayerTimeline({ barRef, current, duration, bufferedEnd, onClick, onTouch }) {
  const progress = (current / duration || 0) * 100;
  const buffered = (bufferedEnd / duration || 0) * 100;
  return (
    <div className="ct-scrubber" ref={barRef} onClick={onClick} onTouchStart={onTouch} onTouchMove={onTouch}>
      <div className="ct-scrubber-buffer" style={{ width: `${buffered}%` }} />
      <div className="ct-scrubber-fill" style={{ width: `${progress}%` }} />
      <div className="ct-scrubber-handle" style={{ left: `${progress}%` }} />
    </div>
  );
}
