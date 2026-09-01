import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const WIDTHS = [25, 50, 75, 100];

export default function LessonNotes({ lessonId }) {
  const editor = useRef(null);
  const [editing, setEditing] = useState(false);
  const [html, setHtml] = useState("");
  const [status, setStatus] = useState("");
  const [selectedImage, setSelectedImage] = useState(null);

  useEffect(() => {
    setStatus("Loading…"); setEditing(false); setSelectedImage(null);
    api.getNote(lessonId).then((note) => {
      const value = note?.content_html || "";
      setHtml(value); setStatus("");
    }).catch((e) => setStatus(e.message));
  }, [lessonId]);

  useEffect(() => {
    if (editing && editor.current) editor.current.innerHTML = html;
  }, [editing]);

  const command = (name, value = null) => {
    editor.current?.focus();
    document.execCommand(name, false, value);
  };

  const insertImage = async (file) => {
    if (!file?.type?.startsWith("image/")) return;
    setStatus("Uploading image…");
    try {
      const result = await api.uploadNoteImage(lessonId, file);
      editor.current?.focus();
      document.execCommand("insertHTML", false, `<img src="${result.url}" data-width="100" style="width:100%;height:auto" alt="Note image"><p><br></p>`);
      setStatus("Image added — save your note");
    } catch (e) { setStatus(e.message); }
  };

  const onPaste = (event) => {
    const image = [...(event.clipboardData?.items || [])].find((item) => item.type.startsWith("image/"));
    if (image) { event.preventDefault(); insertImage(image.getAsFile()); }
  };

  const onEditorClick = (event) => {
    const img = event.target.closest?.("img");
    if (selectedImage) selectedImage.classList.remove("note-image-selected");
    if (img) { img.classList.add("note-image-selected"); setSelectedImage(img); }
    else setSelectedImage(null);
  };

  const resize = (width) => {
    if (!selectedImage) return;
    selectedImage.dataset.width = String(width);
    selectedImage.style.width = `${width}%`;
  };

  const save = async () => {
    setStatus("Saving…");
    try {
      const result = await api.saveNote(lessonId, editor.current?.innerHTML || "");
      setHtml(result.content_html || ""); setEditing(false); setSelectedImage(null); setStatus("Saved");
    } catch (e) { setStatus(e.message); }
  };

  return <section className="lesson-notes card">
    <div className="notes-head">
      <div><h3>My notes</h3><p>Private notes for this lesson. Paste screenshots directly from your clipboard.</p></div>
      {!editing && <button className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>Edit note</button>}
    </div>
    {editing ? <>
      <div className="notes-toolbar">
        <button onClick={() => command("bold")}><b>B</b></button>
        <button onClick={() => command("italic")}><i>I</i></button>
        <button onClick={() => command("insertUnorderedList")}>• List</button>
        <button onClick={() => command("formatBlock", "blockquote")}>Quote</button>
        <label className="notes-upload">Add image<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={(e) => insertImage(e.target.files?.[0])}/></label>
        {selectedImage && <span className="resize-tools">Image: {WIDTHS.map(w => <button key={w} onClick={() => resize(w)}>{w}%</button>)}</span>}
      </div>
      <div ref={editor} className="notes-editor" contentEditable suppressContentEditableWarning onPaste={onPaste} onClick={onEditorClick} />
      <div className="notes-actions"><span>{status}</span><button className="btn btn-ghost" onClick={() => {setEditing(false); setSelectedImage(null)}}>Cancel</button><button className="btn btn-primary" onClick={save}>Save note</button></div>
    </> : <div className={`notes-view ${html ? "" : "empty"}`} dangerouslySetInnerHTML={{__html: html || "No notes yet. Pause the video and add key points or screenshots here."}} />}
    {!editing && status && <small className="notes-status">{status}</small>}
    <style>{`
      .lesson-notes{padding:20px;margin-top:6px}.notes-head{display:flex;justify-content:space-between;gap:16px;align-items:start}.notes-head h3{margin:0 0 5px;font-size:18px}.notes-head p{margin:0;color:var(--text-muted);font-size:13px}.notes-toolbar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:18px 0 8px}.notes-toolbar button,.notes-upload{background:var(--surface-raised);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:6px 10px;font-size:13px;cursor:pointer}.notes-upload input{display:none}.resize-tools{display:flex;gap:4px;align-items:center;margin-left:auto;color:var(--text-muted);font-size:12px}.notes-editor{min-height:220px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;line-height:1.65;outline:none}.notes-editor:focus{border-color:var(--accent)}.notes-editor img,.notes-view img{max-width:100%;height:auto;display:block;margin:12px 0;border-radius:6px}.notes-editor .note-image-selected{outline:3px solid var(--accent);outline-offset:2px}.notes-actions{display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-top:10px}.notes-actions span{margin-right:auto;color:var(--text-muted);font-size:12px}.notes-view{margin-top:16px;line-height:1.65;overflow-wrap:anywhere}.notes-view.empty{color:var(--text-muted);font-style:italic}.notes-view blockquote,.notes-editor blockquote{border-left:3px solid var(--accent);padding-left:12px;color:var(--text-muted)}.notes-status{display:block;margin-top:8px;color:var(--text-muted)}@media(max-width:640px){.lesson-notes{padding:14px}.notes-head{align-items:center}.resize-tools{width:100%;margin-left:0}}
    `}</style>
  </section>;
}
