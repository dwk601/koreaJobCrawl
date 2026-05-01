import logging
import re
from crawler.base import BaseCrawler

logger = logging.getLogger(__name__)

class WorkingUSCrawler(BaseCrawler):
    SOURCE = 'workingus'
    LIST_URL = 'https://www.workingus.com/forums/forum/job-postings/page/{page}/'

    def run(self):
        self.start()
        try:
            max_pages = self.config.get('sites', {}).get('workingus', {}).get('max_pages', 0)
            page = 1
            while True:
                if max_pages and page > max_pages:
                    break
                url = self.LIST_URL.format(page=page)
                logger.info(f"WorkingUS list page {page}: {url}")
                if not self.goto(url):
                    break
                soup = self.soup()
                rows = soup.select('#bbpress-forums li.bbp-body > ul')
                jobs_on_page = 0
                for row in rows:
                    row_id = row.get('id', '')
                    m = re.search(r'(\d+)', row_id)
                    topic_id = m.group(1) if m else row_id
                    link_el = row.select_one('li.bbp-topic-title a.bbp-topic-permalink')
                    if not link_el:
                        continue
                    title = link_el.get_text(strip=True)
                    detail_url = link_el.get('href', '')

                    company_el = row.select_one('li.bbp-topic-title .bbp-topic-job .company')
                    company = company_el.get_text(strip=True) if company_el else ''
                    loc_el = row.select_one('li.bbp-topic-title .bbp-topic-job .location')
                    location = loc_el.get_text(strip=True) if loc_el else ''

                    auth_el = row.select_one('li.bbp-topic-creator a')
                    author = auth_el.get_text(strip=True) if auth_el else ''

                    date_el = row.select_one('li.bbp-topic-freshness .date')
                    time_el = row.select_one('li.bbp-topic-freshness .time')
                    date_str = ''
                    if date_el and time_el:
                        date_str = f"{date_el.get_text(strip=True)} {time_el.get_text(strip=True)}"
                    elif date_el:
                        date_str = date_el.get_text(strip=True)
                    date_posted = self.parse_date(date_str)
                    if self.is_job_too_old(date_posted):
                        continue

                    views_el = row.select_one('li.bbp-topic-voice-count')
                    views = 0
                    if views_el:
                        vm = re.search(r'(\d+)', views_el.get_text(strip=True))
                        views = int(vm.group(1)) if vm else 0

                    if not self.should_scrape_detail(topic_id):
                        continue

                    if not self.goto(detail_url):
                        continue
                    detail_soup = self.soup()
                    title_el = detail_soup.select_one('header.entry-header h1.entry-title')
                    title = title_el.get_text(strip=True) if title_el else title
                    auth_el2 = detail_soup.select_one('.bbp-topic-header .author a')
                    author = auth_el2.get_text(strip=True) if auth_el2 else author
                    date_el2 = detail_soup.select_one('.bbp-topic-header .bbp-topic-post-date .date')
                    time_el2 = detail_soup.select_one('.bbp-topic-header .bbp-topic-post-date .time')
                    if date_el2 and time_el2:
                        date_str = f"{date_el2.get_text(strip=True)} {time_el2.get_text(strip=True)}"
                        date_posted = self.parse_date(date_str) or date_posted
                    views_el2 = detail_soup.select_one('.bbp-topic-header .view')
                    if views_el2:
                        vm = re.search(r'(\d+)', views_el2.get_text(strip=True))
                        views = int(vm.group(1)) if vm else views
                    content_el = detail_soup.select_one('.bbp-topic-content')
                    content = str(content_el) if content_el else ''

                    self.upsert_job({
                        'source_site': self.SOURCE,
                        'external_id': topic_id,
                        'title': title,
                        'company': company,
                        'location': location,
                        'author': author,
                        'date_posted': date_posted,
                        'views': views,
                        'votes': None,
                        'category': '',
                        'content': content,
                        'detail_url': detail_url,
                    })
                    jobs_on_page += 1

                logger.info(f"WorkingUS page {page}: {jobs_on_page} jobs")
                if jobs_on_page == 0:
                    break
                page += 1
        finally:
            self.stop()
