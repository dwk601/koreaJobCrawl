#!/usr/bin/env python3
import fcntl
import os
import sys
from pathlib import Path

LOCK_FILE = '/tmp/koreaJobCrawl.lock'

lock_fd = open(LOCK_FILE, 'w')
try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print('Another crawler instance is already running. Exiting.')
    sys.exit(0)

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from crawler.runner import main

if __name__ == '__main__':
    try:
        main(project_root=PROJECT_ROOT)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass
