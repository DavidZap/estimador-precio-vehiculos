PYTHON ?= python

.PHONY: install run-api init-db check-db extract lint format

install:
	$(PYTHON) -m pip install -e .[dev]

run-api:
	uvicorn vehicle_price_estimator.api.main:app --host 0.0.0.0 --port 8000 --reload

init-db:
	$(PYTHON) scripts/init_db.py

check-db:
	$(PYTHON) scripts/check_db_connection.py

extract:
	$(PYTHON) scripts/extract_marketplace.py

lint:
	ruff check .

format:
	ruff check . --fix
