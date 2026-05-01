VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install run docker-build docker-run shell clean test

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(VENV)/bin/playwright install chromium

run:
	$(PYTHON) run.py

docker-build:
	cd deploy && docker compose build

docker-run:
	cd deploy && docker compose up --build

shell:
	cd deploy && docker compose run --rm crawler sh

clean:
	rm -rf $(VENV) __pycache__ crawler/__pycache__ *.db *.log

test:
	$(PYTHON) -c "import yaml; cfg=yaml.safe_load(open('config.yaml')); \
	[c.update({'max_pages':1}) for c in cfg.get('sites',{}).values()]; \
	yaml.dump(cfg, open('test_config.yaml','w')); \
	import subprocess; subprocess.run(['$(PYTHON)', 'run.py'])"
