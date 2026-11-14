.PHONY: help install lint format format-check typecheck security secrets-check pip-audit \
        lock-check structure-check check deploy-check migrations-check schema-check \
        seed test ci

PYTHON ?= python3

help:
	@echo "Kaveh185 Enterprise Backend — Quality & Verification Commands"
	@echo "  make lint             - Run Ruff linter"
	@echo "  make format-check     - Check code formatting with Ruff"
	@echo "  make typecheck        - Run Mypy static type checker"
	@echo "  make security         - Run Bandit SAST security scanner"
	@echo "  make secrets-check    - Verify zero leaked secrets with detect-secrets"
	@echo "  make pip-audit        - Audit dependencies for CVEs"
	@echo "  make lock-check       - Verify requirements lockfiles are in sync"
	@echo "  make structure-check  - Verify STRUCTURE.md matches repository layout"
	@echo "  make check            - Run Django system checks"
	@echo "  make deploy-check     - Run production security checks (--fail-level WARNING)"
	@echo "  make migrations-check - Ensure zero ungenerated model migrations"
	@echo "  make schema-check     - Validate OpenAPI 3.0 contract (--fail-on-warn)"
	@echo "  make test             - Run pytest suite with >=90% coverage gate"
	@echo "  make ci               - Run all local CI quality gates in sequence"

install:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

format-check:
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy apps config manage.py

security:
	$(PYTHON) -m bandit -c pyproject.toml -r apps config manage.py -q

secrets-check:
	$(PYTHON) -m detect_secrets scan apps config manage.py

pip-audit:
	$(PYTHON) -m pip_audit -r requirements.txt -r requirements-dev.txt --progress-spinner off

lock-check:
	$(PYTHON) scripts/generate_locks.py --check

structure-check:
	$(PYTHON) scripts/generate_structure.py --check

check:
	$(PYTHON) manage.py check

deploy-check:
	DJANGO_SETTINGS_MODULE=config.settings.production \
	DJANGO_SECRET_KEY=prod-deploy-check-secret-key-9876543210-abcdef-1234567890-abcdef \
	$(PYTHON) manage.py check --deploy --fail-level WARNING

migrations-check:
	$(PYTHON) manage.py makemigrations --check --dry-run

schema-check:
	$(PYTHON) manage.py spectacular --validate --fail-on-warn --file /tmp/kaveh185-openapi.yaml

seed:
	$(PYTHON) manage.py migrate
	$(PYTHON) manage.py seed_kaveh185

seed-demo:
	$(PYTHON) manage.py migrate
	$(PYTHON) manage.py seed_kaveh185 --with-demo-data

test:
	$(PYTHON) -m pytest --cov=apps --cov-report=term-missing --cov-fail-under=90

ci: lint format-check typecheck security pip-audit lock-check structure-check check deploy-check migrations-check schema-check test
