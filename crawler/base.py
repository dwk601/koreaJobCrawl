import logging
import time
import random
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, parse_qs, urlparse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from crawler.db import Job, select, text

logger = logging.getLogger(__name__)

class BaseCrawler:
    SOURCE = 'base'

    def __init__(self, db_session, config):
        self.db = db_session
        self.config = config
        self.headless = config.get('headless', True)
        self.delay_min = config.get('delay_min', 1.0)
        self.delay_max = config.get('delay_max', 2.5)
        self.max_retries = config.get('max_retries', 3)
        self.timeout = config.get('timeout', 30000)
        self.commit_batch = config.get('commit_batch', 20)
        self.recency_skip_days = config.get('recency_skip_days', 7)
        self.max_age_days = config.get('max_age_days', 0)
        self.jobs_since_commit = 0
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
        )
        self.page = self.context.new_page()

    def stop(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def goto(self, url):
        for attempt in range(self.max_retries):
            try:
                self.page.goto(url, wait_until='networkidle', timeout=self.timeout)
                time.sleep(random.uniform(self.delay_min, self.delay_max))
                return True
            except Exception as e:
                logger.warning(f"goto {url} attempt {attempt+1} failed: {e}")
                time.sleep(2 ** attempt)
        return False

    def soup(self):
        return BeautifulSoup(self.page.content(), 'html.parser')

    def parse_date(self, text):
        if not text:
            return None
        text = text.strip()
        # strip common labels
        text = re.sub(r'^(Updated:|작성일|등록일|Date:?\s*)', '', text, flags=re.IGNORECASE).strip()

        # try exact formats
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%m-%d-%Y',
            '%m-%d-%Y %H:%M:%S',
            '%m-%d-%Y %H:%M',
            '%Y.%m.%d',
            '%y-%m-%d %H:%M',
            '%y-%m-%d',
            '%m-%d',
            '%Y-%m-%d',
            '%B %d, %Y',
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(text, fmt)
                if fmt in ('%m-%d', '%m-%d-%Y'):
                    dt = dt.replace(year=datetime.now().year)
                return dt
            except ValueError:
                continue

        # extract first date-like token from messy text
        patterns = [
            (r'(\d{4})[-.](\d{2})[-.](\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?', '%Y-%m-%d %H:%M:%S'),
            (r'(\d{2})[-.](\d{2})[-.](\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?', '%y-%m-%d %H:%M:%S'),
            (r'(\d{2})[-.](\d{2})[-.](\d{4})', '%m-%d-%Y'),
            (r'(\d{4})[-.](\d{2})[-.](\d{2})', '%Y-%m-%d'),
            (r'(\d{2})[-.](\d{2})[-.](\d{2})', '%y-%m-%d'),
        ]
        for pat, fmt in patterns:
            m = re.search(pat, text)
            if m:
                try:
                    return datetime.strptime(m.group(0).replace('.', '-'), fmt)
                except ValueError:
                    pass
        return None

    def should_scrape_detail(self, external_id):
        stmt = select(Job).where(Job.source_site == self.SOURCE, Job.external_id == external_id)
        existing = self.db.scalar(stmt)
        if existing and existing.scraped_at:
            if (datetime.utcnow() - existing.scraped_at).days < self.recency_skip_days:
                return False
        return True

    def is_job_too_old(self, date_posted):
        if not date_posted or self.max_age_days <= 0:
            return False
        cutoff = datetime.utcnow().date() - timedelta(days=self.max_age_days)
        return date_posted.date() < cutoff

    def upsert_job(self, data: dict):
        stmt = select(Job).where(Job.source_site == data['source_site'], Job.external_id == data['external_id'])
        existing = self.db.scalar(stmt)
        now = datetime.utcnow()
        if existing:
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            existing.scraped_at = now
            existing.is_active = True
        else:
            self.db.add(Job(scraped_at=now, is_active=True, **data))
        self.jobs_since_commit += 1
        if self.jobs_since_commit >= self.commit_batch:
            self.db.commit()
            self.jobs_since_commit = 0

    def deactivate_old_jobs(self):
        if self.max_age_days <= 0:
            return 0
        cutoff = datetime.utcnow() - timedelta(days=self.max_age_days)
        stmt = (
            select(Job)
            .where(Job.source_site == self.SOURCE)
            .where(Job.date_posted < cutoff)
            .where(Job.is_active == True)
        )
        old_jobs = self.db.scalars(stmt).all()
        count = 0
        for job in old_jobs:
            job.is_active = False
            count += 1
        if count:
            self.db.commit()
        return count

    def purge_old_jobs(self, purge_days=180):
        if purge_days <= 0:
            return 0
        cutoff = datetime.utcnow() - timedelta(days=purge_days)
        stmt = (
            select(Job)
            .where(Job.source_site == self.SOURCE)
            .where(Job.date_posted < cutoff)
            .where(Job.is_active == False)
        )
        old_jobs = self.db.scalars(stmt).all()
        count = 0
        for job in old_jobs:
            self.db.delete(job)
            count += 1
        if count:
            self.db.commit()
            self.db.execute(text('VACUUM'))
        return count

    def run(self):
        raise NotImplementedError
