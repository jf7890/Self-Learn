import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { IconChevronLeft, IconUsers, IconSettings, IconLibrary, IconRefresh, IconCheckCircle, IconX, IconStar, IconEyeOff, IconBell, IconImage, IconMail, IconActivity, IconDownload } from "../icons.jsx";
import { useBranding } from "../BrandingContext.jsx";

function formatLastLogin(lastLoginAt) {
  if (!lastLoginAt) return "Never";
  const then = new Date(lastLoginAt.replace(" ", "T") + "Z").getTime();
  const diffMin = Math.max(0, Math.floor((Date.now() - then) / 60000));
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return new Date(then).toLocaleDateString();
}

const TABS = [
  { id: "members", label: "Members", icon: IconUsers },
  { id: "courses", label: "Courses", icon: IconLibrary },
  { id: "branding", label: "Branding", icon: IconImage },
  { id: "settings", label: "Sign-in settings", icon: IconSettings },
  { id: "notifications", label: "Notifications", icon: IconBell },
  { id: "email", label: "Email", icon: IconMail },
  { id: "activity", label: "Activity", icon: IconActivity },
  { id: "library", label: "Library", icon: IconRefresh },
];

export default function AdminDashboard() {
  const [tab, setTab] = useState("members");

  return (
    <div className="ct-admin">
      <div className="ct-admin-topbar">
        <Link to="/" className="ct-back"><IconChevronLeft width={15} height={15} /> Courses</Link>
        <h2>Admin dashboard</h2>
      </div>

      <div className="ct-admin-tabs">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
            <Icon width={14} height={14} /> {label}
          </button>
        ))}
      </div>

      {tab === "members" && <MembersPanel />}
      {tab === "courses" && <CoursesPanel />}
      {tab === "branding" && <BrandingPanel />}
      {tab === "settings" && <SettingsPanel />}
      {tab === "notifications" && <NotificationsPanel />}
      {tab === "email" && <EmailPanel />}
      {tab === "activity" && <ActivityPanel />}
      {tab === "library" && <LibraryPanel />}

      <style>{`
        .ct-admin { max-width: 880px; margin: 0 auto; padding: var(--space-5); }
        .ct-admin-topbar { display: flex; align-items: center; gap: var(--space-4); margin-bottom: var(--space-5); }
        .ct-back { display: flex; align-items: center; gap: 2px; font-size: var(--text-sm); color: var(--text-muted); text-decoration: none; flex-shrink: 0; }
        .ct-back:hover { color: var(--text); }
        .ct-admin-topbar h2 { font-size: var(--text-lg); }
        .ct-admin-tabs {
          display: flex;
          gap: var(--space-1);
          border-bottom: 1px solid var(--border);
          margin-bottom: var(--space-5);
          flex-wrap: wrap;
          overflow: visible;
        }
        .ct-admin-tabs::-webkit-scrollbar { display: none; }
        .ct-admin-tabs button {
          display: flex;
          align-items: center;
          gap: 6px;
          background: transparent;
          border: none;
          color: var(--text-muted);
          padding: var(--space-3) var(--space-2);
          margin-right: var(--space-2);
          font-size: var(--text-sm);
          font-weight: 500;
          border-bottom: 2px solid transparent;
          transition: color var(--dur-fast) var(--ease);
          flex-shrink: 0;
          white-space: nowrap;
          scroll-snap-align: start;
        }
        .ct-admin-tabs button:hover { color: var(--text); }
        .ct-admin-tabs button.active { color: var(--text); border-bottom-color: var(--accent); }

        @media (max-width: 640px) {
          .ct-admin { padding: var(--space-4) 0; }
          .ct-admin-topbar { padding: 0 var(--space-4); }
          .ct-admin-tabs {
            padding: 0 var(--space-4);
            gap: 0 var(--space-2);
          }
          .ct-admin-tabs button { margin-right: var(--space-3); padding: var(--space-3) var(--space-1); }
          .ct-panel, .ct-table-card { margin: 0 var(--space-4); }
        }
      `}</style>
    </div>
  );
}

function MembersPanel() {
  const [users, setUsers] = useState(null);
  const [smtpEnabled, setSmtpEnabled] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [sendInvite, setSendInvite] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);

  const load = () => api.listUsers().then(setUsers).catch((e) => setError(e.message));
  useEffect(() => {
    load();
    api.getEmailSettings().then((s) => setSmtpEnabled(s.smtp_enabled)).catch(() => {});
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      await api.createUser(username, password, isAdmin, email, sendInvite);
      setUsername(""); setPassword(""); setEmail(""); setSendInvite(false); setIsAdmin(false); setShowCreate(false);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Remove this member? Their progress will be deleted too.")) return;
    await api.deleteUser(id).catch((e) => setError(e.message));
    load();
  };

  if (!users) return <div className="state-screen"><span className="spinner" /></div>;

  return (
    <div className="ct-panel">
      {error && <p className="alert alert-danger">{error}</p>}

      <div className="card ct-table-card">
        <table className="ct-table">
          <thead>
            <tr><th>Username</th><th>Role</th><th>Sign-in</th><th>Last login</th><th></th></tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>
                  {u.username}
                  {u.pending_invite && <span className="badge badge-neutral ct-invite-badge">Pending invite</span>}
                </td>
                <td>
                  <span className={`badge ${u.is_admin ? "badge-accent" : "badge-neutral"}`}>
                    {u.is_admin ? "Admin" : "Member"}
                  </span>
                </td>
                <td className="ct-muted-cell">{u.jellyfin_user_id ? "Jellyfin" : "Local"}</td>
                <td className="ct-muted-cell">{formatLastLogin(u.last_login_at)}</td>
                <td className="ct-table-actions">
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(u.id)}>Remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!showCreate ? (
        <button className="btn btn-secondary" onClick={() => setShowCreate(true)} style={{ alignSelf: "flex-start" }}>
          Add member
        </button>
      ) : (
        <form className="card ct-inline-form" onSubmit={handleCreate}>
          <div className="field">
            <label>Username</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          <div className="field">
            <label>Email {sendInvite ? "" : "(optional)"}</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required={sendInvite} />
          </div>

          {smtpEnabled && (
            <label className="ct-checkbox">
              <input type="checkbox" checked={sendInvite} onChange={(e) => setSendInvite(e.target.checked)} />
              Email an invite link instead of setting a password
            </label>
          )}

          {!sendInvite && (
            <div className="field">
              <label>Password</label>
              <input type="password" placeholder="8+ characters" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} required={!sendInvite} />
            </div>
          )}

          <label className="ct-checkbox">
            <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
            Admin
          </label>
          <div className="ct-inline-form-actions">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowCreate(false)}>Cancel</button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={creating}>
              {creating ? "Creating…" : sendInvite ? "Create & send invite" : "Create member"}
            </button>
          </div>
        </form>
      )}

      <style>{`
        .ct-panel { display: flex; flex-direction: column; gap: var(--space-4); }
        .ct-table-card { overflow: hidden; }
        .ct-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
        .ct-table th {
          text-align: left;
          color: var(--text-muted);
          font-weight: 500;
          font-size: var(--text-xs);
          text-transform: uppercase;
          letter-spacing: 0.04em;
          padding: var(--space-3) var(--space-4);
          border-bottom: 1px solid var(--border);
          background: var(--surface-raised);
        }
        .ct-table td { padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--border); }
        .ct-table tr:last-child td { border-bottom: none; }
        .ct-invite-badge { margin-left: 8px; font-size: 10px; }
        .ct-muted-cell { color: var(--text-muted); }
        .ct-table-actions { text-align: right; }
        .ct-inline-form {
          display: flex;
          flex-direction: column;
          gap: var(--space-3);
          padding: var(--space-4);
          max-width: 340px;
        }
        .ct-checkbox { display: flex; align-items: center; gap: 8px; font-size: var(--text-sm); color: var(--text-muted); }
        .ct-inline-form-actions { display: flex; gap: var(--space-2); justify-content: flex-end; margin-top: 2px; }
      `}</style>
    </div>
  );
}

function CoursesPanel() {
  const [courses, setCourses] = useState(null);
  const [error, setError] = useState(null);
  const [savingId, setSavingId] = useState(null);
  const [drafts, setDrafts] = useState({}); // courseId -> draft tags string, for uncommitted edits

  const load = () => api.getAdminCourses().then(setCourses).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const tagsFor = (course) => drafts[course.id] ?? course.tags ?? "";

  const save = async (course, overrides = {}) => {
    setSavingId(course.id);
    setError(null);
    try {
      const tags = overrides.tags ?? tagsFor(course);
      const isFeatured = overrides.is_featured ?? !!course.is_featured;
      const isHidden = overrides.is_hidden ?? !!course.is_hidden;
      await api.updateAdminCourse(course.id, tags, isFeatured, isHidden);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSavingId(null);
    }
  };

  if (!courses) return <div className="state-screen"><span className="spinner" /></div>;

  return (
    <div className="ct-panel">
      {error && <p className="alert alert-danger">{error}</p>}
      <p className="ct-settings-hint">
        Feature a course to show it in a highlighted row on the home screen, or hide one to keep it out
        of everyone's library entirely (still accessible via direct link, and manageable here any time).
      </p>

      <div className="card ct-table-card">
        <table className="ct-table ct-courses-table">
          <thead>
            <tr><th>Course</th><th>Tags</th><th>Lessons</th><th>Featured</th><th>Hidden</th><th>Open</th></tr>
          </thead>
          <tbody>
            {courses.map((c) => (
              <tr key={c.id} className={c.is_hidden ? "ct-row-hidden" : ""}>
                <td className="ct-course-title-cell"><Link to={`/course/${c.id}`}>{c.title}</Link></td>
                <td>
                  <input
                    className="ct-tags-input"
                    placeholder="e.g. marketing, ai"
                    value={tagsFor(c)}
                    onChange={(e) => setDrafts((d) => ({ ...d, [c.id]: e.target.value }))}
                    onBlur={() => { if (drafts[c.id] !== undefined) save(c); }}
                    onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); }}
                  />
                </td>
                <td className="ct-muted-cell">{c.lesson_count}</td>
                <td>
                  <button
                    className={`btn btn-sm ${c.is_featured ? "btn-primary" : "btn-secondary"}`}
                    disabled={savingId === c.id}
                    onClick={() => save(c, { is_featured: !c.is_featured })}
                  >
                    <IconStar width={13} height={13} /> {c.is_featured ? "Featured" : "Feature"}
                  </button>
                </td>
                <td>
                  <button
                    className={`btn btn-sm ${c.is_hidden ? "btn-danger" : "btn-secondary"}`}
                    disabled={savingId === c.id}
                    onClick={() => save(c, { is_hidden: !c.is_hidden })}
                  >
                    <IconEyeOff width={13} height={13} /> {c.is_hidden ? "Hidden" : "Hide"}
                  </button>
                </td>
                <td><Link className="btn btn-primary btn-sm ct-view-course" to={`/course/${c.id}`}>View course</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <style>{`
        .ct-courses-table th:nth-child(1) { width: 32%; }
        .ct-courses-table th:nth-child(2) { width: 28%; }
        .ct-course-title-cell { font-weight: 500; }
        .ct-course-title-cell a { color: var(--text); text-decoration: none; }
        .ct-course-title-cell a:hover { color: var(--accent); text-decoration: underline; }
        .ct-view-course { white-space: nowrap; text-decoration: none; }
        .ct-row-hidden { opacity: 0.55; }
        .ct-tags-input {
          width: 100%;
          background: var(--surface-raised);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          padding: 6px 9px;
          color: var(--text);
          font-size: var(--text-xs);
          font-family: var(--font-body);
        }
        .ct-tags-input:focus { outline: none; border-color: var(--accent-dim); }
      `}</style>
    </div>
  );
}

function LibraryPanel() {
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const rescan = async () => {
    setScanning(true); setError(null); setResult(null);
    try {
      const summary = await api.rescan();
      setResult(summary);
    } catch (e) {
      setError(e.message);
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="ct-panel">
      {error && <p className="alert alert-danger">{error}</p>}
      <div className="card ct-library-card">
        <p className="ct-settings-hint">
          Walks the courses/ directory and updates the library. Safe to run any time — new folders get
          added, existing ones get refreshed, nothing is duplicated.
        </p>
        <button className="btn btn-primary" onClick={rescan} disabled={scanning} style={{ alignSelf: "flex-start" }}>
          <IconRefresh width={14} height={14} className={scanning ? "ct-spin" : ""} />
          {scanning ? "Scanning…" : "Rescan library"}
        </button>
        {result && (
          <p className="alert alert-success">
            <IconCheckCircle width={15} height={15} />
            Found {result.courses} course{result.courses !== 1 ? "s" : ""}, {result.sections} section{result.sections !== 1 ? "s" : ""},{" "}
            {result.lessons} lesson{result.lessons !== 1 ? "s" : ""}, {result.attachments} attachment{result.attachments !== 1 ? "s" : ""}.
            {(result.removed_courses + result.removed_sections + result.removed_lessons + result.removed_attachments) > 0 && (
              <> Removed {result.removed_courses} course{result.removed_courses !== 1 ? "s" : ""}, {result.removed_lessons} lesson{result.removed_lessons !== 1 ? "s" : ""},{" "}
              {result.removed_attachments} attachment{result.removed_attachments !== 1 ? "s" : ""} no longer on disk.</>
            )}
          </p>
        )}
        {result?.cleanup_skipped && (
          <p className="alert alert-danger">
            <IconX width={15} height={15} />
            No courses were found on disk at all, but the library isn't empty — this usually means a mount
            or volume problem. Nothing was removed from the library as a precaution. Check that courses/
            is actually mounted before rescanning again.
          </p>
        )}
      </div>

      <div className="card ct-library-card">
        <p className="ct-settings-hint">
          Downloads a snapshot of everything uLearn stores itself — accounts, progress, comments,
          settings, and branding assets — as a zip. Doesn't include course files, since those live in
          your own storage and are backed up separately from this.
        </p>
        <a href={api.backupUrl()} download className="btn btn-secondary">
          <IconDownload width={14} height={14} /> Download backup
        </a>
      </div>

      <style>{`
        .ct-library-card { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); align-items: flex-start; }
        .ct-settings-hint { font-size: var(--text-sm); color: var(--text-muted); line-height: 1.55; margin: 0; }
        .ct-spin { animation: ct-spin 0.8s linear infinite; }
      `}</style>
    </div>
  );
}

function SettingsPanel() {
  const [settings, setSettings] = useState(null);
  const [testStatus, setTestStatus] = useState(null); // null | "testing" | "ok" | "fail"
  const [testMessage, setTestMessage] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.getAdminSettings().then(setSettings).catch((e) => setError(e.message)); }, []);

  const save = async () => {
    setSaving(true); setError(null); setSaved(false);
    try {
      await api.updateAdminSettings(settings.jellyfin_auth_enabled, settings.jellyfin_url);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setTestStatus("testing"); setTestMessage(""); setError(null);
    try {
      const result = await api.testJellyfin(settings.jellyfin_url);
      setTestStatus("ok");
      setTestMessage(`Connected to ${result.server_name} (Jellyfin ${result.version})`);
    } catch (e) {
      setTestStatus("fail");
      setTestMessage(e.message);
    }
  };

  if (!settings) return <div className="state-screen"><span className="spinner" /></div>;

  return (
    <div className="ct-panel">
      {error && <p className="alert alert-danger">{error}</p>}

      <div className="card ct-settings-card">
        <div className="ct-settings-row">
          <div>
            <p className="ct-settings-label">Jellyfin sign-in</p>
            <p className="ct-settings-hint">Lets members sign in with their Jellyfin username and password. Adds a button underneath the normal login form.</p>
          </div>
          <label className="ct-toggle">
            <input
              type="checkbox"
              checked={settings.jellyfin_auth_enabled}
              onChange={(e) => setSettings({ ...settings, jellyfin_auth_enabled: e.target.checked })}
            />
            <span className="ct-toggle-track"><span className="ct-toggle-thumb" /></span>
          </label>
        </div>

        {settings.jellyfin_auth_enabled && (
          <div className="field ct-settings-field">
            <label>Jellyfin server URL</label>
            <input
              placeholder="http://jellyfin.example.com:8096"
              value={settings.jellyfin_url}
              onChange={(e) => { setSettings({ ...settings, jellyfin_url: e.target.value }); setTestStatus(null); }}
            />
            <div className="ct-inline-form-actions">
              <button className="btn btn-secondary btn-sm" onClick={testConnection} type="button" disabled={testStatus === "testing"}>
                {testStatus === "testing" ? "Testing…" : "Test connection"}
              </button>
            </div>
            {testStatus === "ok" && (
              <p className="alert alert-success"><IconCheckCircle width={14} height={14} /> Test successful — {testMessage}</p>
            )}
            {testStatus === "fail" && (
              <p className="alert alert-danger"><IconX width={14} height={14} /> Test failed — {testMessage}</p>
            )}
          </div>
        )}

        <div className="ct-settings-footer">
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </button>
          {saved && <span className="ct-saved-tick"><IconCheckCircle width={14} height={14} /> Saved</span>}
        </div>
      </div>

      <style>{`
        .ct-settings-card { padding: var(--space-4); }
        .ct-settings-row { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-5); padding-bottom: var(--space-4); border-bottom: 1px solid var(--border); }
        .ct-settings-label { font-size: var(--text-base); font-weight: 600; margin: 0 0 4px; }
        .ct-settings-hint { font-size: var(--text-sm); color: var(--text-muted); margin: 0; max-width: 420px; line-height: 1.55; }
        .ct-toggle { position: relative; flex-shrink: 0; }
        .ct-toggle input { position: absolute; opacity: 0; width: 40px; height: 22px; margin: 0; cursor: pointer; }
        .ct-toggle-track { display: block; width: 40px; height: 22px; background: var(--surface-raised); border: 1px solid var(--border); border-radius: 12px; transition: background var(--dur) var(--ease); }
        .ct-toggle-thumb { display: block; width: 16px; height: 16px; background: var(--text-muted); border-radius: 50%; margin: 2px; transition: transform var(--dur) var(--ease), background var(--dur) var(--ease); }
        .ct-toggle input:checked + .ct-toggle-track { background: var(--accent-dim); }
        .ct-toggle input:checked + .ct-toggle-track .ct-toggle-thumb { transform: translateX(18px); background: var(--accent); }
        .ct-settings-field { padding: var(--space-4) 0; border-bottom: 1px solid var(--border); }
        .ct-settings-field input { max-width: 360px; }
        .ct-inline-form-actions { display: flex; gap: var(--space-2); justify-content: flex-end; margin-top: var(--space-2); }
        .ct-settings-footer { display: flex; align-items: center; gap: var(--space-3); padding-top: var(--space-4); }
        .ct-saved-tick { display: flex; align-items: center; gap: 5px; font-size: var(--text-sm); color: var(--complete); }
      `}</style>
    </div>
  );
}

function NotificationsPanel() {
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testStatus, setTestStatus] = useState(null); // null | "testing" | "ok" | "fail"
  const [testMessage, setTestMessage] = useState("");

  useEffect(() => {
    api.getNotificationSettings().then(setSettings).catch((e) => setError(e.message));
  }, []);

  const update = (patch) => setSettings((s) => ({ ...s, ...patch }));

  const save = async () => {
    setSaving(true); setError(null); setSaved(false);
    try {
      await api.updateNotificationSettings(settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTestStatus("testing"); setTestMessage("");
    try {
      await api.testNotification();
      setTestStatus("ok");
      setTestMessage("Test message sent — check your channel(s).");
    } catch (e) {
      setTestStatus("fail");
      setTestMessage(e.message);
    }
  };

  if (!settings) return <div className="state-screen"><span className="spinner" /></div>;

  return (
    <div className="ct-panel">
      {error && <p className="alert alert-danger">{error}</p>}

      <div className="card ct-settings-card">
        <div className="ct-settings-row">
          <div>
            <p className="ct-settings-label">Discord</p>
            <p className="ct-settings-hint">Posts to a Discord channel via webhook when a course is completed or added.</p>
          </div>
          <label className="ct-toggle">
            <input type="checkbox" checked={settings.discord_enabled} onChange={(e) => update({ discord_enabled: e.target.checked })} />
            <span className="ct-toggle-track"><span className="ct-toggle-thumb" /></span>
          </label>
        </div>
        {settings.discord_enabled && (
          <div className="field ct-settings-field">
            <label>Webhook URL</label>
            <input
              placeholder="https://discord.com/api/webhooks/..."
              value={settings.discord_webhook_url}
              onChange={(e) => update({ discord_webhook_url: e.target.value })}
            />
          </div>
        )}

        <div className="ct-settings-row">
          <div>
            <p className="ct-settings-label">Telegram</p>
            <p className="ct-settings-hint">Sends via a Telegram bot when a course is completed or added.</p>
          </div>
          <label className="ct-toggle">
            <input type="checkbox" checked={settings.telegram_enabled} onChange={(e) => update({ telegram_enabled: e.target.checked })} />
            <span className="ct-toggle-track"><span className="ct-toggle-thumb" /></span>
          </label>
        </div>
        {settings.telegram_enabled && (
          <>
            <div className="field ct-settings-field">
              <label>Bot token</label>
              <input
                placeholder="123456:ABC-DEF..."
                value={settings.telegram_bot_token}
                onChange={(e) => update({ telegram_bot_token: e.target.value })}
              />
            </div>
            <div className="field ct-settings-field">
              <label>Chat ID</label>
              <input
                placeholder="-1001234567890"
                value={settings.telegram_chat_id}
                onChange={(e) => update({ telegram_chat_id: e.target.value })}
              />
            </div>
          </>
        )}

        <div className="field ct-settings-field">
          <label>Message when a course is completed</label>
          <textarea
            rows={2}
            value={settings.template_course_completed}
            onChange={(e) => update({ template_course_completed: e.target.value })}
          />
          <p className="ct-template-hint">Placeholders: {"{username}"}, {"{course_title}"}</p>
        </div>

        <div className="field ct-settings-field">
          <label>Message when a new course is added</label>
          <textarea
            rows={2}
            value={settings.template_course_added}
            onChange={(e) => update({ template_course_added: e.target.value })}
          />
          <p className="ct-template-hint">Placeholders: {"{course_title}"}, {"{lesson_count}"}</p>
        </div>

        <div className="ct-settings-footer">
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </button>
          <button className="btn btn-secondary" onClick={test} disabled={testStatus === "testing"} type="button">
            {testStatus === "testing" ? "Sending…" : "Send test notification"}
          </button>
          {saved && <span className="ct-saved-tick"><IconCheckCircle width={14} height={14} /> Saved</span>}
        </div>

        {testStatus === "ok" && <p className="alert alert-success"><IconCheckCircle width={14} height={14} /> {testMessage}</p>}
        {testStatus === "fail" && <p className="alert alert-danger"><IconX width={14} height={14} /> Test failed — {testMessage}</p>}
      </div>

      <style>{`
        .ct-settings-card { padding: var(--space-4); display: flex; flex-direction: column; }
        .ct-settings-row { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-5); padding: var(--space-4) 0; border-bottom: 1px solid var(--border); }
        .ct-settings-row:first-child { padding-top: 0; }
        .ct-settings-label { font-size: var(--text-base); font-weight: 600; margin: 0 0 4px; }
        .ct-settings-hint { font-size: var(--text-sm); color: var(--text-muted); margin: 0; max-width: 420px; line-height: 1.55; }
        .ct-toggle { position: relative; flex-shrink: 0; }
        .ct-toggle input { position: absolute; opacity: 0; width: 40px; height: 22px; margin: 0; cursor: pointer; }
        .ct-toggle-track { display: block; width: 40px; height: 22px; background: var(--surface-raised); border: 1px solid var(--border); border-radius: 12px; transition: background var(--dur) var(--ease); }
        .ct-toggle-thumb { display: block; width: 16px; height: 16px; background: var(--text-muted); border-radius: 50%; margin: 2px; transition: transform var(--dur) var(--ease), background var(--dur) var(--ease); }
        .ct-toggle input:checked + .ct-toggle-track { background: var(--accent-dim); }
        .ct-toggle input:checked + .ct-toggle-track .ct-toggle-thumb { transform: translateX(18px); background: var(--accent); }
        .ct-settings-field { padding: var(--space-4) 0; border-bottom: 1px solid var(--border); }
        .ct-settings-field input, .ct-settings-field textarea { max-width: 420px; width: 100%; font-family: var(--font-body); }
        .ct-settings-footer { display: flex; align-items: center; gap: var(--space-3); padding-top: var(--space-4); }
        .ct-saved-tick { display: flex; align-items: center; gap: 5px; font-size: var(--text-sm); color: var(--complete); }
        .ct-template-hint { font-size: var(--text-xs); color: var(--text-faint); margin: 4px 0 0; }
      `}</style>
    </div>
  );
}

function BrandingPanel() {
  const { site_name, accent_color, logo_url, favicon_url, refresh } = useBranding();
  const [name, setName] = useState(site_name);
  const [color, setColor] = useState(accent_color);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadingFavicon, setUploadingFavicon] = useState(false);

  // keep local draft in sync once branding actually loads (avoids
  // overwriting user's in-progress edits on unrelated re-renders)
  useEffect(() => { setName(site_name); }, [site_name]);
  useEffect(() => { setColor(accent_color); }, [accent_color]);

  const save = async () => {
    setSaving(true); setError(null); setSaved(false);
    try {
      await api.updateBranding(name, color);
      refresh();
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setError(null);
    try {
      await api.uploadBrandingLogo(file);
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const removeLogo = async () => {
    setError(null);
    try {
      await api.deleteBrandingLogo();
      refresh();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleFaviconFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingFavicon(true); setError(null);
    try {
      await api.uploadBrandingFavicon(file);
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploadingFavicon(false);
      e.target.value = "";
    }
  };

  const removeFavicon = async () => {
    setError(null);
    try {
      await api.deleteBrandingFavicon();
      refresh();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="ct-panel">
      {error && <p className="alert alert-danger">{error}</p>}

      <div className="card ct-settings-card">
        <div className="field ct-settings-field ct-first-field">
          <label>Site name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="uLearn" />
        </div>

        <div className="ct-settings-field">
          <label className="ct-field-label">Logo</label>
          <div className="ct-logo-row">
            <div className="ct-logo-preview">
              {logo_url ? <img src={`/api${logo_url}`} alt="Current logo" /> : <span className="ct-logo-placeholder">No logo</span>}
            </div>
            <div className="ct-logo-actions">
              <label className="btn btn-secondary btn-sm ct-upload-btn">
                {uploading ? "Uploading…" : "Upload logo"}
                <input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" onChange={handleFile} hidden />
              </label>
              {logo_url && (
                <button className="btn btn-ghost btn-sm" onClick={removeLogo} type="button">Remove</button>
              )}
            </div>
          </div>
          <p className="ct-settings-hint">PNG, JPEG, SVG, or WebP, up to 2MB. Falls back to the default mark if none is set.</p>
        </div>

        <div className="ct-settings-field">
          <label className="ct-field-label">Favicon</label>
          <div className="ct-logo-row">
            <div className="ct-logo-preview ct-favicon-preview">
              {favicon_url ? <img src={`/api${favicon_url}`} alt="Current favicon" /> : <span className="ct-logo-placeholder">Default</span>}
            </div>
            <div className="ct-logo-actions">
              <label className="btn btn-secondary btn-sm ct-upload-btn">
                {uploadingFavicon ? "Uploading…" : "Upload favicon"}
                <input type="file" accept="image/png,image/svg+xml,image/webp,image/x-icon,.ico" onChange={handleFaviconFile} hidden />
              </label>
              {favicon_url && (
                <button className="btn btn-ghost btn-sm" onClick={removeFavicon} type="button">Remove</button>
              )}
            </div>
          </div>
          <p className="ct-settings-hint">The icon shown in browser tabs. PNG, SVG, WebP, or ICO, up to 2MB.</p>
        </div>

        <div className="ct-settings-field">
          <label className="ct-field-label">Accent color</label>
          <div className="ct-color-row">
            <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="ct-color-swatch" />
            <input
              value={color}
              onChange={(e) => setColor(e.target.value)}
              placeholder="#e8a33d"
              className="ct-color-hex"
            />
          </div>
          <p className="ct-settings-hint">Used for buttons, progress bars, and highlights throughout the app.</p>
        </div>

        <div className="ct-settings-footer">
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save branding"}
          </button>
          {saved && <span className="ct-saved-tick"><IconCheckCircle width={14} height={14} /> Saved</span>}
        </div>
      </div>

      <style>{`
        .ct-settings-card { padding: var(--space-4); display: flex; flex-direction: column; }
        .ct-first-field { padding-top: 0; }
        .ct-settings-field { padding: var(--space-4) 0; border-bottom: 1px solid var(--border); }
        .ct-settings-field input:not([type=color]):not([type=file]) { max-width: 340px; width: 100%; }
        .ct-field-label { display: block; font-size: var(--text-sm); font-weight: 500; color: var(--text-muted); margin-bottom: var(--space-2); }
        .ct-settings-hint { font-size: var(--text-sm); color: var(--text-muted); margin: var(--space-2) 0 0; line-height: 1.5; }
        .ct-logo-row { display: flex; align-items: center; gap: var(--space-3); }
        .ct-logo-preview {
          width: 64px; height: 64px;
          background: var(--surface-raised);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          display: flex; align-items: center; justify-content: center;
          overflow: hidden;
          flex-shrink: 0;
        }
        .ct-logo-preview img { max-width: 100%; max-height: 100%; object-fit: contain; }
        .ct-favicon-preview { width: 40px; height: 40px; }
        .ct-logo-placeholder { font-size: 10px; color: var(--text-faint); }
        .ct-logo-actions { display: flex; gap: var(--space-2); align-items: center; }
        .ct-upload-btn { cursor: pointer; }
        .ct-color-row { display: flex; align-items: center; gap: var(--space-2); }
        .ct-color-swatch {
          width: 40px; height: 36px;
          padding: 2px;
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          background: var(--surface-raised);
          cursor: pointer;
        }
        .ct-color-hex {
          font-family: var(--font-body);
          font-size: var(--text-sm);
          color: var(--text);
          background: var(--surface-raised);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          padding: 8px 10px;
          width: 120px;
        }
        .ct-settings-footer { display: flex; align-items: center; gap: var(--space-3); padding-top: var(--space-4); }
        .ct-saved-tick { display: flex; align-items: center; gap: 5px; font-size: var(--text-sm); color: var(--complete); }
      `}</style>
    </div>
  );
}

function EmailPanel() {
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testAddress, setTestAddress] = useState("");
  const [testStatus, setTestStatus] = useState(null); // null | "testing" | "ok" | "fail"
  const [testMessage, setTestMessage] = useState("");

  useEffect(() => {
    api.getEmailSettings().then(setSettings).catch((e) => setError(e.message));
  }, []);

  const update = (patch) => setSettings((s) => ({ ...s, ...patch }));

  const save = async () => {
    setSaving(true); setError(null); setSaved(false);
    try {
      await api.updateEmailSettings(settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    if (!testAddress.trim()) return;
    setTestStatus("testing"); setTestMessage("");
    try {
      await api.testEmailSettings(testAddress.trim());
      setTestStatus("ok");
      setTestMessage(`Sent to ${testAddress.trim()} — check the inbox.`);
    } catch (e) {
      setTestStatus("fail");
      setTestMessage(e.message);
    }
  };

  if (!settings) return <div className="state-screen"><span className="spinner" /></div>;

  return (
    <div className="ct-panel">
      {error && <p className="alert alert-danger">{error}</p>}

      <div className="card ct-settings-card">
        <div className="ct-settings-row">
          <div>
            <p className="ct-settings-label">Email (SMTP)</p>
            <p className="ct-settings-hint">Powers invite emails and self-service password resets. Off by default.</p>
          </div>
          <label className="ct-toggle">
            <input type="checkbox" checked={settings.smtp_enabled} onChange={(e) => update({ smtp_enabled: e.target.checked })} />
            <span className="ct-toggle-track"><span className="ct-toggle-thumb" /></span>
          </label>
        </div>

        {settings.smtp_enabled && (
          <>
            <div className="ct-field-row">
              <div className="field ct-settings-field">
                <label>SMTP host</label>
                <input placeholder="smtp.gmail.com" value={settings.smtp_host} onChange={(e) => update({ smtp_host: e.target.value })} />
              </div>
              <div className="field ct-settings-field ct-port-field">
                <label>Port</label>
                <input value={settings.smtp_port} onChange={(e) => update({ smtp_port: e.target.value })} />
              </div>
            </div>
            <div className="field ct-settings-field">
              <label>Username</label>
              <input value={settings.smtp_username} onChange={(e) => update({ smtp_username: e.target.value })} />
            </div>
            <div className="field ct-settings-field">
              <label>Password</label>
              <input type="password" value={settings.smtp_password} onChange={(e) => update({ smtp_password: e.target.value })} />
            </div>
            <div className="ct-field-row">
              <div className="field ct-settings-field">
                <label>From address</label>
                <input placeholder="noreply@example.com" value={settings.smtp_from_address} onChange={(e) => update({ smtp_from_address: e.target.value })} />
              </div>
              <div className="field ct-settings-field">
                <label>From name</label>
                <input value={settings.smtp_from_name} onChange={(e) => update({ smtp_from_name: e.target.value })} />
              </div>
            </div>
            <label className="ct-checkbox ct-settings-field">
              <input type="checkbox" checked={settings.smtp_use_tls} onChange={(e) => update({ smtp_use_tls: e.target.checked })} />
              Use STARTTLS
            </label>
            <div className="field ct-settings-field">
              <label>Site URL</label>
              <input placeholder="https://learn.example.com" value={settings.site_url} onChange={(e) => update({ site_url: e.target.value })} />
              <p className="ct-template-hint">Used to build the links inside invite and reset emails.</p>
            </div>

            <div className="field ct-settings-field">
              <label>Invite email</label>
              <textarea rows={4} value={settings.template_invite} onChange={(e) => update({ template_invite: e.target.value })} />
              <p className="ct-template-hint">Placeholders: {"{username}"}, {"{site_name}"}, {"{link}"}</p>
            </div>
            <div className="field ct-settings-field">
              <label>Password reset email</label>
              <textarea rows={4} value={settings.template_password_reset} onChange={(e) => update({ template_password_reset: e.target.value })} />
              <p className="ct-template-hint">Placeholders: {"{username}"}, {"{site_name}"}, {"{link}"}</p>
            </div>

            <div className="ct-settings-field">
              <label className="ct-field-label">Send a test email</label>
              <div className="ct-field-row">
                <input placeholder="you@example.com" value={testAddress} onChange={(e) => setTestAddress(e.target.value)} className="ct-test-input" />
                <button className="btn btn-secondary btn-sm" onClick={test} type="button" disabled={testStatus === "testing"}>
                  {testStatus === "testing" ? "Sending…" : "Send test"}
                </button>
              </div>
              {testStatus === "ok" && <p className="alert alert-success"><IconCheckCircle width={14} height={14} /> {testMessage}</p>}
              {testStatus === "fail" && <p className="alert alert-danger"><IconX width={14} height={14} /> Test failed — {testMessage}</p>}
            </div>
          </>
        )}

        <div className="ct-settings-footer">
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </button>
          {saved && <span className="ct-saved-tick"><IconCheckCircle width={14} height={14} /> Saved</span>}
        </div>
      </div>

      <style>{`
        .ct-settings-card { padding: var(--space-4); display: flex; flex-direction: column; }
        .ct-settings-row { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-5); padding: var(--space-4) 0; border-bottom: 1px solid var(--border); }
        .ct-settings-row:first-child { padding-top: 0; }
        .ct-settings-label { font-size: var(--text-base); font-weight: 600; margin: 0 0 4px; }
        .ct-settings-hint { font-size: var(--text-sm); color: var(--text-muted); margin: 0; max-width: 420px; line-height: 1.55; }
        .ct-toggle { position: relative; flex-shrink: 0; }
        .ct-toggle input { position: absolute; opacity: 0; width: 40px; height: 22px; margin: 0; cursor: pointer; }
        .ct-toggle-track { display: block; width: 40px; height: 22px; background: var(--surface-raised); border: 1px solid var(--border); border-radius: 12px; transition: background var(--dur) var(--ease); }
        .ct-toggle-thumb { display: block; width: 16px; height: 16px; background: var(--text-muted); border-radius: 50%; margin: 2px; transition: transform var(--dur) var(--ease), background var(--dur) var(--ease); }
        .ct-toggle input:checked + .ct-toggle-track { background: var(--accent-dim); }
        .ct-toggle input:checked + .ct-toggle-track .ct-toggle-thumb { transform: translateX(18px); background: var(--accent); }
        .ct-settings-field { padding: var(--space-4) 0; border-bottom: 1px solid var(--border); }
        .ct-settings-field input, .ct-settings-field textarea { width: 100%; max-width: 420px; font-family: var(--font-body); }
        .ct-field-label { display: block; font-size: var(--text-sm); font-weight: 500; color: var(--text-muted); margin-bottom: var(--space-2); }
        .ct-field-row { display: flex; gap: var(--space-3); }
        .ct-field-row .ct-settings-field { flex: 1; }
        .ct-port-field { max-width: 100px; }
        .ct-port-field input { max-width: 100px; }
        .ct-test-input { flex: 1; max-width: 260px; background: var(--surface-raised); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 10px; color: var(--text); font-size: var(--text-sm); }
        .ct-template-hint { font-size: var(--text-xs); color: var(--text-faint); margin: 6px 0 0; }
        .ct-settings-footer { display: flex; align-items: center; gap: var(--space-3); padding-top: var(--space-4); }
        .ct-saved-tick { display: flex; align-items: center; gap: 5px; font-size: var(--text-sm); color: var(--complete); }
      `}</style>
    </div>
  );
}

function formatHistoryTime(createdAt) {
  const then = new Date(createdAt.replace(" ", "T") + "Z");
  return then.toLocaleString();
}

function ActivityPanel() {
  const [history, setHistory] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getLoginHistory(200).then(setHistory).catch((e) => setError(e.message));
  }, []);

  if (!history) return <div className="state-screen"><span className="spinner" /></div>;

  return (
    <div className="ct-panel">
      {error && <p className="alert alert-danger">{error}</p>}
      <p className="ct-settings-hint">Most recent 200 sign-in attempts, successful and failed — useful for spotting brute-force attempts.</p>

      <div className="card ct-table-card">
        <table className="ct-table">
          <thead>
            <tr><th>Username</th><th>Result</th><th>Method</th><th>IP address</th><th>When</th></tr>
          </thead>
          <tbody>
            {history.length === 0 ? (
              <tr><td colSpan={5} className="ct-muted-cell" style={{ textAlign: "center", padding: "24px" }}>No login attempts recorded yet.</td></tr>
            ) : (
              history.map((h) => (
                <tr key={h.id}>
                  <td>{h.username}</td>
                  <td>
                    <span className={`badge ${h.success ? "badge-complete" : "badge-neutral"}`} style={!h.success ? { color: "var(--danger)", background: "var(--danger-soft)", borderColor: "rgba(226,87,76,0.35)" } : undefined}>
                      {h.success ? "Success" : "Failed"}
                    </span>
                  </td>
                  <td className="ct-muted-cell">{h.method === "jellyfin" ? "Jellyfin" : "Local"}</td>
                  <td className="ct-muted-cell">{h.ip_address || "—"}</td>
                  <td className="ct-muted-cell">{formatHistoryTime(h.created_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
