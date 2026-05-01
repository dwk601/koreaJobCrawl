#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from crawler.runner import main

if __name__ == '__main__':
    main(project_root=PROJECT_ROOT)
