# uLearn

A self-hosted, multi-user course platform for video and document-based
learning content — built for people who've accumulated a pile of
downloaded courses (Udemy, LinkedIn Learning, cohort-based programs,
community exports, etc.) and want a proper place to watch them, track
progress, and share access with others, without uploading anything to a
third party.

Point it at a folder of course exports, run one command, and you get a
Netflix-style library with real per-user progress tracking, a custom
video player, and an admin dashboard — all running on your own hardware.

## Features

**Watching**
- Custom video/audio player: resume where you left off, adjustable
  playback speed, auto-advance to the next lesson, keyboard-free touch
  controls on mobile
- Subtitles/closed captions, auto-matched to their lesson by filename
  (e.g. "3. Introduction.en_US.srt" matches "3. Introduction.mp4") —
  SRT is converted to WebVTT on the fly since that's what browsers
  actually support. Multiple languages per lesson show up as a picker;
  the on/off preference carries over between lessons automatically
- Built-in viewer for document lessons (PDF, plain text, Markdown) —
  not everything is a video
- Downloadable resources/attachments per section, kept separate from the
  tracked lesson sequence
- Per-lesson discussion — a simple comment thread under each lesson

**Progress**
- Per-user completion and watch-position tracking, with a safety net
  that marks a lesson complete once ~95% watched (not just on literal
  end-of-file)
- "Continue watching" row on the home screen — one card per course,
  always the most recently touched lesson
- A personal progress page: current streak, lessons/courses completed,
  total watch time
- A downloadable completion certificate once a course is finished

**Finding things**
- Search and status filters (in progress / completed / not started) on
  the home screen
- Tag-based filtering, with tags managed per course from the admin
  dashboard
- A "Featured" row for courses an admin wants to highlight, and a "New"
  badge that appears automatically on anything added in the last week
- In-course lesson search

**Make it yours**
- Custom site name, logo, and browser favicon — set live from the admin
  dashboard, no rebuild needed. Falls back cleanly to the default mark
  if nothing's been customized
- Custom accent color — one hex value drives every button, progress bar,
  badge, and highlight throughout the app

**Notifications**
- Optional Discord and/or Telegram alerts when a member completes a
  course, or when a new course is added to the library
- Message templates are plain text with placeholders
  (`{username}`, `{course_title}`, `{lesson_count}`), editable from the
  dashboard with sensible defaults out of the box, plus a test-send
  button that reports back if a webhook or bot token is actually wrong

**Auth**
- Local accounts by default — an admin account is created on first run,
  and that admin creates member accounts from the dashboard (no public
  self-signup)
- Optional email invites — if SMTP is configured, an admin can invite a
  member by email instead of setting a password directly; the member
  gets a link to set their own password
- Self-service password reset via email, once SMTP is configured — no
  admin involvement needed for someone who's forgotten their password
- Optional Jellyfin sign-in, off by default. An admin can turn it on
  and set the Jellyfin server URL from the dashboard at any time — no
  redeploy required. When enabled, a "Sign in with Jellyfin" button
  appears under the normal login form. Signing in with Jellyfin
  auto-links to a local account with a matching username, or creates one

**Security**
- Login rate limiting — 5 failed attempts per 15 minutes, keyed by IP
  and username together, applied to local login, Jellyfin login,
  password reset requests, and first-run setup
- Every authenticated request re-verifies the account against the
  database rather than trusting a cached claim in the session token —
  deleting a user or changing admin status takes effect immediately,
  not whenever their existing session happens to expire
- Passwords hashed with bcrypt; invite/reset links use cryptographically
  random tokens that expire (48 hours for invites, 1 hour for resets)
  and are single-use
- Full login history (success and failure, with IP and method) visible
  to admins, alongside a per-member "last login" timestamp

**Admin dashboard**
- **Members** — add, remove, and manage local/Jellyfin-linked accounts
- **Courses** — tag courses, mark them featured, or hide them from the
  library entirely
- **Branding** — site name, logo, favicon, accent color
- **Sign-in settings** — toggle and configure Jellyfin sign-in, with a
  connection test
- **Notifications** — Discord/Telegram webhook config and message
  templates, with a test-send button
- **Email** — SMTP settings, invite/reset email templates, and a
  test-send button
- **Activity** — recent login attempts (successful and failed), useful
  for spotting brute-force attempts
- **Library** — rescan the course folder on demand; safe to run any
  time, since it upserts what it finds and prunes anything removed from
  disk (with a built-in guard against wiping the library if a mount
  looks unexpectedly empty). Also downloads a one-click backup of
  everything uLearn stores itself — accounts, progress, comments,
  settings, branding — as a zip. Doesn't include course files, since
  those live in your own storage and are backed up separately from this

**Operations**
- `GET /health` — no auth, actually queries the database rather than
  just confirming the process is alive, for use with Docker's own
  `HEALTHCHECK` (both containers have one built in) or external
  monitoring like Uptime Kuma

**The scanner**
Course exports are rarely uniform, so the folder scanner is deliberately
forgiving:
- Numbered folders become sections; numbered files become lessons, with
  flexible separators (`01-Title`, `01.Title`, `01 Title` all work)
- Video/audio files are always treated as lessons regardless of naming;
  documents only count as lessons if they're explicitly part of the
  numbered sequence, otherwise they're treated as resources
- Handles per-lesson subfolders (one folder per lesson containing the
  video and any accompanying files)
- Handles flat courses too — if lesson files sit directly in the course's
  root folder with no section subfolders at all, they're automatically
  grouped into a single implicit "Lessons" section rather than being
  silently treated as non-lesson attachments
- Handles bulk-downloader exports too — folders like `~Get Your Files
  Here !` that wrap the real numbered sections one level deeper get
  looked through automatically, rather than the whole course ending up
  with zero lessons. A reseller tag on the course folder name itself
  (e.g. `[ SomeSite.com ] Udemy - Course Title`) gets stripped for
  display too, without touching anything on disk
- Automatically skips local HTML snapshot pages and `.url` shortcut
  files that some course platforms and downloaders bundle alongside the
  real content
- Subtitle files (`.srt`/`.vtt`) are matched to their lesson by filename
  in the same folder, rather than showing up as a generic download

## Quick start

Requires Docker and Docker Compose.

```bash
git clone https://github.com/<your-username>/ulearn.git
cd ulearn
cp .env.example .env
cp docker-compose.example.yml docker-compose.yml
# edit .env: set SECRET_KEY to a random 32+ character string,
# and CORS_ORIGINS to whatever URL you'll actually access uLearn from
# edit docker-compose.yml if you want different ports than the defaults

docker compose up -d --build
```

This starts two services:
- `ulearn-api` — FastAPI backend, listening on `8000`
- `ulearn-web` — the React frontend, listening on `4173`

Put your own reverse proxy in front of both (Caddy, nginx, Traefik,
whatever you already run) — proxy `/api/*` to the API container and
everything else to the web container. The exact config depends on your
setup, so it's intentionally not prescribed here.

If you just want to try it locally without a reverse proxy, the frontend
container isn't set up to reach the API directly in that mode — use the
[local development](#local-development) instructions instead for a
quick look.

## First run

1. Visit the site — since no accounts exist yet, you'll land on a setup
   screen. Create the admin account.
2. Drop course folders into `./courses/` (see the structure below).
3. Admin → Library → **Rescan library**.
4. *(Optional)* Admin → Sign-in settings → enable Jellyfin sign-in, set
   the server URL, test the connection, save.
5. Admin → Members → add accounts for anyone else who needs access.
6. Admin → Courses → tag things, feature a course, hide anything that
   isn't ready yet.
7. *(Optional)* Admin → Branding → set a site name, logo, favicon, and
   accent color to make it yours.
8. *(Optional)* Admin → Notifications → hook up Discord or Telegram for
   completion/new-course alerts.

### Expected course folder structure

```
courses/
  Photoshop 2021 One-on-One Advanced/
    01-Introduction/
      01-Welcome to Photoshop One-on-One.mp4
      02-Previously on Photoshop One-on-One.mp4
    02-The Advanced Selection Commands/
      01-Color Range Focus Area and more.mp4
      ...
      resources/
        exercise-files.zip
```

Top-level folders under `courses/` are courses. Numbered subfolders are
sections. See "The scanner" above for how individual files
get classified.

### Using network storage instead of a local folder

The `courses/` volume mount in `docker-compose.yml` can point anywhere
readable on the host — it doesn't have to be a subfolder of the project
itself. This is worth doing once a course library gets large, so it
lives on a NAS or other network storage instead of local disk.

- **Windows + Docker Desktop**: map the network share to a drive letter
  first (File Explorer → This PC → Map network drive), then point the
  volume at that drive letter, e.g. `Z:\Courses:/app/courses:ro`.
  Docker Desktop's WSL2 backend can bind-mount Windows drive letters
  directly. UNC paths (`\\nas\share`) generally don't work directly in
  the compose file — map a drive letter first.
- **Linux hosts**: mount the NFS/SMB share at the OS level (e.g. via
  `/etc/fstab`) to a path like `/mnt/courses`, then point the volume at
  that: `/mnt/courses:/app/courses:ro`.

Keep the `:ro` (read-only) suffix regardless of where the mount points
— uLearn only ever reads course files, never writes to them.

## Configuration

Set these in `.env` (copied from `.env.example`):

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Random string used to sign session tokens. Generate one with `openssl rand -hex 32` or similar. The API refuses to start if this is unset or left as a placeholder. |
| `CORS_ORIGINS` | Recommended | The URL(s) uLearn is served from, comma-separated. Defaults to `http://localhost:4173` if unset. |

Jellyfin sign-in is *not* configured via environment variables — it's
set live from the admin dashboard after deployment, so it can be
toggled or changed without rebuilding or redeploying.

## Local development

```bash
# backend
cd server
pip install -r requirements.txt --break-system-packages
export SECRET_KEY=dev-secret
export COURSES_ROOT=../courses
uvicorn main:app --reload

# frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Vite's dev server proxies `/api/*` to `localhost:8000`. Open
`http://localhost:5173` — you'll land on the setup screen since no users
exist yet.

## Tech stack

- **Backend**: FastAPI, SQLite, JWT sessions, bcrypt password hashing
- **Frontend**: React + Vite, no UI framework dependency
- **Media**: direct file serving with HTTP range requests — no
  transcoding, so source formats need to be browser-playable (h264/mp4
  is the safest bet; some course exports use codecs that Safari or
  mobile browsers won't like)
- **Deployment**: Docker Compose, two containers, SQLite file on a
  mounted volume

## Known limitations

- No transcoding — see above. If a video won't play, it's almost always
  a codec issue with the source file, not a uLearn bug.
- Course thumbnails are generated (gradient + initials), not extracted
  from the actual video.
- Removing a member deletes their progress on every course (cascading
  delete, by design, not currently reversible).
- Schema changes across versions may require a fresh database rather
  than an automatic migration, depending on the release — check release
  notes if upgrading.

## License

MIT — see [LICENSE](LICENSE).

## Self-learn MVP quick start

The host course library is `./courses`; each direct child is one course. The current library is
`courses/Microsoft-Admin` with numbered MP4 lessons. Private notes and pasted images are stored
under `./data`, not beside the videos.

### Run directly on a VM/LXC

```bash
cp .env.example .env
# Set a random SECRET_KEY in .env (for example: openssl rand -hex 32)
./run-local.sh
```

Open `http://SERVER_IP:4173`. The API listens on `0.0.0.0:8000`; Vite proxies `/api` to it.
The first visitor creates the admin account and the library is scanned automatically.

### Docker Compose

```bash
cp .env.example .env
# Set SECRET_KEY and set CORS_ORIGINS=http://SERVER_IP:4173
docker compose up -d --build
```

`./courses` is mounted read-only and `./data` persists SQLite, note images, and branding. You never
need to copy or upload videos inside a container. Use Admin → Library → Rescan after adding files.
