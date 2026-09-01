const BASE = "/api";

function getToken() {
  return localStorage.getItem("ct_token");
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem("ct_token");
    localStorage.removeItem("ct_user");
    window.location.href = "/login";
    return null;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }

  return res.status === 204 ? null : res.json();
}

// Separate helper for multipart uploads — no Content-Type header (the
// browser sets the correct multipart boundary itself).
async function uploadRequest(path, formData) {
  const token = getToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { method: "POST", headers, body: formData });

  if (res.status === 401) {
    localStorage.removeItem("ct_token");
    localStorage.removeItem("ct_user");
    window.location.href = "/login";
    return null;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  authConfig: () => request("/auth/config"),
  setup: (username, password) =>
    request("/auth/setup", { method: "POST", body: JSON.stringify({ username, password }) }),
  login: (username, password) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  jellyfinLogin: (username, password) =>
    request("/auth/jellyfin/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  getCourses: () => request("/courses"),
  getFeatured: () => request("/featured"),
  getCourse: (id) => request(`/courses/${id}`),
  getContinueWatching: () => request("/continue-watching"),
  getMyStats: () => request("/me/stats"),
  getNote: (lessonId) => request(`/lessons/${lessonId}/note`),
  saveNote: (lessonId, contentHtml) => request(`/lessons/${lessonId}/note`, { method: "PUT", body: JSON.stringify({ content_html: contentHtml }) }),
  uploadNoteImage: (lessonId, file) => {
    const form = new FormData();
    form.append("file", file);
    return uploadRequest(`/lessons/${lessonId}/note-images`, form);
  },
  getComments: (lessonId) => request(`/lessons/${lessonId}/comments`),
  postComment: (lessonId, body) => request(`/lessons/${lessonId}/comments`, { method: "POST", body: JSON.stringify({ body }) }),
  deleteComment: (commentId) => request(`/comments/${commentId}`, { method: "DELETE" }),
  reportDuration: (lessonId, durationSeconds) =>
    request(`/lessons/${lessonId}/duration`, { method: "POST", body: JSON.stringify({ duration_seconds: durationSeconds }) }),
  updateProgress: (lessonId, positionSeconds, completed) =>
    request("/progress", {
      method: "POST",
      body: JSON.stringify({ lesson_id: lessonId, position_seconds: positionSeconds, completed }),
    }),
  rescan: () => request("/admin/rescan", { method: "POST" }),
  mediaUrl: (lessonId) => `${BASE}/media/${lessonId}?t=${getToken()}`,
  authenticatedAssetUrl: (path) => `${path}${path.includes("?") ? "&" : "?"}t=${encodeURIComponent(getToken() || "")}`,
  subtitleUrl: (subtitleId) => `${BASE}/subtitles/${subtitleId}?t=${getToken()}`,
  attachmentUrl: (attachmentId) => `${BASE}/attachments/${attachmentId}?t=${getToken()}`,

  // admin
  listUsers: () => request("/admin/users"),
  createUser: (username, password, isAdmin, email = "", sendInvite = false) =>
    request("/admin/users", { method: "POST", body: JSON.stringify({ username, password, is_admin: isAdmin, email, send_invite: sendInvite }) }),
  deleteUser: (id) => request(`/admin/users/${id}`, { method: "DELETE" }),
  resetPassword: (id, password) =>
    request(`/admin/users/${id}/reset-password`, { method: "POST", body: JSON.stringify({ password }) }),
  getAdminSettings: () => request("/admin/settings"),
  updateAdminSettings: (jellyfinAuthEnabled, jellyfinUrl) =>
    request("/admin/settings", {
      method: "PUT",
      body: JSON.stringify({ jellyfin_auth_enabled: jellyfinAuthEnabled, jellyfin_url: jellyfinUrl }),
    }),
  testJellyfin: (url) => request("/admin/settings/test-jellyfin", { method: "POST", body: JSON.stringify({ jellyfin_url: url }) }),
  getAdminCourses: () => request("/admin/courses"),
  updateAdminCourse: (courseId, tags, isFeatured, isHidden) =>
    request(`/admin/courses/${courseId}`, {
      method: "PUT",
      body: JSON.stringify({ tags, is_featured: isFeatured, is_hidden: isHidden }),
    }),
  getNotificationSettings: () => request("/admin/notifications"),
  updateNotificationSettings: (settings) =>
    request("/admin/notifications", { method: "PUT", body: JSON.stringify(settings) }),
  testNotification: () => request("/admin/notifications/test", { method: "POST" }),
  getBranding: () => request("/branding"),
  updateBranding: (siteName, accentColor) =>
    request("/admin/branding", { method: "PUT", body: JSON.stringify({ site_name: siteName, accent_color: accentColor }) }),
  uploadBrandingLogo: (file) => {
    const form = new FormData();
    form.append("file", file);
    return uploadRequest("/admin/branding/logo", form);
  },
  deleteBrandingLogo: () => request("/admin/branding/logo", { method: "DELETE" }),
  uploadBrandingFavicon: (file) => {
    const form = new FormData();
    form.append("file", file);
    return uploadRequest("/admin/branding/favicon", form);
  },
  deleteBrandingFavicon: () => request("/admin/branding/favicon", { method: "DELETE" }),
  forgotPassword: (email) => request("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
  checkAuthToken: (token) => request(`/auth/token/${token}`),
  setPasswordViaToken: (token, password) =>
    request(`/auth/token/${token}`, { method: "POST", body: JSON.stringify({ password }) }),
  getEmailSettings: () => request("/admin/email-settings"),
  updateEmailSettings: (settings) => request("/admin/email-settings", { method: "PUT", body: JSON.stringify(settings) }),
  testEmailSettings: (toAddress) => request("/admin/email-settings/test", { method: "POST", body: JSON.stringify({ to_address: toAddress }) }),
  getLoginHistory: (limit = 200) => request(`/admin/login-history?limit=${limit}`),
  backupUrl: () => `${BASE}/admin/backup?t=${getToken()}`,
};

export { getToken };
