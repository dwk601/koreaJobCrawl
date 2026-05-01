import logging
import os
from pathlib import Path
import yaml
from crawler.db import get_engine, init_db, get_session
from crawler.gtksa import GTKSACrawler
from crawler.jobkoreausa import JobKoreaUSACrawler
from crawler.workingus import WorkingUSCrawler
from crawler.texasksa import TexasKSACrawler

logger = logging.getLogger(__name__)

CRAWLERS = [
    GTKSACrawler,
    JobKoreaUSACrawler,
    WorkingUSCrawler,
    TexasKSACrawler,
]

def run_all(config, project_root=None):
    db_path = os.environ.get('DB_PATH') or config.get('db_path', 'jobs.db')
    if project_root and not Path(db_path).is_absolute():
        db_path = str(project_root / db_path)
    engine = get_engine(db_path)
    init_db(engine)
    session = get_session(engine)
    try:
        for CrawlerCls in CRAWLERS:
            crawler = CrawlerCls(session, config)
            try:
                logger.info(f"Starting {CrawlerCls.SOURCE}")
                crawler.run()
                deactivated = crawler.deactivate_old_jobs()
                if deactivated:
                    logger.info(f"Deactivated {deactivated} old jobs from {CrawlerCls.SOURCE}")
                session.commit()
                logger.info(f"Finished {CrawlerCls.SOURCE}")
            except Exception as e:
                logger.exception(f"Failed {CrawlerCls.SOURCE}: {e}")
                session.rollback()
    finally:
        session.close()

def main(project_root=None):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    config_path = Path('config.yaml')
    if project_root:
        config_path = project_root / 'config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    run_all(config, project_root=project_root)

if __name__ == '__main__':
    main()
