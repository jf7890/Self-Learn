# Self Learn

Self-hosted video learning platform for personal use or small teams. Add course folders, rescan the library, and watch lessons with private progress tracking and rich study notes.

## Features

- Local accounts, per-user learning progress and admin-managed course access
- Automatic course/lesson discovery from folders
- Robust MP4 Range streaming, buffering feedback, seeking and saved playback position
- Private rich-text notes with headings, lists, quotes, pasted images and PDF export
- Responsive desktop/mobile interface
- SQLite database; suitable for a small deployment
- Custom logo, title and other settings from the admin panel

## Course access control

Administrators can open **Admin → Members → Course access** to grant or revoke individual courses. Admin accounts always have access to every course. Authorization is enforced by the API for course details, media, attachments, subtitles, notes, comments and progress—not merely hidden in the frontend.

When upgrading an existing installation, the first startup grants existing non-admin users access to all courses that already exist, preserving previous behavior. New users and courses are deny-by-default until an administrator grants access. Revoking access does not delete a learner's notes or progress.

## Course structure

Place courses under `courses/`. Each direct child folder is treated as one course.

```text
courses/
└── Microsoft-Admin/
    ├── 01 Introduction.mp4
    ├── 02 Installation.mp4
    └── Section 2/
        └── 03 Configuration.mp4
```

Video files remain on the host. After adding or reorganizing files, open:

**Admin → Library → Rescan**

Do not store application data inside `courses/`. Docker mounts this directory read-only.

## Deploy with Docker Compose

Requirements: Docker Engine with the Compose v2 plugin. The Compose specification no longer needs a top-level `version:` field.

```bash
git clone <repository-url> Self-learn
cd Self-learn
cp docker-compose.example.yml docker-compose.yml
cp .env.example .env
```

Edit `.env` and set at least:

```env
SECRET_KEY=replace-with-a-random-32-plus-character-string
CORS_ORIGINS=http://SERVER_IP:4173
```

Generate a secret with:

```bash
openssl rand -hex 32
```

Start the application:

```bash
docker compose up -d --build
```

Open:

```text
http://SERVER_IP:4173
```

The API is available on port `8000`. On first use, follow the setup screen to create the administrator account.

Useful commands:

```bash
docker compose ps
docker compose logs -f
docker compose restart
docker compose down
```

## Run directly on a VM/LXC

For a fresh Debian/Ubuntu VM or LXC, use the setup script. It installs Python, FFmpeg/FFprobe and Node.js 20 when needed, generates `.env`, and installs locked dependencies:

```bash
git clone <repository-url> Self-learn
cd Self-learn
chmod +x setup-local.sh run-local.sh
sudo ./setup-local.sh
./run-local.sh
```

The installer preserves an existing `.env`, `courses/`, and `data/`. Review `.env` after setup if the server IP/domain differs from the detected address.

For manual installation, provide Python 3 with `venv`, Node.js 20+, npm, and FFmpeg/FFprobe, then run:

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/pip install -r server/requirements.txt
npm --prefix frontend ci
./run-local.sh
```

The startup script listens on all interfaces:

- Web: `http://SERVER_IP:4173`
- API: `http://SERVER_IP:8000`

Stop it with `Ctrl+C`.

## Common configuration

| File/path | Purpose |
|---|---|
| `.env` | Secret key, allowed frontend origins and optional port variables |
| `docker-compose.yml` | Docker ports, volume mounts and container settings |
| `courses/` | Host-managed course and video library |
| `data/ulearn.db` | SQLite users, progress, settings and note HTML |
| `data/note-images/` | Images pasted into private notes |
| `frontend/public/` | Default logo and favicon assets |
| `setup-local.sh` | One-time Debian/Ubuntu VM/LXC dependency installer |
| `run-local.sh` | Direct VM/LXC development startup script (Vite + Uvicorn) |
| `deploy-production.sh` | Install/update the Nginx + systemd production deployment |
| `deploy/` | Versioned Nginx and systemd templates |
| `server/requirements.txt` | Pinned Python package versions |
| `frontend/package-lock.json` | Locked frontend dependency tree used by `npm ci` |

Optional ports and authentication/proxy settings can be added to `.env`:

```env
WEB_PORT=4173
API_PORT=8000
SESSION_COOKIE_SECURE=true
TRUSTED_PROXIES=127.0.0.1,::1
```

For direct local development over plain HTTP, use `SESSION_COOKIE_SECURE=false`. Keep it `true` for HTTPS production. Only list reverse proxies you control in `TRUSTED_PROXIES`.

If the frontend is served from a domain, use the exact origin:

```env
CORS_ORIGINS=https://learn.example.com
```

Multiple origins are comma-separated. For direct VM/LXC **development**, Vite automatically allows the hostnames extracted from `CORS_ORIGINS`, so there is no need to edit `frontend/vite.config.js`. Production uses the Nginx template in `deploy/`; `vite.config.js` remains in the repository for local development. If an unusual development setup needs additional Host headers without adding CORS origins, set bare hostnames separately:

```env
VITE_ALLOWED_HOSTS=internal-alias.local,another-host.example.com
```

## Data and backup

All persistent application data is stored in `data/`; course videos are stored separately in `courses/`.

For a basic backup, stop writes and copy both directories:

```bash
docker compose stop       # Docker deployment only
cp -a data data-backup
cp -a courses courses-backup
```

At minimum, preserve:

- `data/ulearn.db`
- `data/note-images/`
- `courses/`

Never commit `.env`, `data/`, or private course videos to a public repository.

## Updating

```bash
git pull
```

Docker:

```bash
docker compose up -d --build
```

VM/LXC development: stop the current process and run `./run-local.sh` again.

VM/LXC production (Nginx + systemd):

```bash
git pull --ff-only
.venv/bin/pip install -r server/requirements.txt
sudo ./deploy-production.sh
```

The production script builds the frontend into `/var/www/selflearn`, installs the versioned service/proxy templates, restarts `selflearn-api`, reloads Nginx, and runs health checks. Adjust paths/domain/ports in `deploy/selflearn-api.service` and `deploy/nginx-selflearn.conf` when deploying somewhere other than `/root/Self-Learn`.

## Architecture and developer handoff

This section is the canonical orientation for future maintainers and coding agents. Read it before changing authentication, media delivery, access control, scanning, or deployment.

### Runtime architecture

Official production uses this path:

```text
Browser
  ↓ HTTPS
Cloudflare Tunnel
  ↓
Nginx :4173
  ├── /          → static Vite build in /var/www/selflearn
  └── /api/*     → FastAPI on 127.0.0.1:8000
                       ├── SQLite: data/ulearn.db
                       ├── note images: data/note-images/
                       └── course media: courses/ (host-managed)
```

Vite is a build tool and development server only. Do not run `vite --host` as the official production frontend. Nginx must serve the built files, and systemd must supervise FastAPI.

Canonical production paths are currently:

```text
Repository:  /root/Self-Learn
Database:    /root/Self-Learn/data/ulearn.db
Courses:     /root/Self-Learn/courses
Web root:    /var/www/selflearn
API service: selflearn-api.service
```

Do not accidentally start Uvicorn without `ULEARN_DB` and `COURSES_ROOT`; that can create or use an unrelated database such as `/data/ulearn.db`.

### Backend layout

`server/main.py` is intentionally small. It creates the FastAPI application, installs middleware, includes routers, runs startup checks, and retains a few compatibility aliases for tests/older callers.

```text
server/
├── main.py                         application composition and middleware
├── auth.py                         password/JWT/session dependency helpers
├── db.py                           schema initialization and SQLite helpers
├── rate_limit.py                   login/forgot-password budgets and trusted proxy IPs
├── scanner.py                      filesystem course discovery and FFprobe metadata
├── schemas.py                      API request models
├── access/policies.py              course/lesson ACL and safe course paths
├── services/note_sanitizer.py      authoritative rich-note sanitization
├── services/ranges.py              bounded HTTP Range parsing
├── services/playback_tickets.py    opaque session-bound media tickets
└── routers/
    ├── auth_routes.py              setup/login/logout/reset flows
    ├── branding.py                 public/admin branding
    ├── courses.py                  course and lesson reads
    ├── media.py                    media, ticket, subtitle, attachment delivery
    ├── notes.py                    private notes and note images
    ├── progress.py                 progress, stats and continue watching
    ├── comments.py                 lesson comments
    └── admin.py                    users, ACL, settings, email, backup and rescan
```

Keep SQL parameterized with SQLite `?` placeholders. Do not concatenate request values into SQL.

### Frontend layout

```text
frontend/src/
├── api.js                          same-origin API client and authenticated asset URLs
├── App.jsx                         routing, auth gates and top navigation
├── components/                     page and feature components
└── features/player/
    ├── PlayerTimeline.jsx
    ├── playerUtils.js
    └── usePersistedAudio.js
```

Authentication state has two parts:

- The server sets a `HttpOnly`, `Secure`, `SameSite=Lax` `session_token` cookie.
- `ct_user` and a non-secret `ct_token` marker in local storage are frontend routing hints only. They are not credentials and must never be accepted by the backend.

The API client uses same-origin cookies. Do not put session JWTs back into query strings, local storage, media URLs, subtitles, note images, attachments, or backup URLs.

### Media delivery and download deterrence

The goal is to deter ordinary users and users with basic DevTools knowledge without degrading playback. It is not DRM and cannot prevent screen recording or a specialist from reproducing authenticated browser requests.

Current video/audio flow:

1. The authenticated player calls `POST /api/media/{lesson_id}/ticket`.
2. The API verifies the account and course ACL, then returns an opaque `/api/play/{ticket}` URL.
3. A ticket is bound to the user, lesson and exact HttpOnly session cookie.
4. The player sends normal bounded Range requests to the ticket URL.
5. The API rechecks the ticket, account and course ACL on every request.
6. Ticket URLs are accepted only for same-origin/same-site requests whose `Sec-Fetch-Dest` is `video`, preventing a simple **Open in new tab** download.
7. Tickets expire after 15 idle minutes and have a six-hour hard lifetime. The player automatically obtains a replacement and resumes at the previous timestamp after a long pause or an expired-ticket media error.

Additional behavior:

- Open-ended Range responses are capped by `RANGE_WINDOW_BYTES` (currently 8 MiB).
- The player begins with metadata preload and switches to automatic preload after playback.
- `controlsList="nodownload"` removes the normal browser download affordance.
- Media responses are private/no-store and served inline.
- Direct video/audio access through `/api/media/{lesson_id}` is rejected; that compatibility route remains for non-video lesson documents.
- Original MP4 files are not modified, transcoded or reduced in quality.

Do not globally block right-click, copy/paste, `Ctrl+U`, or DevTools. Learners need normal browser interaction for notes and technical material. HLS is deliberately deferred; do not introduce it incidentally.

Playback tickets are stored in process memory. Restarting FastAPI invalidates existing ticket URLs; the frontend is expected to recover by requesting a new ticket. If production later runs multiple API workers, tickets must move to a shared store or use a carefully designed signed-ticket format before increasing the worker count.

### Authorization invariants

Course access is server-enforced. UI locks are not security boundaries.

- Admins always access every course.
- Members access only explicitly granted courses.
- ACL checks must remain on course details, lessons, media/tickets, subtitles, attachments, notes/images, progress and comments.
- Revoking access must not delete notes or progress.
- Private notes and note images are scoped to both user and lesson.
- Media ticket issuance and every Range request must retain ACL checks.

When adding an endpoint derived from a course or lesson, require the relevant policy from `server/access/policies.py` before returning metadata or file content.

### Authentication and proxy security

- Login throttling combines per-IP-and-identifier and aggregate per-IP budgets.
- Nonexistent accounts still perform a dummy bcrypt comparison to reduce username timing leakage.
- Forgot-password responses do not reveal whether an email exists.
- `X-Forwarded-For` is trusted only when the direct peer appears in `TRUSTED_PROXIES`; the default is `127.0.0.1,::1`.
- Keep `SESSION_COOKIE_SECURE=true` on HTTPS production. Set it to `false` only for direct HTTP development.
- `SECRET_KEY` must be a strong stable secret. Changing it invalidates all sessions.

### Scanner and source-of-truth rules

The filesystem under `courses/` is the library source of truth. Admin → Library → Rescan synchronizes it with SQLite. The scanner recognizes numeric and `Part`-style section folders and uses FFprobe for media duration.

Never rename, trim, transcode, overwrite, or delete original course media without explicit authorization. For an approved bulk rename:

1. Detect destination collisions.
2. Back up `data/ulearn.db`.
3. Rename files.
4. Update stored relative paths to preserve lesson IDs, progress and notes.
5. Rescan and validate course/lesson counts and duration coverage.

### Development validation

Run these checks before every commit that changes application behavior:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q server tests
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=low
git diff --check
```

The route-count smoke check is useful after router work:

```bash
ULEARN_DB=/tmp/selflearn-smoke.db \
COURSES_ROOT=/tmp/selflearn-courses \
SECRET_KEY=test-only-secret-key-that-is-long-enough \
.venv/bin/python -c 'import sys; sys.path.insert(0,"server"); import main; print(len(main.app.routes))'
```

Do not use `npm audit fix --force`. Upgrade dependencies deliberately, build, test and review major-version behavior.

### Safe production update and rollback

Never deploy a partially validated refactor. Before changing production:

1. Confirm SSH access, repository branch/status, disk space, and active services.
2. Back up `data/ulearn.db` with a timestamped name.
3. Pull only with `git pull --ff-only`.
4. Run backend tests/compile and frontend install/build on the production host.
5. Deploy static assets, restart FastAPI only when backend code changed, and reload Nginx after `nginx -t` succeeds.
6. Verify local UI/API first, then public UI/API.
7. Smoke-test login, ACL, notes/images, progress/comments, video ticket issuance, Range playback, pause/resume renewal, subtitles, attachments and admin functions.

Rollback consists of checking out the previous known-good commit, rebuilding/redeploying the frontend, restarting the API when needed, and restoring the pre-deployment SQLite backup only if a database migration caused the failure. Do not overwrite a newer healthy database merely to roll back frontend/backend code.

The deployment script's immediate API health check can race a slower service startup. If it exits after restart, inspect `systemctl status selflearn-api`, `journalctl -u selflearn-api`, listening ports and direct health endpoints before deciding whether rollback is necessary.

### Known follow-up work

The current system is production-usable for a small trusted group, but useful future work includes:

- Broader integration tests for login cookies, ACL denial, note ownership, private images, `GET`/`HEAD`/Range media, ticket renewal, progress, comments and admin operations.
- Split `frontend/src/api.js` into domain clients and reduce `AdminDashboard.jsx`.
- Add frontend route/component code splitting to reduce the approximately 788 KB minified main bundle.
- Move repeated router business/SQL logic into repositories/services when it materially improves testing.
- Harden remaining operational items: run FastAPI as an unprivileged user, restrict `.env`/SQLite permissions, review CSP, upload validation/quotas, Jellyfin SSRF controls, firewall and OS updates.

Preserve existing API response shapes and learner-visible behavior unless a migration is explicitly planned and tested.

## License

See [LICENSE](LICENSE).
