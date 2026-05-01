import logging
import re
from urllib.parse import parse_qs, urlparse
from crawler.base import BaseCrawler

logger = logging.getLogger(__name__)

class TexasKSACrawler(BaseCrawler):
    SOURCE = 'texasksa'
    LIST_URL = 'https://www.texasksa.org/%ec%b7%a8%ec%97%85-%ec%a0%95%eb%b3%b4/?pageid={page}&mod=list'

    def run(self):
        self.start()
        try:
            max_pages = self.config.get('sites', {}).get('texasksa', {}).get('max_pages', 0)
            page = 1
            while True:
                if max_pages and page > max_pages:
                    break
                url = self.LIST_URL.format(page=page)
                logger.info(f"TexasKSA list page {page}: {url}")
                if not self.goto(url):
                    break
                soup = self.soup()
                rows = soup.select('.kboard-list tbody tr')
                jobs_on_page = 0
                for row in rows:
                    if 'kboard-list-notice' in row.get('class', []):
                        continue
                    link_el = row.select_one('td.kboard-list-title a')
                    if not link_el:
                        continue
                    href = link_el.get('href', '')
                    m = re.search(r'uid=(\d+)', href)
                    if not m:
                        continue
                    uid = m.group(1)
                    title_el = row.select_one('td.kboard-list-title .kboard-default-cut-strings')
                    title = title_el.get_text(strip=True) if title_el else ''
                    author_el = row.select_one('td.kboard-list-user')
                    author = author_el.get_text(strip=True) if author_el else ''
                    date_el = row.select_one('td.kboard-list-date')
                    date_str = date_el.get_text(strip=True) if date_el else ''
                    date_posted = self.parse_date(date_str)
                    if self.is_job_too_old(date_posted):
                        continue
                    views_el = row.select_one('td.kboard-list-view')
                    views = 0
                    if views_el:
                        vm = re.search(r'(\d+)', views_el.get_text(strip=True))
                        views = int(vm.group(1)) if vm else 0
                    votes_el = row.select_one('td.kboard-list-vote')
                    votes = 0
                    if votes_el:
                        vm = re.search(r'(\d+)', votes_el.get_text(strip=True))
                        votes = int(vm.group(1)) if vm else 0

                    detail_url = href
                    if not detail_url.startswith('http'):
                        detail_url = 'https://www.texasksa.org' + detail_url

                    if not self.should_scrape_detail(uid):
                        continue

                    if not self.goto(detail_url):
                        continue
                    detail_soup = self.soup()
                    title_el = detail_soup.select_one('.kboard-document-wrap .kboard-title h1')
                    title = title_el.get_text(strip=True) if title_el else title
                    auth_el = detail_soup.select_one('.kboard-detail .detail-writer .detail-value')
                    author = auth_el.get_text(strip=True) if auth_el else author
                    date_el2 = detail_soup.select_one('.kboard-detail .detail-date .detail-value')
                    if date_el2:
                        date_posted = self.parse_date(date_el2.get_text(strip=True)) or date_posted
                    views_el2 = detail_soup.select_one('.kboard-detail .detail-view .detail-value')
                    if views_el2:
                        vm = re.search(r'(\d+)', views_el2.get_text(strip=True))
                        views = int(vm.group(1)) if vm else views
                    votes_el2 = detail_soup.select_one('.kboard-detail .detail-vote .detail-value')
                    if votes_el2:
                        vm = re.search(r'(\d+)', votes_el2.get_text(strip=True))
                        votes = int(vm.group(1)) if vm else votes
                    content_el = detail_soup.select_one('.kboard-document-wrap .kboard-content')
                    content = str(content_el) if content_el else ''

                    self.upsert_job({
                        'source_site': self.SOURCE,
                        'external_id': uid,
                        'title': title,
                        'company': '',
                        'location': '',
                        'author': author,
                        'date_posted': date_posted,
                        'views': views,
                        'votes': votes,
                        'category': '',
                        'content': content,
                        'detail_url': detail_url,
                    })
                    jobs_on_page += 1

                logger.info(f"TexasKSA page {page}: {jobs_on_page} jobs")
                if jobs_on_page == 0:
                    break
                page += 1
        finally:
            self.stop()
