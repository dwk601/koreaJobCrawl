# Korean Job Board Crawler

A Dockerized Python crawler that scrapes Korean job posting boards in the US and stores structured data in SQLite. Designed to run on a schedule (e.g., weekly) on a server.

**Supported sites**
- [gtksa.net](https://gtksa.net/bbs/board.php?bo_table=hiring) — GTKSA 구인/구직
- [jobkoreausa.com](https://jobkoreausa.com/work/employ_list.html) — JobKoreaUSA
- [workingus.com](https://www.workingus.com/forums/forum/job-postings/) — WorkingUS Job Postings
- [texasksa.org](https://www.texasksa.org/%ec%b7%a8%ec%97%85-%ec%a0%95%eb%b3%b4/) — TexasKSA 채용공고

---

## Quick Start (Docker)

```bash
git clone https://github.com/dwk601/koreaJobCrawl.git
cd koreaJobCrawl/deploy
docker compose up -d --build
```

The `-d` flag runs the crawler in the background (detached). The SQLite database is created automatically on first run and persists in `deploy/data/jobs.db`.

View live logs:
```bash
docker compose logs -f
```

---

## Schedule Weekly Runs

On your server, add a cron job:

```bash
crontab -e
```

Add this line (adjust path and user):

```
0 3 * * 0 cd /home/YOUR_USERNAME/koreaJobCrawl/deploy && docker compose up -d --build >> /home/YOUR_USERNAME/crawler.log 2>&1
```

Runs every Sunday at 3:00 AM.

---

## Check Results

```bash
sqlite3 data/jobs.db "SELECT source_site, COUNT(*) FROM jobs GROUP BY source_site;"
```

Or export to CSV:

```bash
sqlite3 data/jobs.db ".mode csv" ".output jobs.csv" "SELECT * FROM jobs;"
```

---

## Configuration

Edit `config.yaml` before running. Key fields:

| Key | Description | Default |
|-----|-------------|---------|
| `delay_min` / `delay_max` | Request delay range (seconds) | 1.5 / 2.5 |
| `sites.{name}.max_pages` | Page limit per site. `0` = unlimited | 0 |
| `recency_skip_days` | Skip re-scraping posts updated within N days | 7 |

> `db_path` is ignored in Docker. The container always uses `DB_PATH=/app/data/jobs.db`.

---

## Database Schema

Single SQLite table `jobs`:

| Field | Type | Description |
|-------|------|-------------|
| `source_site` | String | `gtksa`, `jobkoreausa`, `workingus`, `texasksa` |
| `external_id` | String | Site-native job ID |
| `title` | String | Job title |
| `company` | String | Company name |
| `location` | String | Job location |
| `author` | String | Post author |
| `date_posted` | DateTime | Post date |
| `views` | Integer | View count |
| `content` | Text | Full HTML content |
| `detail_url` | String | Direct URL |
| `scraped_at` | DateTime | Last crawl timestamp |

Unique: `(source_site, external_id)` — enables upsert on re-runs.

---

## Project Structure

```
.
├── config.yaml              # Crawler configuration
├── requirements.txt         # Python dependencies
├── run.py                   # CLI entrypoint
├── crawler/                 # Core package
│   ├── base.py              # Shared Playwright crawler base
│   ├── db.py                # SQLAlchemy models + engine
│   ├── gtksa.py
│   ├── jobkoreausa.py
│   ├── runner.py
│   ├── texasksa.py
│   └── workingus.py
└── deploy/
    ├── Dockerfile
    ├── docker-compose.yml   # Mounts data/ for persistence
    └── data/                # SQLite DB lives here (auto-created)
```

---

## License

MIT License. See [LICENSE](LICENSE).
