# Self Learn

Self-hosted video learning platform for personal use or small teams. Add course folders, rescan the library, and watch lessons with private progress tracking and rich study notes.

## Features

- Local accounts and per-user learning progress
- Automatic course/lesson discovery from folders
- MP4 streaming with seeking and saved playback position
- Private rich-text notes with headings, lists, quotes, pasted images and PDF export
- Responsive desktop/mobile interface
- SQLite database; suitable for a small deployment
- Custom logo, title and other settings from the admin panel

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

Requirements: Docker and Docker Compose.

```bash
git clone <repository-url> Self-learn
cd Self-learn
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

Requirements:

- Python 3 with `venv`
- Node.js and npm
- FFmpeg/FFprobe

```bash
git clone <repository-url> Self-learn
cd Self-learn
cp .env.example .env
# Edit SECRET_KEY and CORS_ORIGINS
./run-local.sh
```

The script installs Python and frontend dependencies on first launch, then listens on all interfaces:

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
| `run-local.sh` | Direct VM/LXC startup script |

Optional ports can be added to `.env`:

```env
WEB_PORT=4173
API_PORT=8000
```

If the frontend is served from a domain, use the exact origin:

```env
CORS_ORIGINS=https://learn.example.com
```

Multiple origins are comma-separated.

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
