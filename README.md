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
| `run-local.sh` | Direct VM/LXC startup script |
| `server/requirements.txt` | Pinned Python package versions |
| `frontend/package-lock.json` | Locked frontend dependency tree used by `npm ci` |

Optional ports can be added to `.env`:

```env
WEB_PORT=4173
API_PORT=8000
```

If the frontend is served from a domain, use the exact origin:

```env
CORS_ORIGINS=https://learn.example.com
```

Multiple origins are comma-separated. For direct VM/LXC deployments, Vite automatically allows the hostnames extracted from `CORS_ORIGINS`, so there is no need to edit `frontend/vite.config.js`. If an unusual setup needs additional Host headers without adding CORS origins, set bare hostnames separately:

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

VM/LXC: stop the current process and run `./run-local.sh` again. If dependencies changed, run:

```bash
.venv/bin/pip install -r server/requirements.txt
npm --prefix frontend install
```

## License

See [LICENSE](LICENSE).
