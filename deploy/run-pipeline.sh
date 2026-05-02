#!/bin/bash
# Korean Job Crawler - Full Pipeline: Crawl -> Clean -> Migrate to PocketBase
# Usage: ./run-pipeline.sh [--dry-run]
# Schedule: Add to crontab (see deploy/cron.example)

set -euo pipefail

PROJECT_ROOT="/home/dwk1/koreaJobCrawl"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
LOG_FILE="/home/dwk1/crawler-pipeline.log"
MAX_LOG_DAYS=30
DRY_RUN=""

# Parse arguments
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] === DRY-RUN MODE ==="
fi

# Log rotation: keep last N days, archive older
rotate_logs() {
    if [[ -f "$LOG_FILE" ]]; then
        local age_days=$(( ($(date +%s) - $(stat -c %Y "$LOG_FILE" 2>/dev/null || echo 0)) / 86400 ))
        if [[ $age_days -gt $MAX_LOG_DAYS ]]; then
            mv "$LOG_FILE" "$LOG_FILE.old"
        fi
    fi
}

# Unified logging
log() {
    local level="$1"
    shift
    local msg="$*"
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] [$level] $msg" | tee -a "$LOG_FILE"
}

# Cleanup on exit
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log "ERROR" "Pipeline failed with exit code $exit_code"
        log "ERROR" "Check logs at $LOG_FILE"
    fi
}
trap cleanup EXIT

rotate_logs

log "INFO" "=== Starting pipeline ==="

# Stage 1: Crawl
log "INFO" "[CRAWL] Starting Docker compose..."
cd "$DEPLOY_DIR"
if [[ -n "$DRY_RUN" ]]; then
    log "INFO" "[CRAWL] [DRY-RUN] Would run: docker compose up --build"
else
    docker compose up --build >> "$LOG_FILE" 2>&1
fi
log "INFO" "[CRAWL] Complete"

# Stage 2: Clean
log "INFO" "[CLEAN] Starting data cleaning..."
cd "$PROJECT_ROOT"
if [[ -n "$DRY_RUN" ]]; then
    log "INFO" "[CLEAN] [DRY-RUN] Would run: python3 clean_data.py"
else
    python3 clean_data.py >> "$LOG_FILE" 2>&1
fi
log "INFO" "[CLEAN] Complete"

# Stage 3: Migrate to PocketBase
log "INFO" "[MIGRATE] Starting PocketBase migration..."
cd "$PROJECT_ROOT"
if [[ -n "$DRY_RUN" ]]; then
    log "INFO" "[MIGRATE] [DRY-RUN] Would run: python3 migrate_to_pocketbase.py --dry-run"
    python3 migrate_to_pocketbase.py --dry-run >> "$LOG_FILE" 2>&1
else
    python3 migrate_to_pocketbase.py >> "$LOG_FILE" 2>&1
fi
log "INFO" "[MIGRATE] Complete"

log "INFO" "=== Pipeline finished ==="
