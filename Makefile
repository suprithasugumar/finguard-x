# FinGuard-X Makefile

VENV_PYTHON = .venv/bin/python
VENV_PYTEST = .venv/bin/pytest
VENV_ALEMBIC = .venv/bin/alembic
VENV_RUFF = .venv/bin/ruff

# Windows fallback detection
ifeq ($(OS),Windows_NT)
	VENV_PYTHON = .\.venv\Scripts\python.exe
	VENV_PYTEST = .\.venv\Scripts\pytest.exe
	VENV_ALEMBIC = .\.venv\Scripts\alembic.exe
	VENV_RUFF = .\.venv\Scripts\ruff.exe
endif

.PHONY: help test test-cov lint format migrate downgrade run-pipeline

help:
	@echo "Available commands:"
	@echo "  make test        - Run test suite"
	@echo "  make test-cov    - Run test suite with term-missing coverage report"
	@echo "  make lint        - Run ruff linter check"
	@echo "  make format      - Run ruff auto-formatter"
	@echo "  make migrate     - Run Alembic migrations to head"
	@echo "  make downgrade   - Downgrade Alembic migrations by 1"

test:
	$(VENV_PYTEST) backend/tests

test-cov:
	$(VENV_PYTEST) -v --cov=backend/app --cov-report=term-missing backend/tests

lint:
	$(VENV_RUFF) check backend/

format:
	$(VENV_RUFF) format backend/
	$(VENV_RUFF) check --fix backend/

migrate:
	$(VENV_ALEMBIC) upgrade head

downgrade:
	$(VENV_ALEMBIC) downgrade -1
