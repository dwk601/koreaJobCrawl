import logging
import re
from urllib.parse import urljoin
from crawler.base import BaseCrawler

logger = logging.getLogger(__name__)

class JobKoreaUSACrawler(BaseCrawler):
    SOURCE = 'jobkoreausa'
    LIST_URL = 'https://jobkoreausa.com/work/employ_list.html?page={page}'

    def run(self):
        self.start()
        try:
            max_pages = self.config.get('sites', {}).get('jobkoreausa', {}).get('max_pages', 0)
            page = 1
            while True:
                if max_pages and page > max_pages:
                    break
                url = self.LIST_URL.format(page=page)
                logger.info(f"JKUSA list page {page}: {url}")
                if not self.goto(url):
                    break
                soup = self.soup()
                rows = soup.select('#list .list-view .row.element')
                jobs_on_page = 0
                for row in rows:
                    link_el = row.select_one('.job1.floatleft > a')
                    if not link_el:
                        continue
                    href = link_el.get('href', '')
                    m = re.search(r'no=(\d+)', href)
                    if not m:
                        continue
                    job_id = m.group(1)
                    detail_url = urljoin(url, href)

                    company_el = row.select_one('.col-1 strong')
                    company = company_el.get_text(strip=True) if company_el else ''

                    col2 = row.select_one('.col-2')
                    title = ''
                    location = ''
                    closing_date = ''
                    if col2:
                        strings = list(col2.stripped_strings)
                        if strings:
                            title = strings[0]
                        meta = col2.select_one('.ks_1.gray99.mt5')
                        if meta:
                            meta_text = meta.get_text(separator=' ', strip=True)
                            lm = re.search(r'Location:\s*(.+?)(?:Closing Date:|$)', meta_text)
                            if lm:
                                location = lm.group(1).strip()
                            cm = re.search(r'Closing Date:\s*(.+)', meta_text)
                            if cm:
                                closing_date = cm.group(1).strip()

                    views_el = row.select_one('.col-5')
                    views = 0
                    if views_el:
                        vm = re.search(r'(\d+)', views_el.get_text(strip=True))
                        views = int(vm.group(1)) if vm else 0

                    if not self.should_scrape_detail(job_id):
                        continue

                    if not self.goto(detail_url):
                        continue
                    detail_soup = self.soup()
                    title_el = detail_soup.select_one('.j-title-content .t-txt')
                    title = title_el.get_text(strip=True) if title_el else title

                    mod_el = detail_soup.select_one('.cin-box .modify_date')
                    date_str = mod_el.get_text(strip=True).replace('Updated:', '').strip() if mod_el else ''
                    date_posted = self.parse_date(date_str)
                    if self.is_job_too_old(date_posted):
                        continue

                    views_el2 = detail_soup.select_one('.cin-box .hits em')
                    if views_el2:
                        vm = re.search(r'(\d+)', views_el2.get_text(strip=True))
                        views = int(vm.group(1)) if vm else views

                    main_html = self.page.content()
                    # iframe content
                    iframe = detail_soup.select_one('#job_content')
                    iframe_html = ''
                    if iframe and iframe.get('src'):
                        iframe_url = urljoin(detail_url, iframe['src'])
                        if self.goto(iframe_url):
                            iframe_soup = self.soup()
                            body = iframe_soup.select_one('body')
                            iframe_html = str(body) if body else self.page.content()

                    content = f'<!-- MAIN -->\n{main_html}\n<!-- IFRAME -->\n{iframe_html}'

                    self.upsert_job({
                        'source_site': self.SOURCE,
                        'external_id': job_id,
                        'title': title,
                        'company': company,
                        'location': location,
                        'author': '',
                        'date_posted': date_posted,
                        'views': views,
                        'votes': None,
                        'category': closing_date,
                        'content': content,
                        'detail_url': detail_url,
                    })
                    jobs_on_page += 1

                logger.info(f"JKUSA page {page}: {jobs_on_page} jobs")
                if jobs_on_page == 0:
                    break
                page += 1
        finally:
            self.db.commit()
            self.stop()
