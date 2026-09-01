import { useEffect, useRef, useState } from "react";
import { useEditor, EditorContent, NodeViewWrapper, ReactNodeViewRenderer } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import { TextStyle } from "@tiptap/extension-text-style";
import { Table } from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableHeader from "@tiptap/extension-table-header";
import TableCell from "@tiptap/extension-table-cell";
import Image from "@tiptap/extension-image";
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { api } from "../api";

const FontSize = Extension.create({
  name: "fontSize",
  addGlobalAttributes() {
    return [{ types: ["textStyle"], attributes: { fontSize: {
      default: null,
      parseHTML: el => el.style.fontSize?.replace("px", "") || null,
      renderHTML: attrs => attrs.fontSize ? { style: `font-size:${attrs.fontSize}px` } : {},
    } } }];
  },
  addCommands() { return { setFontSize: size => ({ chain }) => chain().setMark("textStyle", { fontSize: size }).run(), unsetFontSize: () => ({ chain }) => chain().setMark("textStyle", { fontSize: null }).removeEmptyTextStyle().run() }; },
});

const Indent = Extension.create({
  name: "indent",
  addGlobalAttributes() {
    return [{ types: ["paragraph", "heading"], attributes: { indent: {
      default: 0,
      parseHTML: el => Number(el.dataset.indent || 0),
      renderHTML: attrs => attrs.indent ? { "data-indent": attrs.indent, style: `margin-left:${attrs.indent * 2}rem` } : {},
    } } }];
  },
  addCommands() {
    const set = delta => ({ tr, state, dispatch }) => {
      let changed = false;
      state.doc.nodesBetween(state.selection.from, state.selection.to, (node, pos) => {
        if (["paragraph", "heading"].includes(node.type.name)) {
          const indent = Math.max(0, Math.min(6, (node.attrs.indent || 0) + delta));
          if (indent !== node.attrs.indent) { tr.setNodeMarkup(pos, undefined, { ...node.attrs, indent }); changed = true; }
        }
      });
      if (changed && dispatch) dispatch(tr); return changed;
    };
    return { indent: () => set(1), outdent: () => set(-1) };
  },
  addKeyboardShortcuts() {
    return {
      Tab: () => this.editor.commands.indent() || true,
      "Shift-Tab": () => this.editor.commands.outdent() || true,
      Backspace: () => {
        const { $from, empty } = this.editor.state.selection;
        const atStart = empty && $from.parentOffset === 0;
        const indent = $from.parent?.attrs?.indent || 0;
        return atStart && indent > 0 ? this.editor.commands.outdent() : false;
      },
    };
  },
});

function ImageView({ node, updateAttributes, selected }) {
  const width = node.attrs.width || 100, align = node.attrs.align || "left";
  return <NodeViewWrapper className={`note-image-wrap align-${align} ${selected ? "selected" : ""}`}>
    <figure style={{ width: `${width}%` }}>
      <img src={node.attrs.src} alt={node.attrs.alt || "Note image"} />
      {node.attrs.caption && <figcaption>{node.attrs.caption}</figcaption>}
    </figure>
  </NodeViewWrapper>;
}

const StudyImage = Image.extend({
  addAttributes() {
    return { ...this.parent?.(), width: { default: 100, parseHTML: el => Number(el.dataset.width || 100), renderHTML: a => ({ "data-width": a.width }) }, align: { default: "left", parseHTML: el => el.dataset.align || "left", renderHTML: a => ({ "data-align": a.align }) }, caption: { default: "", parseHTML: el => el.dataset.caption || "", renderHTML: a => a.caption ? ({ "data-caption": a.caption }) : {} } };
  },
  addNodeView() { return ReactNodeViewRenderer(ImageView); },
});

export default function LessonNotes({ lessonId }) {
  const [editing, setEditing] = useState(false), [savedHtml, setSavedHtml] = useState(""), [status, setStatus] = useState("");
  const alignmentSelection = useRef(null);
  const authorizeImages = value => value.replace(/src="(\/api\/notes\/images\/[^"]+)"/g, (_, src) => `src="${api.authenticatedAssetUrl(src)}"`);
  const stripTokens = value => value.replace(/(\/api\/notes\/images\/[a-f0-9-]+\.(?:png|jpe?g|webp|gif))\?t=[^"&]*/g, "$1");

  const editor = useEditor({
    extensions: [StarterKit, Underline, TextStyle, FontSize, Indent, TextAlign.configure({ types: ["heading", "paragraph"] }), Table.configure({ resizable: true }), TableRow, TableHeader, TableCell, StudyImage.configure({ inline: false, allowBase64: false })],
    content: "",
    editable: false,
    editorProps: { attributes: { class: "notes-editor" } },
  });

  useEffect(() => {
    if (!editor) return;
    setEditing(false); setStatus("Loading…"); editor.setEditable(false);
    api.getNote(lessonId).then(n => { const h = authorizeImages(n?.content_html || ""); setSavedHtml(h); editor.commands.setContent(h || "<p></p>"); setStatus(""); }).catch(e => setStatus(e.message));
  }, [lessonId, editor]);

  useEffect(() => { if (editor) editor.setEditable(editing); }, [editing, editor]);

  const uploadImage = async file => {
    if (!file?.type?.startsWith("image/")) return;
    setStatus("Uploading image…");
    try { const r = await api.uploadNoteImage(lessonId, file); editor.chain().focus().setImage({ src: api.authenticatedAssetUrl(r.url), width: 100, align: "left" }).run(); setStatus("Image added — save your note"); }
    catch (e) { setStatus(e.message); }
  };

  useEffect(() => {
    if (!editor) return;
    const el = editor.view.dom;
    const paste = e => { const item = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith("image/")); if (item) { e.preventDefault(); uploadImage(item.getAsFile()); } };
    el.addEventListener("paste", paste); return () => el.removeEventListener("paste", paste);
  }, [editor, lessonId]);

  const save = async () => { setStatus("Saving…"); try { const r = await api.saveNote(lessonId, stripTokens(editor.getHTML())); const h = authorizeImages(r.content_html || ""); setSavedHtml(h); editor.commands.setContent(h || "<p></p>"); setEditing(false); setStatus("Saved"); } catch(e) { setStatus(e.message); } };
  const cancel = () => { editor.commands.setContent(savedHtml || "<p></p>"); setEditing(false); setStatus(""); };
  const exportPdf = () => {
    const win = window.open("about:blank", "_blank");
    if (!win) return setStatus("Allow pop-ups to export PDF");
    const html = editor.getHTML();
    win.document.open();
    win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Lesson notes</title><style>@page{margin:18mm}body{font:15px/1.6 Arial;color:#111}h1{font-size:28px}h2{font-size:23px}h3{font-size:19px}img{max-width:100%;max-height:700px;object-fit:contain}table{border-collapse:collapse;width:100%}td,th{border:1px solid #777;padding:6px}blockquote{border-left:3px solid #555;padding-left:12px;color:#444}</style></head><body><h1>Lesson notes</h1>${html}<script>window.addEventListener('load',async()=>{await Promise.all(Array.from(document.images).map(i=>i.complete?Promise.resolve():new Promise(r=>{i.onload=i.onerror=r})));setTimeout(()=>window.print(),200)})<\/script></body></html>`);
    win.document.close();
    win.opener = null;
  };
  if (!editor) return null;
  const imageSelected = editor.isActive("image");
  const rememberAlignmentSelection = () => {
    const { from, to } = editor.state.selection;
    alignmentSelection.current = { from, to, image: editor.isActive("image") };
  };
  const applyAlignment = align => {
    const remembered = alignmentSelection.current;
    const chain = editor.chain().focus();
    if (remembered?.from != null) chain.setTextSelection({ from: remembered.from, to: remembered.to });
    const isImage = remembered?.image || editor.isActive("image");
    if (isImage) chain.updateAttributes("image", { align }).run();
    else chain.setTextAlign(align).run();
    alignmentSelection.current = null;
  };
  const addImageCaption = () => {
    if (!imageSelected) return;
    const current = editor.getAttributes("image").caption || "";
    const caption = prompt("Image caption", current || "Figure 1 — ");
    if (caption !== null) editor.chain().focus().updateAttributes("image", { caption: caption.trim() }).run();
  };

  return <section className="lesson-notes card">
    <div className="notes-head"><div><h3>My notes</h3><p>Private study notes — or use them to create a document.</p></div><div className="head-actions">{!editing && <button className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>Edit note</button>}<button className="btn btn-secondary btn-sm" onClick={exportPdf}>Export PDF</button></div></div>
    {editing && <div className="notes-toolbar">
      <select aria-label="Text style" onChange={e => { const v=e.target.value; v.startsWith("h") ? editor.chain().focus().setHeading({level:Number(v[1])}).run() : editor.chain().focus().setParagraph().run(); }}><option value="p">Paragraph</option><option value="h1">Heading 1</option><option value="h2">Heading 2</option><option value="h3">Heading 3</option></select>
      <select aria-label="Font size" onChange={e => e.target.value ? editor.chain().focus().setFontSize(e.target.value).run() : editor.chain().focus().unsetFontSize().run()}><option value="">Font size</option><option value="12">Small</option><option value="15">Normal</option><option value="18">Large</option><option value="24">Extra large</option></select>
      <button className={editor.isActive("bold")?"active":""} onClick={() => editor.chain().focus().toggleBold().run()}><b>B</b></button><button onClick={() => editor.chain().focus().toggleItalic().run()}><i>I</i></button><button onClick={() => editor.chain().focus().toggleUnderline().run()}><u>U</u></button>
      <select aria-label="List style" defaultValue="none" onChange={e => { const v=e.target.value; if(v==="bullet") editor.chain().focus().toggleBulletList().run(); if(v==="numbered") editor.chain().focus().toggleOrderedList().run(); e.target.value="none"; }}><option value="none">List</option><option value="bullet">Bullet list</option><option value="numbered">Numbered list</option></select>
      <button className={editor.isActive("blockquote")?"active":""} onClick={() => editor.chain().focus().toggleBlockquote().run()}>Quote</button>
      <select aria-label="Alignment" value={imageSelected ? (editor.getAttributes("image").align || "left") : (editor.isActive({textAlign:"center"})?"center":editor.isActive({textAlign:"right"})?"right":"left")} onPointerDown={rememberAlignmentSelection} onFocus={rememberAlignmentSelection} onChange={e => applyAlignment(e.target.value)}><option value="left">Align left</option><option value="center">Align center</option><option value="right">Align right</option></select>
      {imageSelected && <span className="image-tools"><select aria-label="Image size" value={editor.getAttributes("image").width || 100} onChange={e => editor.chain().focus().updateAttributes("image",{width:Number(e.target.value)}).run()}><option value="25">Image 25%</option><option value="50">Image 50%</option><option value="75">Image 75%</option><option value="100">Image 100%</option></select><button onClick={addImageCaption}>Add caption</button></span>}
    </div>}
    <EditorContent editor={editor} className={!editing && !savedHtml ? "notes-empty" : ""}/>
    {!editing && !savedHtml && <p className="empty-message">No notes yet. Pause the video and add key points or screenshots here.</p>}
    {editing && <div className="notes-actions"><span>{status}</span><button className="btn btn-ghost" onClick={cancel}>Cancel</button><button className="btn btn-primary" onClick={save}>Save note</button></div>}{!editing && status && <small>{status}</small>}
    <style>{`
      .lesson-notes{padding:20px;margin-top:8px}.notes-head{display:flex;justify-content:space-between;gap:16px}.notes-head h3{margin:0 0 5px}.notes-head p,.empty-message{margin:0;color:var(--text-muted);font-size:13px}.head-actions{display:flex;gap:8px;flex-shrink:0}.notes-toolbar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:18px 0 8px}.notes-toolbar button,.notes-toolbar select,.notes-upload{background:var(--surface-raised);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:6px 9px;font-size:12px;cursor:pointer}.notes-toolbar button.active{border-color:var(--accent);color:var(--accent)}.notes-upload input{display:none}.image-tools{display:flex;gap:4px;align-items:center;flex-wrap:wrap}.notes-editor{min-height:220px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;line-height:1.65;outline:none}.notes-editor:focus{border-color:var(--accent)}.notes-empty .notes-editor{display:none}.empty-message{margin-top:16px;font-style:italic}.notes-editor img{width:100%;max-width:100%;max-height:min(520px,65vh);height:auto;object-fit:contain;border-radius:6px}.note-image-wrap{display:flex;margin:12px 0}.note-image-wrap figure{margin:0}.note-image-wrap figcaption{text-align:center;color:var(--text-muted);font-size:12px;font-style:italic;margin-top:6px}.note-image-wrap.align-left{justify-content:flex-start}.note-image-wrap.align-center{justify-content:center}.note-image-wrap.align-right{justify-content:flex-end}.note-image-wrap.selected img{outline:3px solid var(--accent)}.notes-editor table{border-collapse:collapse;width:100%;margin:12px 0}.notes-editor td,.notes-editor th{border:1px solid var(--border-strong);padding:7px;min-width:60px}.notes-editor th{background:var(--surface-raised)}.notes-editor blockquote{border-left:3px solid var(--accent);padding-left:12px}.notes-actions{display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-top:10px}.notes-actions span{margin-right:auto;color:var(--text-muted);font-size:12px}@media(max-width:640px){.lesson-notes{padding:14px}.notes-head{flex-direction:column}.head-actions{align-self:flex-end}}
    `}</style>
  </section>;
}
