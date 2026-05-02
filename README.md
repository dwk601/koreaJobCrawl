# Korean Job Board Crawler

A fully automated ETL pipeline that scrapes Korean job posting boards in the US, cleans the data, and publishes it to a PocketBase backend API. Designed to run on a schedule (e.g., twice weekly) on a server.

**Supported sites**
- [gtksa.net](https://gtksa.net/bbs/board.php?bo_table=hiring) — GTKSA 구인/구직
- [jobkoreausa.com](https://jobkoreausa.com/work/employ_list.html) — JobKoreaUSA
- [workingus.com](https://www.workingus.com/forums/forum/job-postings/) — WorkingUS Job Postings
- [texasksa.org](https://www.texasksa.org/%ec%b7%a8%ec%97%85-%ec%a0%95%eb%b3%b4/) — TexasKSA 채용공고

---

## Architecture

```
[Crawl]        [Clean]           [Migrate]
 Docker     →  SQLite       →   PocketBase
(run.py)      (clean_data.py)   (migrate_to_pocketbase.py)
  │                │                  │
  │                │                  │
Playwright    Deduplicate        Normalized schema
4 job boards  Extract contacts   Sources, Companies
Upsert DB     Remove spam        Locations, Categories
              Extract location   Job Postings (with relations)
```

The entire pipeline is orchestrated by `deploy/run-pipeline.sh` and triggered via cron.

---

## Quick Start

### 1. Clone & Configure

```bash
git clone https://github.com/dwk601/koreaJobCrawl.git
cd koreaJobCrawl
```

Edit `config.yaml` to adjust crawling behavior:

```yaml
delay_min: 1.5          # Min delay between requests (seconds)
delay_max: 2.5          # Max delay between requests (seconds)
recency_skip_days: 7    # Skip re-scraping posts updated within N days
max_age_days: 60        # Only scrape jobs posted within N days (0 = no limit)
```

### 2. Run the Full Pipeline

```bash
# Run everything: crawl → clean → migrate to PocketBase
./deploy/run-pipeline.sh

# Dry-run (preview without modifying PocketBase)
./deploy/run-pipeline.sh --dry-run
```

### 3. Schedule Automated Runs

On your server, add a cron job:

```bash
crontab -e
```

```
# Every Sunday at 3:00 AM
0 3 * * 0 /home/dwk1/koreaJobCrawl/deploy/run-pipeline.sh

# Twice weekly: Sunday and Wednesday at 3:00 AM
0 3 * * 0,3 /home/dwk1/koreaJobCrawl/deploy/run-pipeline.sh
```

Logs are written to `/home/dwk1/crawler-pipeline.log` with automatic rotation (30-day retention).

---

## Pipeline Stages

### Stage 1: Crawl (Docker)

Scrapes all 4 job boards using Playwright and stores raw data in SQLite.

```bash
cd deploy
docker compose up --build
```

The SQLite database is created automatically on first run and persists in `deploy/data/jobs.db`.

View live logs:
```bash
docker compose logs -f
```

> In Docker, `db_path` from `config.yaml` is ignored. The container always uses `DB_PATH=/app/data/jobs.db`.

### Stage 2: Clean (SQLite)

Processes the raw scraped data to improve quality:

```bash
python3 clean_data.py
```

**What it does:**
- **Removes spam** — filters out beauty services, ads, non-job postings (보톡스, 필러, 마사지, etc.)
- **Removes job-seeking posts** — keeps only 구인 (hiring), removes 구직 (job seeking)
- **Strips HTML** — converts raw HTML `content` to plain text `cleaned_content`
- **Extracts contacts** — parses emails, phone numbers, and salary info into separate columns
- **Computes content hash** — for deduplication tracking
- **Assigns quality score** — 100 for valid jobs, 0 for spam (spam is then deleted)

### Stage 3: Migrate (PocketBase)

Publishes cleaned data to PocketBase with a normalized schema:

```bash
# Live migration
python3 migrate_to_pocketbase.py

# Dry-run (preview only, no writes)
python3 migrate_to_pocketbase.py --dry-run
```

**What it does:**
- **Deduplicates** — keeps only the most recent post per `content_hash`
- **Extracts location** — parses city, state, country from free-text location
- **Extracts company** — parses company names from title/content
- **Normalizes salary** — deduplicates and cleans salary strings
- **Skips existing records** — fetches all `(source, external_id)` pairs from PocketBase and only imports new ones (idempotent re-runs)
- **Creates relations** — links job postings to sources, companies, locations, and categories

---

## PocketBase Schema

The migration creates 5 normalized collections:

### `sources`
| Field | Type | Description |
|-------|------|-------------|
| `name` | Text (unique) | Site identifier: `gtksa`, `workingus`, etc. |
| `url` | URL | Source website URL |
| `is_active` | Bool | Whether the source is actively crawled |

### `companies`
| Field | Type | Description |
|-------|------|-------------|
| `name` | Text | Company name |
| `website` | URL | Company website (if available) |
| `email_domain` | Text | Extracted email domain |

### `locations`
| Field | Type | Description |
|-------|------|-------------|
| `city` | Text | Parsed city name |
| `state` | Text | US state abbreviation (e.g., `AL`, `GA`) |
| `country` | Text | `US` or `KR` |
| `full_text` | Text | Original location string |

### `categories`
| Field | Type | Description |
|-------|------|-------------|
| `name` | Text (unique) | Category name (e.g., `구인`) |

### `job_postings`
| Field | Type | Description |
|-------|------|-------------|
| `source` | Relation → sources | Job board source |
| `company` | Relation → companies | Hiring company |
| `location` | Relation → locations | Job location |
| `category` | Relation → categories | Post category |
| `external_id` | Text | Site-native job ID |
| `title` | Text | Job title |
| `cleaned_content` | Text | Plain-text job description (HTML stripped) |
| `salary_info` | Text | Extracted salary/wage information |
| `contact_email` | Text | Extracted email addresses |
| `contact_phone` | Text | Extracted phone numbers |
| `detail_url` | URL | Direct link to original post |
| `date_posted` | Date | Original post date |
| `scraped_at` | Date | Last crawl timestamp |
| `views` | Number | View count |
| `votes` | Number | Vote count |
| `is_active` | Bool | Whether the posting is still active |
| `content_hash` | Text | MD5 hash of cleaned content |
| `quality_score` | Number | Data quality score (100 = good) |

**Unique constraint:** `(source, external_id)` — prevents duplicates on re-runs.

**API rules:** Public read access (`listRule` and `viewRule` are open). Create/update/delete are restricted.

---

## SQLite Database Schema

The crawler stores raw data in a single SQLite table `jobs` before cleaning:

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
| `votes` | Integer | Vote count |
| `category` | String | Post category |
| `content` | Text | Full HTML content |
| `detail_url` | String | Direct URL |
| `scraped_at` | DateTime | Last crawl timestamp |
| `is_active` | Boolean | Whether the post is active |

**Added by `clean_data.py`:**
| Field | Type | Description |
|-------|------|-------------|
| `cleaned_content` | Text | HTML-stripped plain text |
| `content_hash` | Text | MD5 hash for deduplication |
| `quality_score` | Integer | 100 = good, 0 = spam |
| `contact_email` | Text | Extracted emails |
| `contact_phone` | Text | Extracted phones |
| `salary_info` | Text | Extracted salary |
| `is_spam` | Boolean | True if spam/non-job |
| `is_job_seeker` | Boolean | True if 구직 post |

Unique: `(source_site, external_id)` — enables upsert on re-runs.

---

## Check Results

### SQLite
```bash
sqlite3 data/jobs.db "SELECT source_site, COUNT(*) FROM jobs GROUP BY source_site;"
```

### PocketBase
Query the API directly:
```bash
# List all job postings (public read access)
curl http://YOUR_SERVER:8020/api/collections/job_postings/records

# Expand relations to see company, location, etc.
curl "http://YOUR_SERVER:8020/api/collections/job_postings/records?expand=source,company,location"

# Filter by source
curl "http://YOUR_SERVER:8020/api/collections/job_postings/records?filter=source.name='gtksa'"
```

### Export to CSV
```bash
sqlite3 data/jobs.db ".mode csv" ".output jobs.csv" "SELECT * FROM jobs;"
```

---

## Project Structure

```
.
├── config.yaml              # Crawler configuration
├── requirements.txt         # Python dependencies
├── run.py                   # CLI entrypoint (Docker)
├── clean_data.py            # Data cleaning pipeline
├── migrate_to_pocketbase.py # SQLite → PocketBase migration
├── deploy/
│   ├── run-pipeline.sh      # Full pipeline orchestrator (cron target)
│   ├── Dockerfile
│   ├── docker-compose.yml   # Mounts data/ for persistence
│   ├── cron.example         # Example crontab entry
│   ├── crawler.service      # systemd service file
│   ├── crawler.timer        # systemd timer file
│   └── data/                # SQLite DB lives here (auto-created)
└── crawler/                 # Core package
    ├── base.py              # Shared Playwright crawler base
    ├── db.py                # SQLAlchemy models + engine
    ├── runner.py            # Orchestrates all crawlers
    ├── gtksa.py
    ├── jobkoreausa.py
    ├── texasksa.py
    └── workingus.py
```

---

## Configuration

Edit `config.yaml` before running:

| Key | Description | Default |
|-----|-------------|---------|
| `delay_min` / `delay_max` | Request delay range (seconds) | 1.5 / 2.5 |
| `sites.{name}.max_pages` | Page limit per site. `0` = unlimited | 0 |
| `recency_skip_days` | Skip re-scraping posts updated within N days | 7 |
| `max_age_days` | Only scrape jobs posted within N days (0 = no limit) | 60 |

> `db_path` is ignored in Docker. The container always uses `DB_PATH=/app/data/jobs.db`.

---

## License

MIT License. See [LICENSE](LICENSE).
