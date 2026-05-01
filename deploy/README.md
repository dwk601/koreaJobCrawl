# Deployment Guide

## Prerequisites

- Python 3.12+ (for local development/testing)
- Docker + Docker Compose (on target server)
- rsync + ssh (for remote deploy script)

---

## Local Development (No Docker)

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium
./venv/bin/python run.py
```

---

## Option 1: Docker on Remote Server (Recommended)

### Step 1: Prepare the remote server

Ensure Docker and Docker Compose are installed:

```bash
ssh user@your-server "docker --version && docker compose version"
```

### Step 2: Deploy with the helper script

From your local machine:

```bash
cd deploy
./deploy-remote.sh user@your-server /opt/korea-job-crawl
```

This will:
- rsync the project to the remote server (excluding `venv/`, `.git/`, `*.db`, `*.log`)
- Build the Docker image on the remote
- Run the crawler once
- The SQLite database (`jobs.db`) is created automatically inside `deploy/data/`

### Step 3: Schedule weekly runs on the remote server

On the **remote server**, add a cron job:

```bash
ssh user@your-server
crontab -e
```

Add:

```
0 3 * * 0 cd /opt/korea-job-crawl/deploy && docker compose up --build >> /var/log/crawler.log 2>&1
```

Or use systemd timer (see `crawler.service` and `crawler.timer`):

```bash
sudo cp /opt/korea-job-crawl/deploy/crawler.service /etc/systemd/system/
sudo cp /opt/korea-job-crawl/deploy/crawler.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable crawler.timer
sudo systemctl start crawler.timer
```

### Step 4: Check results

```bash
ssh user@your-server "sqlite3 /opt/korea-job-crawl/deploy/data/jobs.db 'SELECT source_site, COUNT(*) FROM jobs GROUP BY source_site;'"
```

### Manual Docker run (no script)

If you prefer to copy files manually:

```bash
# On local machine
scp -r crawler/ config.yaml requirements.txt run.py user@server:/opt/korea-job-crawl/

# On remote server
cd /opt/korea-job-crawl/deploy
mkdir -p data
docker compose up --build
```

---

## Option 2: Bare-metal with Systemd Timer

See `crawler.service` and `crawler.timer` files. Copy them to `/etc/systemd/system/`, adjust paths to match your install directory, then enable the timer.

---

## Option 3: Bare-metal with Cron

See `cron.example`. Paste the line into `crontab -e` after adjusting paths.

---

## Configuration

Edit `config.yaml` on the server to tune:

| Key | Description |
|-----|-------------|
| `db_path` | SQLite file location. Ignored in Docker; container uses `DB_PATH=/app/data/jobs.db` |
| `delay_min` / `delay_max` | Request delays in seconds |
| `sites.{name}.max_pages` | Page limit per site (`0` = unlimited) |
| `recency_skip_days` | Skip re-scraping posts scraped within N days |
| `headless` | `true` for production; `false` shows browser window (debug) |

---

## Database Persistence with Docker

The `docker-compose.yml` mounts a `data/` directory from the host into the container. This means:
- Data survives container restarts
- You can query the DB directly on the host with `sqlite3 deploy/data/jobs.db`
- The first run will auto-create `jobs.db` inside the mounted directory
- No need to pre-create the file manually

---

## Logs

Docker logs go to stdout. View with:

```bash
cd deploy && docker compose logs
```

For cron/systemd, logs are written to `/var/log/crawler.log` (adjust path as needed).
