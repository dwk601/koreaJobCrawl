import logging
import re
from urllib.parse import parse_qs, urlparse
from crawler.base import BaseCrawler

logger = logging.getLogger(__name__)

class GTKSACrawler(BaseCrawler):
    SOURCE = 'gtksa'
    LIST_URL = 'https://gtksa.net/bbs/board.php?bo_table=hiring&page={page}'

    def run(self):
        self.start()
        try:
            max_pages = self.config.get('sites', {}).get('gtksa', {}).get('max_pages', 0)
            page = 1
            while True:
                if max_pages and page > max_pages:
                    break
                url = self.LIST_URL.format(page=page)
                logger.info(f"GTKSA list page {page}: {url}")
                if not self.goto(url):
                    break
                soup = self.soup()
                rows = soup.select('table tbody tr')
                jobs_on_page = 0
                for row in rows:
                    if 'bo_notice' in row.get('class', []):
                        continue
                    link = row.select_one('td.td_subject a[href*="wr_id="]')
                    if not link:
                        continue
                    href = link.get('href', '')
                    m = re.search(r'wr_id=(\d+)', href)
                    if not m:
                        continue
                    wr_id = m.group(1)
                    title = link.get_text(strip=True)
                    cate_el = row.select_one('.bo_cate_link')
                    category = cate_el.get_text(strip=True) if cate_el else ''
                    author_el = row.select_one('.td_name .sv_member') or row.select_one('.td_name')
                    author = author_el.get_text(strip=True) if author_el else ''
                    date_el = row.select_one('.td_datetime')
                    date_str = date_el.get_text(strip=True) if date_el else ''
                    date_posted = self.parse_date(date_str)
                    if self.is_job_too_old(date_posted):
                        continue
                    views_el = row.select_one('.td_num')
                    views = 0
                    if views_el:
                        vm = re.search(r'(\d+)', views_el.get_text(strip=True))
                        views = int(vm.group(1)) if vm else 0

                    detail_url = href
                    if not detail_url.startswith('http'):
                        detail_url = 'https://gtksa.net' + detail_url

                    if not self.should_scrape_detail(wr_id):
                        continue

                    if not self.goto(detail_url):
                        continue
                    detail_soup = self.soup()
                    title_el = detail_soup.select_one('.bo_v_tit')
                    title = title_el.get_text(strip=True) if title_el else title
                    cate_el = detail_soup.select_one('.bo_v_cate')
                    category = cate_el.get_text(strip=True) if cate_el else category
                    content_el = detail_soup.select_one('#bo_v_con')
                    content = str(content_el) if content_el else ''
                    profile = detail_soup.select_one('.profile_info_ct')
                    if profile:
                        auth_el = profile.select_one('.sv_member')
                        author = auth_el.get_text(strip=True) if auth_el else author
                        date_el = profile.select_one('.if_date')
                        if date_el:
                            date_posted = self.parse_date(date_el.get_text(strip=True)) or date_posted
                        eye = profile.select_one('.fa-eye')
                        if eye:
                            vtxt = eye.find_parent('strong')
                            if vtxt:
                                vm = re.search(r'(\d+)', vtxt.get_text(strip=True))
                                views = int(vm.group(1)) if vm else views

                    self.upsert_job({
                        'source_site': self.SOURCE,
                        'external_id': wr_id,
                        'title': title,
                        'company': '',
                        'location': '',
                        'author': author,
                        'date_posted': date_posted,
                        'views': views,
                        'votes': None,
                        'category': category,
                        'content': content,
                        'detail_url': detail_url,
                    })
                    jobs_on_page += 1

                logger.info(f"GTKSA page {page}: {jobs_on_page} jobs")
                if jobs_on_page == 0:
                    break
                page += 1
        finally:
            self.stop()
